from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_SKILLS = {
    "image-agent-operator",
    "image-agent-architect",
    "image-agent-developer",
    "image-agent-workflow-runner",
    "image-agent-result-reviewer",
    "image-agent-rag-curator",
    "neuroimaging-workflow-runner",
}

REQUIRED_SECTIONS = {
    "## Trigger Rules",
    "## Operating Rules",
    "## Reference Loading",
    "## Output Shape",
    "## Eval Hints",
}

REQUIRED_EVAL_CATEGORIES = {"normal_path", "missing_info", "risk_conflict"}
LONG_REFERENCE_LINE_THRESHOLD = 100
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?:OPENAI|DEEPSEEK|RAWCHAT|API)_?KEY\s*=\s*['\"]?[^`'\"\s<]+", re.IGNORECASE),
)


def audit_skill_maintenance(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root).resolve()
    skills_root = root_path / "docs" / "skills"
    findings: list[dict[str, str]] = []

    matrix = _audit_routing_matrix(skills_root, findings)
    skills = _audit_skills(skills_root, findings)
    references = _audit_references(skills_root, findings)
    evals = _audit_evals(skills_root, findings)

    return {
        "status": "passed" if not findings else "failed",
        "routing_matrix": matrix,
        "skills": skills,
        "references": references,
        "evals": evals,
        "findings": findings,
    }


