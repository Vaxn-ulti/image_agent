import json
import time
from pathlib import Path

from app.core.config import PROJECTS_ROOT
from app.db.database import connect, now_iso
from app.workflows.t1_results import write_t1_result_summary


def _append(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {text}\n")


def _task_project_root(project_id: int, log_path: Path) -> Path:
    if log_path.parent.name == "logs":
        return log_path.parent.parent
    return PROJECTS_ROOT / str(project_id)


def run_mock_deepprep(task_id: int) -> None:
    with connect() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task is None:
            return
        project_id = task["project_id"]
        log_path = Path(task["log_path"])
        derivative_dir = _task_project_root(project_id, log_path) / "derivatives" / str(task_id)
        out_dir = derivative_dir / "output"
        conn.execute("UPDATE tasks SET status='running', progress=10, started_at=? WHERE id=?", (now_iso(), task_id))
    try:
        _append(log_path, "Mock DeepPrep started")
        out_dir.mkdir(parents=True, exist_ok=True)
        for progress, step in [(25, "validating T1 input"), (50, "running anatomical preprocessing"), (75, "generating segmentation outputs")]:
            time.sleep(0.3)
            _append(log_path, step)
            with connect() as conn:
                conn.execute("UPDATE tasks SET progress=? WHERE id=?", (progress, task_id))
        outputs = {
            "qc_report": out_dir / "qc_report.html",
            "segmentation": out_dir / "segmentation_summary.txt",
            "chart": out_dir / "volume_chart.json",
        }
        outputs["qc_report"].write_text("<html><body><h1>Mock DeepPrep QC</h1><p>Status: completed</p></body></html>\n", encoding="utf-8")
        outputs["segmentation"].write_text("Mock segmentation output for MVP validation.\n", encoding="utf-8")
        outputs["chart"].write_text(json.dumps({"labels": ["GM", "WM", "CSF"], "values": [620, 510, 180]}, indent=2), encoding="utf-8")
        summary_path = write_t1_result_summary(out_dir, task_id=task_id, workflow_type="t1_deepprep_mock")
        with connect() as conn:
            for output_type, path in outputs.items():
                metadata = {
                    "relative_path": path.relative_to(out_dir).as_posix(),
                    "content_type": "text/html" if path.suffix == ".html" else "application/json" if path.suffix == ".json" else "text/plain",
                }
                conn.execute(
                    "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
                    (task_id, output_type, str(path), None, json.dumps(metadata), now_iso()),
                )
            conn.execute(
                "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
                (task_id, "json", str(summary_path), None, json.dumps({"kind": "result_summary", "modality": "T1"}), now_iso()),
            )
            conn.execute("UPDATE tasks SET status='completed', progress=100, finished_at=? WHERE id=?", (now_iso(), task_id))
        _append(log_path, "Mock DeepPrep completed")
    except Exception as exc:
        _append(log_path, f"FAILED: {exc}")
        with connect() as conn:
            conn.execute("UPDATE tasks SET status='failed', error_message=?, finished_at=? WHERE id=?", (str(exc), now_iso(), task_id))
