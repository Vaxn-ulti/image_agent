import json
from pathlib import Path

from app.workflows.scientific_reports import build_scientific_report_summary


OUTPUTS = [
    (41, "t1_deepprep", Path("/home/yyf/project/image_agent/data/projects/13/derivatives/41/output/summary/t1_result_summary.json")),
    (111, "bold_second_level", Path("/home/yyf/project/image_agent/data/projects/13/derivatives/111/output/summary/bold_result_summary.json")),
    (114, "dwi_fast_gpu_dti", Path("/home/yyf/project/image_agent/data/projects/13/derivatives/114/output/summary/dwi_result_summary.json")),
]


for task_id, workflow_type, summary_path in OUTPUTS:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.setdefault("summary_path", str(summary_path))
    report_summary = build_scientific_report_summary(summary_path.parents[1], task_id, workflow_type, summary)
    print(f"task={task_id} modality={summary.get('modality')} report_summary={report_summary}")
