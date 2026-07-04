import json

from app.agent import backend_context


def test_chat_backend_context_adds_workflow_metadata_to_result_summaries(monkeypatch, tmp_path):
    projects_root = tmp_path / "projects"
    summary_dir = projects_root / "7" / "derivatives" / "41" / "output" / "summary"
    summary_dir.mkdir(parents=True)
    summary_path = summary_dir / "t1_result_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 41,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "spaces": ["T1w"],
                "feature_groups": ["quality_control"],
                "outputs": {},
                "provenance": {},
            }
        ),
        encoding="utf-8",
    )

    def fake_fetch_rows(query, params=()):
        if "FROM tasks" in query:
            return [
                {
                    "id": 41,
                    "project_id": 7,
                    "workflow_type": "t1_deepprep",
                    "runtime_workflow_type": "t1_deepprep",
                    "status": "completed",
                    "progress": 100,
                    "error_message": None,
                }
            ]
        return []

    monkeypatch.setattr(backend_context, "fetch_rows", fake_fetch_rows)

    context = backend_context.build_chat_backend_context(
        7,
        "show task 41 result-summary",
        projects_root=projects_root,
        workflows=[],
    )

    summary = context["result_summaries"][0]
    assert summary["workflow_type"] == "t1_deepprep"
    assert summary["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert summary["workflow_metadata"]["runtime_workflow_type"] == "t1_deepprep"
    assert summary["workflow_metadata"]["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert summary["workflow_metadata"]["is_report_only"] is False
    assert "summary_path" not in summary
