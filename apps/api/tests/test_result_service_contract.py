from app.services.result_service import _public_result_summary


def test_public_result_summary_uses_stable_task_workflow_type_over_legacy_payload():
    task = {
        "id": 120,
        "project_id": 13,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "status": "completed",
    }
    payload = {
        "contract_version": "1.0",
        "workflow_type": "t1_deepprep",
        "runtime_workflow_type": None,
        "summary_path": "/tmp/private/result_summary.json",
        "outputs": {
            "reports": [
                {
                    "name": "index.html",
                    "path": "/home/yyf/project/image_agent/data/projects/13/derivatives/120/output/reports/index.html",
                    "relative_path": "reports/index.html",
                }
            ]
        },
        "provenance": {
            "source_stats_dir": "/home/yyf/project/image_agent/data/projects/13/derivatives/120/output/Recon/sub-01/stats",
            "stats_files": [
                {
                    "name": "brainvol.stats",
                    "path": "/home/yyf/project/image_agent/data/projects/13/derivatives/120/output/Recon/sub-01/stats/brainvol.stats",
                }
            ],
        },
    }

    public = _public_result_summary(task, payload)

    assert public["workflow_type"] == "t1_deepprep_anat_report"
    assert public["runtime_workflow_type"] == "t1_deepprep"
    assert public["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert public["workflow_metadata"]["runtime_workflow_type"] == "t1_deepprep"
    assert "summary_path" not in public
    assert "path" not in public["outputs"]["reports"][0]
    assert public["outputs"]["reports"][0]["relative_path"] == "reports/index.html"
    assert "path" not in public["provenance"]["stats_files"][0]
    assert public["provenance"]["source_stats_dir"] == "[redacted-host-path]"


def test_public_result_summary_does_not_redact_bids_task_label_as_secret():
    task = {
        "id": 135,
        "project_id": 24,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "runtime_workflow_type": "bold_fmriprep_xcpd_report",
        "status": "completed",
    }
    payload = {
        "contract_version": "1.0",
        "workflow_type": "bold_fmriprep_xcpd_report",
        "outputs": {
            "reports": [
                {
                    "name": "sub-01_task-rest_desc-summary_bold.html",
                    "relative_path": "fmriprep/sub-01/figures/sub-01_task-rest_desc-summary_bold.html",
                    "download_url": "/tasks/135/artifacts/fmriprep/sub-01/figures/sub-01_task-rest_desc-summary_bold.html",
                    "content_type": "text/html",
                }
            ]
        },
        "provenance": {
            "error": "OPENAI_API_KEY=sk-real-secret-token",
        },
    }

    public = _public_result_summary(task, payload)
    item = public["outputs"]["reports"][0]

    assert item["name"] == "sub-01_task-rest_desc-summary_bold.html"
    assert item["relative_path"] == "fmriprep/sub-01/figures/sub-01_task-rest_desc-summary_bold.html"
    assert item["download_url"] == "/tasks/135/artifacts/fmriprep/sub-01/figures/sub-01_task-rest_desc-summary_bold.html"
    assert public["provenance"]["error"] == "OPENAI_API_KEY=[redacted-secret]"