def _audit_routing_matrix(skills_root: Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    matrix_path = skills_root / "maintenance" / "routing-matrix.json"
    if not matrix_path.exists():
        findings.append(_finding("routing_matrix_missing", str(matrix_path), "Routing matrix is missing."))
        return {"covered_skill_count": 0}
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.append(_finding("routing_matrix_invalid_json", str(matrix_path), str(exc)))
        return {"covered_skill_count": 0}

    skills = matrix.get("skills") if isinstance(matrix, dict) else None
    if not isinstance(skills, list):
        findings.append(_finding("routing_matrix_invalid_shape", str(matrix_path), "skills must be a list."))
        return {"covered_skill_count": 0}

    skill_names = {str(item.get("skill_name")) for item in skills if isinstance(item, dict)}
    missing = REQUIRED_SKILLS - skill_names
    extra = skill_names - REQUIRED_SKILLS
    for skill_name in sorted(missing):
        findings.append(_finding("routing_matrix_missing_skill", str(matrix_path), skill_name))
    for skill_name in sorted(extra):
        findings.append(_finding("routing_matrix_unknown_skill", str(matrix_path), skill_name))

    for item in skills:
        if not isinstance(item, dict):
            continue
        skill_name = str(item.get("skill_name") or "<unknown>")
        for key in ("primary_triggers", "owns", "defers_to"):
            if not isinstance(item.get(key), list) or not item[key]:
                findings.append(_finding("routing_matrix_missing_field", str(matrix_path), f"{skill_name}.{key}"))
        if item.get("defers_to") == [skill_name]:
            findings.append(_finding("routing_matrix_self_only_deferral", str(matrix_path), skill_name))

    serialized = json.dumps(matrix, ensure_ascii=False)
    if "dwi_fast_gpu_dti" not in serialized or "legacy QSIPrep/QSIRecon" not in serialized:
        findings.append(
            _finding(
                "routing_matrix_dwi_boundary_missing",
                str(matrix_path),
                "Matrix must distinguish production dwi_fast_gpu_dti from legacy QSIPrep/QSIRecon.",
            )
        )

    return {"covered_skill_count": len(skill_names & REQUIRED_SKILLS), "path": str(matrix_path)}


def _audit_skills(skills_root: Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    checked = 0
    for skill_name in sorted(REQUIRED_SKILLS):
        skill_dir = skills_root / skill_name
        skill_path = skill_dir / "SKILL.md"
        if not skill_path.exists():
            findings.append(_finding("skill_missing", str(skill_path), "SKILL.md is missing."))
            continue
        checked += 1
        text = skill_path.read_text(encoding="utf-8")
        metadata = _frontmatter(text)
        if metadata.get("name") != skill_name:
            findings.append(_finding("skill_name_mismatch", str(skill_path), str(metadata.get("name"))))
        if "Use when" not in str(metadata.get("description", "")):
            findings.append(_finding("skill_description_weak", str(skill_path), "description should include Use when."))
        missing_sections = REQUIRED_SECTIONS - set(re.findall(r"^## .+$", text, flags=re.MULTILINE))
        for section in sorted(missing_sections):
            findings.append(_finding("skill_missing_section", str(skill_path), section))
        _audit_reference_targets(skill_dir, skill_path, text, findings)
        _audit_sensitive_text(skill_path, text, findings)
    return {"checked_skill_count": checked}


def _audit_evals(skills_root: Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    eval_path = skills_root / "evals" / "evals.json"
    if not eval_path.exists():
        findings.append(_finding("evals_missing", str(eval_path), "evals.json is missing."))
        return {"skills_with_required_categories": 0}
    payload = json.loads(eval_path.read_text(encoding="utf-8"))
    evals = payload.get("evals") or []
    categories_by_skill: dict[str, set[str]] = {skill: set() for skill in REQUIRED_SKILLS}
    for item in evals:
        if not isinstance(item, dict):
            continue
        skill_name = str(item.get("skill_name") or "")
        category = str(item.get("category") or "")
        if skill_name in categories_by_skill:
            categories_by_skill[skill_name].add(category)
    passed = 0
    for skill_name, categories in sorted(categories_by_skill.items()):
        missing = REQUIRED_EVAL_CATEGORIES - categories
        if missing:
            findings.append(_finding("eval_categories_missing", str(eval_path), f"{skill_name}: {sorted(missing)}"))
        else:
            passed += 1
    return {"skills_with_required_categories": passed}


def _audit_references(skills_root: Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    checked = 0
    long_count = 0
    long_with_toc = 0
    for skill_name in sorted(REQUIRED_SKILLS):
        references_dir = skills_root / skill_name / "references"
        for path in sorted(references_dir.glob("*.md")):
            checked += 1
            text = path.read_text(encoding="utf-8")
            _audit_sensitive_text(path, text, findings)
            line_count = len(text.splitlines())
            if line_count < LONG_REFERENCE_LINE_THRESHOLD:
                continue
            long_count += 1
            if _has_toc(text):
                long_with_toc += 1
            else:
                findings.append(
                    _finding(
                        "long_reference_missing_toc",
                        str(path),
                        f"{line_count} lines; add a Contents/Table of Contents section.",
                    )
                )
    return {
        "checked_reference_count": checked,
        "long_reference_count": long_count,
        "long_references_with_toc": long_with_toc,
        "long_reference_line_threshold": LONG_REFERENCE_LINE_THRESHOLD,
    }


def _has_toc(text: str) -> bool:
    return bool(re.search(r"^## (?:Contents|Table of Contents|Quick Navigation)\s*$", text, flags=re.MULTILINE))


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    metadata: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _audit_reference_targets(skill_dir: Path, skill_path: Path, text: str, findings: list[dict[str, str]]) -> None:
    for match in sorted(set(re.findall(r"`([^`]+\.md)`", text))):
        if match.startswith("http"):
            continue
        if match.startswith("docs/"):
            target = skill_dir.parents[2] / match
        elif match.startswith("../") or match.startswith("references/"):
            target = (skill_dir / match).resolve()
        else:
            continue
        if not target.exists():
            findings.append(_finding("skill_reference_missing", str(skill_path), match))


def _audit_sensitive_text(path: Path, text: str, findings: list[dict[str, str]]) -> None:
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if "..." in match.group(0):
                continue
            findings.append(_finding("sensitive_token_pattern", str(path), pattern.pattern))
            break


def _finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Image Agent skill routing and maintenance contracts.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()
    result = audit_skill_maintenance(args.root)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"status={result['status']}")
        for finding in result["findings"]:
            print(f"{finding['code']}: {finding['path']}: {finding['detail']}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
