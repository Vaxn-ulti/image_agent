from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".env",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}

API_KEY_RE = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
FORBIDDEN_PROXY_MARKERS = (
    "liang" + "xin",
    "O" + "wO=",
    "b826" + "ec",
)


def _is_probably_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"README", "Makefile"}


def _iter_git_files(repo_root: Path) -> list[Path]:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [repo_root / line for line in proc.stdout.splitlines() if line.strip()]


def _iter_input_files(paths: Iterable[Path], *, repo_root: Path) -> list[Path]:
    selected = list(paths)
    if not selected:
        selected = _iter_git_files(repo_root)
    files: list[Path] = []
    for raw_path in selected:
        path = Path(raw_path)
        if not path.is_absolute():
            path = repo_root / path
        if path.is_dir():
            for child in path.rglob("*"):
                if any(part in SKIP_DIRS for part in child.parts):
                    continue
                if child.is_file() and _is_probably_text(child):
                    files.append(child)
        elif path.is_file() and _is_probably_text(path):
            files.append(path)
    return sorted({path.resolve() for path in files})


def _safe_relpath(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _is_allowed_secret_fixture(line: str, path: Path) -> bool:
    normalized = path.as_posix()
    if "/tests/" not in normalized and not normalized.endswith("_test.py"):
        return False
    return "secret" in line.lower() or "redacted" in line.lower() or "fixture" in line.lower()


def _scan_file(path: Path, *, repo_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings
    relpath = _safe_relpath(path, repo_root)
    for index, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if any(stripped.startswith(marker) for marker in CONFLICT_MARKERS):
            findings.append({"type": "conflict_marker", "path": relpath, "line": index})
        if any(marker in line for marker in FORBIDDEN_PROXY_MARKERS):
            findings.append({"type": "forbidden_proxy_marker", "path": relpath, "line": index})
        if API_KEY_RE.search(line) and not _is_allowed_secret_fixture(line, path):
            findings.append({"type": "api_key_shaped_secret", "path": relpath, "line": index})
    return findings


def run_hygiene_check(*, paths: Iterable[Path] = (), repo_root: Path | None = None) -> dict:
    root = Path.cwd() if repo_root is None else Path(repo_root)
    files = _iter_input_files(paths, repo_root=root)
    findings: list[dict[str, object]] = []
    for path in files:
        findings.extend(_scan_file(path, repo_root=root))
    report = {
        "status": "passed" if not findings else "failed",
        "checked": {
            "file_count": len(files),
            "finding_count": len(findings),
            "finding_types": sorted({str(item["type"]) for item in findings}),
        },
        "findings": findings,
        "summary": "repository_hygiene_status=passed" if not findings else "repository_hygiene_status=failed",
    }
    if findings:
        kinds = ",".join(report["checked"]["finding_types"])
        raise SystemExit(f"repository hygiene check failed: {kinds}")
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check repository hygiene for release-safe source files")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--paths", nargs="*", default=[], help="Files or directories to scan; defaults to git ls-files")
    parser.add_argument("--output-json", default="", help="Optional JSON report path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    repo_root = Path(args.repo_root).resolve()
    try:
        report = run_hygiene_check(paths=[Path(item) for item in args.paths], repo_root=repo_root)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)
    print(report["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
