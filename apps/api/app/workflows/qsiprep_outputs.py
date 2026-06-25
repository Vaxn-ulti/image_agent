from __future__ import annotations

from pathlib import Path


def qsiprep_output_has_anat(task_id: int, *, projects_root: Path) -> bool:
    anat_dir = qsiprep_output_dir(task_id, projects_root=projects_root) / "sub-01" / "anat"
    return anat_dir.exists() and any(anat_dir.iterdir())


def qsiprep_output_dir(task_id: int, *, projects_root: Path) -> Path:
    for project_dir in projects_root.iterdir() if projects_root.exists() else []:
        candidate = project_dir / "derivatives" / str(task_id) / "output"
        if candidate.exists():
            return candidate
    return projects_root / "__missing__" / str(task_id) / "output"
