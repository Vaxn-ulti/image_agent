from app.workflows.bold_result_contract import build_run_summary, build_seed_record


def test_build_run_summary_has_stable_sections():
    summary = build_run_summary(
        subject_id="01",
        task_label="rest",
        metrics=["alff", "falff"],
        seed_records=[build_seed_record("PCC_DMN", [0, -52, 26], 6, "DMN")],
        provenance={"source": "unit-test"},
    )

    assert summary["subject_id"] == "01"
    assert summary["task_label"] == "rest"
    assert summary["metrics"] == ["alff", "falff"]
    assert summary["seeds"][0]["preset_id"] == "PCC_DMN"
    assert "provenance" in summary
    assert "outputs" in summary
