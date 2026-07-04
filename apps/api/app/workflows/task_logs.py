from __future__ import annotations

from pathlib import Path

from app.workflows.remote_scripts import classify_bold_fmriprep_xcpd_artifact_stage


_NATIVE_LOG_PATTERNS = (
    "logs/*.log",
    "*.log",
    "QC/**/*.log",
    "Recon/**/*.log",
    "reports/**/*.log",
    "WorkDir/nextflow/*.log",
    "WorkDir/nextflow/.nextflow.log",
)
_MAX_REMOTE_LOGS = 40


def _candidate_log_files(output_path: Path) -> list[Path]:
    candidates: dict[str, Path] = {}
    for pattern in _NATIVE_LOG_PATTERNS:
        try:
            matches = output_path.glob(pattern)
            for log_file in matches:
                if log_file.is_file():
                    candidates[log_file.resolve().as_posix()] = log_file
        except OSError:
            continue
    return [candidates[key] for key in sorted(candidates)[:_MAX_REMOTE_LOGS]]


def collect_remote_task_logs(output_dir: Path | str) -> list[dict]:
    output_path = Path(output_dir)
    remote_logs = []
    if not output_path.exists():
        return remote_logs

    for log_file in _candidate_log_files(output_path):
        try:
            log_text = log_file.read_text(encoding="utf-8", errors="replace")
            size_bytes = log_file.stat().st_size
        except OSError:
            continue
        remote_logs.append(
            {
                "name": log_file.name,
                "path": str(log_file),
                "source_stage": classify_bold_fmriprep_xcpd_artifact_stage(log_file, output_path),
                "size_bytes": size_bytes,
                "tail": log_text[-12000:],
            }
        )
    return remote_logs
