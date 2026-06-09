import json
from pathlib import Path

from app.workflows.scientific_reports import build_scientific_report_summary


TASKS = [
    (41, "t1_deepprep"),
    (111, "bold_second_level"),
    (114, "dwi_fast_gpu_dti"),
]


root = Path("/home/yyf/project/image_agent")
for task_id, workflow_type in TASKS:
    out_dir = root / "data" / "projects" / "13" / "derivatives" / str(task_id) / "output"
    summary_candidates = sorted((out_dir / "summary").glob("*_result_summary.json"))
    if not summary_candidates:
        raise SystemExit(f"missing result summary for task {task_id}: {out_dir}")
    summary_path = summary_candidates[0]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report_path = build_scientific_report_summary(
        out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        summary=summary,
    )
    print(f"task {task_id}: {report_path}")
