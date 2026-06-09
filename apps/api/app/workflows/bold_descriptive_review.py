from __future__ import annotations

import json
from pathlib import Path


def build_descriptive_review(out_dir: Path, subject_summaries: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "network_fc_difference_descriptive.png").write_bytes(b"placeholder-png")
    (out_dir / "motion_qc_overlay.png").write_bytes(b"placeholder-png")
    summary = {
        "subject_count": len(subject_summaries),
        "subjects": subject_summaries,
        "network_difference_descriptive_png": str(out_dir / "network_fc_difference_descriptive.png"),
        "motion_qc_overlay_png": str(out_dir / "motion_qc_overlay.png"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_dir
