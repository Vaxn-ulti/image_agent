import json

from app.workflows.bold_descriptive_review import build_descriptive_review


def test_descriptive_review_writes_summary_and_figure_index(tmp_path):
    output_dir = build_descriptive_review(
        out_dir=tmp_path,
        subject_summaries=[
            {
                "subject_id": "01",
                "metrics": ["alff", "tsnr"],
                "seed_outputs": ["PCC_DMN"],
            }
        ],
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["subject_count"] == 1
    assert "network_difference_descriptive_png" in summary
    assert "motion_qc_overlay_png" in summary
