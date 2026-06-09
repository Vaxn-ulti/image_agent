import json
from pathlib import Path


for task_id in (41, 111, 114):
    output_dir = Path(f"/home/yyf/project/image_agent/data/projects/13/derivatives/{task_id}/output")
    print(f"TASK:{task_id}")
    reports_dir = output_dir / "reports"
    for path in sorted(reports_dir.glob("*")):
        if path.is_file():
            print(f"  ASSET {path.name} {path.stat().st_size} bytes")
    summary_path = next((output_dir / "summary").glob("*_result_summary.json"))
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    reports = payload.get("outputs", {}).get("reports", [])
    print(f"  reports_in_main_summary={len(reports)}")
    for item in reports:
        print(f"  SUMMARY {item.get('relative_path')} {item.get('content_type')} {item.get('size_bytes')}")
