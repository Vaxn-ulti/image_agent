from __future__ import annotations

from pathlib import Path

from app.workflows.remote_scripts import classify_bold_fmriprep_xcpd_artifact_stage


def collect_remote_task_logs(output_dir: Path | str) -> list[dict]:
    output_path = Path(output_dir)
    output_log_dir = output_path / "logs"
    remote_logs = []
    if not output_log_dir.exists():
        return remote_logs

    for log_file in sorted(output_log_dir.glob("*.log")):
        try:
            log_text = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        remote_logs.append(
            {
                "name": log_file.name,
                "path": str(log_file),
                "source_stage": classify_bold_fmriprep_xcpd_artifact_stage(log_file, output_path),
                "size_bytes": log_file.stat().st_size,
                "tail": log_text[-12000:],
            }
        )
    return remote_logs
