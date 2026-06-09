from __future__ import annotations

import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_ROOT = REPO_ROOT / "docs" / "skills"

SKILL_NAMES = {
    "operator": "image-agent-operator",
    "architect": "image-agent-architect",
    "workflow": "image-agent-workflow-runner",
    "result": "image-agent-result-reviewer",
    "rag": "image-agent-rag-curator",
}


def select_skill(message: str, decision: dict[str, Any] | None = None) -> str:
    decision = decision or {}
    intent = str(decision.get("intent") or "").lower()
    lane = str(decision.get("action_lane") or decision.get("lane") or "").lower()
    text = message.lower()
    if lane == "toolchain_incubation" or intent in {"curate_rag", "rag_curate"}:
        return SKILL_NAMES["rag"] if intent in {"curate_rag", "rag_curate"} else SKILL_NAMES["workflow"]
    if intent == "run_workflow" or any(token in text for token in ("workflow", "preflight", "run ", "launch", "fmriprep", "xcp-d", "xcpd", "deepprep")):
        return SKILL_NAMES["workflow"]
    if intent in {"inspect_result", "review_result", "summarize_result"} or any(token in text for token in ("result", "summary", "report", "artifact", "metric", "explain")):
        return SKILL_NAMES["result"]
    if intent in {"architect", "architecture", "develop"} or any(token in text for token in ("architecture", "langgraph", "sdk", "backend", "frontend", "架构")):
        return SKILL_NAMES["architect"]
    if any(token in text for token in ("rag", "knowledge", "source", "vendor doc", "知识库")):
        return SKILL_NAMES["rag"]
    return SKILL_NAMES["operator"]


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, text[end + 4 :].lstrip()


def _declared_reference_names(body: str) -> set[str]:
    names = set(re.findall(r"`references/([^`]+)`", body))
    names.update(re.findall(r"references/([A-Za-z0-9_.-]+\.md)", body))
    return names


def load_skill_context(skill_name: str, *, skills_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(skills_root or SKILLS_ROOT)
    skill_dir = root / skill_name
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name}")
    raw = skill_path.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(raw)
    declared = _declared_reference_names(body)
    reference_paths = sorted((skill_dir / "references").glob("*.md")) if (skill_dir / "references").exists() else []
    if declared:
        reference_paths = [path for path in reference_paths if path.name in declared]
    references = [
        {
            "path": str(path.relative_to(root.parent.parent)),
            "name": path.name,
            "content": path.read_text(encoding="utf-8"),
        }
        for path in reference_paths
    ]
    return {
        "name": metadata.get("name") or skill_name,
        "description": metadata.get("description", ""),
        "skill_path": str(skill_path),
        "body": body,
        "references": references,
    }


def load_selected_skill(message: str, decision: dict[str, Any] | None = None) -> dict[str, Any]:
    return load_skill_context(select_skill(message, decision))
