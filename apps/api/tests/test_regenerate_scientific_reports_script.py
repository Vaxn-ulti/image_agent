import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("apps/api/scripts/regenerate_scientific_reports.py")


def test_regenerate_scientific_reports_cli_preserves_native_reports(tmp_path):
    output_dir = tmp_path / "output"
    summary_path = output_dir / "summary" / "bold_result_summary.json"
    native_report = output_dir / "fmriprep" / "sub-01.html"
    native_report.parent.mkdir(parents=True)
    summary_path.parent.mkdir(parents=True)
    native_report.write_text("<html>native</html>", encoding="utf-8")
    summary_path.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "task_id": 118,
                "workflow_type": "bold_fmriprep_xcpd_report",
                "modality": "BOLD",
                "spaces": ["MNI152"],
                "feature_groups": ["preprocessing", "reports"],
                "outputs": {
                    "reports": [
                        {
                            "name": "sub-01.html",
                            "path": str(native_report),
                            "relative_path": "fmriprep/sub-01.html",
                            "content_type": "text/html",
                            "native_artifact": True,
                            "source_stage": "fmriprep",
                            "artifact_role": "container_native_html_report",
                        }
                    ]
                },
                "provenance": {},
                "summary_path": str(summary_path),
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(output_dir), "--json"],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["results"][0]["task_id"] == 118
    assert payload["results"][0]["native_report_count"] == 1
    assert "reports/index.html" in payload["results"][0]["report_relative_paths"]

    refreshed = json.loads(summary_path.read_text(encoding="utf-8"))
    reports = {item["relative_path"]: item for item in refreshed["outputs"]["reports"]}
    assert reports["fmriprep/sub-01.html"]["native_artifact"] is True
    assert reports["reports/index.html"]["source_stage"] == "scientific_report"
    assert (output_dir / "reports" / "report_manifest.json").exists()
