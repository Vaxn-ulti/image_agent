from __future__ import annotations

from pathlib import Path


def validate_group_inputs(group_a: list[str], group_b: list[str]) -> None:
    if len(group_a) < 2 or len(group_b) < 2:
        raise ValueError("Group analysis requires at least 2 completed subjects per group")


def build_group_review_scaffold(out_dir: Path) -> Path:
    voxel_dir = out_dir / "voxelwise"
    voxel_dir.mkdir(parents=True, exist_ok=True)
    (voxel_dir / "alff_mean_difference_stat.png").write_bytes(b"placeholder-png")
    (voxel_dir / "alff_mean_difference_glass.png").write_bytes(b"placeholder-png")
    (voxel_dir / "alff_mean_difference_peaks.tsv").write_text("x\ty\tz\tstat\n", encoding="utf-8")
    return out_dir
