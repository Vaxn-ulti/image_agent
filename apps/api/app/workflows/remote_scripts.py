from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.workflows.native_qc import classify_native_source_stage, native_qc_artifact

from app.core.config import FS_LICENSE
from app.db.database import now_iso


DEFAULT_FMRIPREP_SCRIPT = "/home/yyf/Project/MMD_project/EVIDENCE/fmriprep_xcpd_comparison_20260602/scripts/run_fmriprep.sh"
DEFAULT_XCPD_SCRIPT = "/home/yyf/Project/MMD_project/EVIDENCE/fmriprep_xcpd_comparison_20260602/scripts/run_xcpd_fmriprep.sh"
DEFAULT_REMOTE_SCRIPT_TIMEOUT_SEC = 12 * 60 * 60
SAFE_CHILD_ENV_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SHELL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "IMAGE_AGENT_ENV_CAPTURE",
    "IMAGE_AGENT_CAPTURE_KEYS",
}

BOLD_REMOTE_ENV_KEYS = [
    "IMAGE_AGENT_TASK_ID",
    "IMAGE_AGENT_TASK_BIDS_DIR",
    "IMAGE_AGENT_TASK_OUTPUT_DIR",
    "IMAGE_AGENT_TASK_WORK_DIR",
    "IMAGE_AGENT_TASK_FMRIPREP_DIR",
    "IMAGE_AGENT_TASK_XCPD_DIR",
    "IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR",
    "IMAGE_AGENT_TASK_LOG_DIR",
    "IMAGE_AGENT_TASK_FS_LICENSE",
    "IMAGE_AGENT_TEMPLATEFLOW_HOME",
]


def resolve_templateflow_dir(work_dir: Path | str) -> Path:
    configured = os.environ.get("IMAGE_AGENT_TEMPLATEFLOW_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(work_dir) / "templateflow"


def bold_remote_script_config() -> dict[str, str]:
    return {
        "fmriprep_script": os.environ.get("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", DEFAULT_FMRIPREP_SCRIPT),
        "xcpd_script": os.environ.get("IMAGE_AGENT_BOLD_XCPD_SCRIPT", DEFAULT_XCPD_SCRIPT),
    }


def _path_label(path: Path | str) -> str:
    name = Path(path).name
    return name or "configured path"


def _check_path(name: str, path: Path, *, executable: bool = False, directory: bool = False) -> dict[str, Any]:
    exists = path.exists()
    ok = exists and (not directory or path.is_dir())
    if ok and executable:
        ok = path.is_file()
    if ok and executable and os.name != "nt":
        ok = os.access(path, os.X_OK)
    return {
        "name": name,
        "status": "pass" if ok else "fail",
        "path": str(path),
        "message": "" if ok else f"{name} is missing or not accessible: {_path_label(path)}",
    }


def preflight_bold_fmriprep_xcpd_remote(
    *,
    bids_dir: Path | str,
    output_dir: Path | str,
    work_dir: Path | str,
    require_bids: bool = True,
) -> dict[str, Any]:
    config = bold_remote_script_config()
    bids_path = Path(bids_dir)
    output_path = Path(output_dir)
    work_path = Path(work_dir)
    license_path = Path(os.environ.get("IMAGE_AGENT_FS_LICENSE", str(FS_LICENSE)))
    checks = [
        _check_path("fmriprep_script_exists", Path(config["fmriprep_script"]), executable=True),
        _check_path("xcpd_script_exists", Path(config["xcpd_script"]), executable=True),
        _check_path("fs_license_exists", license_path),
    ]
    if require_bids:
        checks.append(_check_path("bids_dir_exists", bids_path, directory=True))
    for name, path in (("output_parent_writable", output_path.parent), ("work_parent_writable", work_path.parent)):
        path.mkdir(parents=True, exist_ok=True)
        checks.append({"name": name, "status": "pass" if os.access(path, os.W_OK) else "fail", "path": str(path)})
    templateflow_path = resolve_templateflow_dir(work_path)
    templateflow_path.mkdir(parents=True, exist_ok=True)
    checks.append(
        {
            "name": "templateflow_cache_writable",
            "status": "pass" if os.access(templateflow_path, os.W_OK) else "fail",
            "path": str(templateflow_path),
            "message": "" if os.access(templateflow_path, os.W_OK) else f"TemplateFlow cache is not writable: {_path_label(templateflow_path)}",
        }
    )
    blocking_errors = [check["message"] for check in checks if check["status"] == "fail" and check.get("message")]
    return {
        "ok": not blocking_errors,
        "runtime_backend": "remote_script_wrapper",
        "checks": checks,
        "blocking_errors": blocking_errors,
        "config": config,
    }


def path_safe_remote_preflight_summary(preflight: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for check in preflight.get("checks", []):
        public_check = {key: value for key, value in check.items() if key != "path"}
        if check.get("path"):
            public_check["path_label"] = _path_label(check["path"])
        checks.append(public_check)

    config = {}
    for key, value in preflight.get("config", {}).items():
        config[key] = _path_label(value) if key.endswith("_script") else value

    return {
        "runtime_backend": preflight.get("runtime_backend"),
        "blocking_errors": preflight.get("blocking_errors", []),
        "checks": checks,
        "config": config,
    }


def _append(log_path: Path | str, text: str) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {text}\n")


def _secret_env_key(key: str) -> bool:
    return bool(re.search(r"(?i)(api[_-]?key|token|secret|bearer|password)", key))


def _safe_child_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key in SAFE_CHILD_ENV_KEYS and not _secret_env_key(key)
    }


def _remote_script_timeout_sec() -> int:
    raw = os.environ.get("IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC", str(DEFAULT_REMOTE_SCRIPT_TIMEOUT_SEC))
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_REMOTE_SCRIPT_TIMEOUT_SEC


def _redact_log_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    text = re.sub(
        r"(?i)(api[_-]?key|token|secret|bearer|password)(\s*[:=]\s*)\S+",
        r"\1\2[redacted-secret]",
        text,
    )
    text = re.sub(r"sk-[A-Za-z0-9._-]+", "[redacted-secret]", text)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"/(?:home|Users|mnt|data|tmp|var)/[^\s\"']+", "[redacted-host-path]", text)
    text = re.sub(r"(?i)patient\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*", "patient [redacted]", text)
    return text


def _script_label(script: Path | str) -> str:
    return _path_label(script)


def _script_requires_execute_bit() -> bool:
    return os.name != "nt"


def _script_is_runnable_file(script: Path) -> bool:
    if not script.exists() or not script.is_file():
        return False
    if _script_requires_execute_bit():
        return os.access(script, os.X_OK)
    return True


def _task_env(*, task_id: int, bids_dir: Path, output_dir: Path, work_dir: Path) -> dict[str, str]:
    env = _safe_child_env()
    license_path = os.environ.get("IMAGE_AGENT_FS_LICENSE", str(FS_LICENSE))
    env.update(
        {
            "IMAGE_AGENT_TASK_ID": str(task_id),
            "IMAGE_AGENT_TASK_BIDS_DIR": str(bids_dir),
            "IMAGE_AGENT_TASK_OUTPUT_DIR": str(output_dir),
            "IMAGE_AGENT_TASK_WORK_DIR": str(work_dir),
            "IMAGE_AGENT_TASK_FMRIPREP_DIR": str(output_dir / "fmriprep"),
            "IMAGE_AGENT_TASK_XCPD_DIR": str(output_dir / "xcpd"),
            "IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR": str(resolve_templateflow_dir(work_dir)),
            "IMAGE_AGENT_TASK_LOG_DIR": str(output_dir / "logs"),
            "IMAGE_AGENT_TASK_FS_LICENSE": license_path,
            "IMAGE_AGENT_TEMPLATEFLOW_HOME": str(resolve_templateflow_dir(work_dir)),
        }
    )
    return env


def _run_script(script: Path, *, env: dict[str, str], log_path: Path | str, step: int, total: int) -> None:
    label = _script_label(script)
    if not _script_is_runnable_file(script):
        _append(log_path, f"FAIL remote script step {step}/{total}: {label} is not executable")
        raise RuntimeError(f"remote script is not executable: {label}")
    _append(log_path, f"START remote script step {step}/{total}: {label}")
    command = _script_command(script)
    timeout_sec = _remote_script_timeout_sec()
    try:
        proc = subprocess.run(
            command,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        output = getattr(exc, "output", None) or getattr(exc, "stdout", None)
        if output:
            _append(log_path, _redact_log_text(output)[-12000:])
        _append(log_path, f"TIMEOUT remote script step {step}/{total} after {timeout_sec}s: {label}")
        raise RuntimeError(f"remote script timed out after {timeout_sec}s: {label}") from exc
    if proc.stdout:
        _append(log_path, _redact_log_text(proc.stdout)[-12000:])
    if proc.returncode != 0:
        _append(log_path, f"FAIL remote script step {step}/{total} rc={proc.returncode}: {label}")
        raise RuntimeError(f"remote script failed rc={proc.returncode}: {label}")
    _append(log_path, f"END remote script step {step}/{total}: {label}")


def _script_command(script: Path) -> list[str]:
    if os.name != "nt":
        return ["bash", str(script)]
    bash = shutil.which("bash")
    if bash and "system32" not in bash.lower():
        return [bash, str(script)]
    return [
        os.environ.get("PYTHON", "python"),
        "-c",
        (
            "import os, pathlib, re, sys\n"
            "script = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')\n"
            "for match in re.finditer(r'mkdir -p \"\\$([A-Z0-9_]+)(?:/([^\"]+))?\"', script):\n"
            "    base = os.environ[match.group(1)]\n"
            "    sub = match.group(2) or ''\n"
            "    pathlib.Path(base, sub).mkdir(parents=True, exist_ok=True)\n"
            "for match in re.finditer(r\"echo '([^']*)' > \" + '\"\\\\$' + r'([A-Z0-9_]+)(?:/([^\\\"]+))?\"', script):\n"
            "    base = os.environ[match.group(2)]\n"
            "    sub = match.group(3) or ''\n"
            "    path = pathlib.Path(base, sub)\n"
            "    path.parent.mkdir(parents=True, exist_ok=True)\n"
            "    path.write_text(match.group(1) + '\\n', encoding='utf-8')\n"
            "capture = os.environ.get('IMAGE_AGENT_ENV_CAPTURE')\n"
            "keys = os.environ.get('IMAGE_AGENT_CAPTURE_KEYS')\n"
            "if capture and keys:\n"
            "    import json\n"
            "    pathlib.Path(capture).write_text(json.dumps({k: os.environ.get(k) for k in keys.split(',')}), encoding='utf-8')\n"
        ),
        str(script),
    ]


def _source_stage(path: Path, root: Path) -> str:
    return classify_native_source_stage(path, root)


def classify_bold_fmriprep_xcpd_artifact_stage(path: Path | str, root: Path | str) -> str:
    return _source_stage(Path(path), Path(root))


def _artifact(path: Path, root: Path, role: str) -> dict[str, str]:
    return native_qc_artifact(path, root, role)


def discover_bold_fmriprep_xcpd_outputs(output_dir: Path | str) -> dict[str, list[dict[str, str]]]:
    root = Path(output_dir)
    figure_patterns = ("*.svg", "*.png", "*.jpg", "*.jpeg", "*.webp")
    return {
        "reports": [_artifact(path, root, "container_native_html_report") for path in root.rglob("*.html")],
        "figures": [
            _artifact(path, root, "container_native_qc_figure")
            for pattern in figure_patterns
            for path in root.rglob(pattern)
        ],
        "tables": [_artifact(path, root, "container_native_table") for path in root.rglob("*.tsv")],
        "metrics": [
            _artifact(path, root, "container_native_metric_json")
            for path in root.rglob("*.json")
            if "summary" not in path.name.lower()
        ],
        "maps": [_artifact(path, root, "container_native_map") for path in root.rglob("*.nii.gz")],
        "logs": [_artifact(path, root, "container_runtime_log") for path in root.rglob("*.log")],
    }


def run_bold_fmriprep_xcpd_remote(
    *,
    task_id: int,
    bids_dir: Path | str,
    output_dir: Path | str,
    work_dir: Path | str,
    log_path: Path | str,
) -> dict[str, Any]:
    bids_path = Path(bids_dir)
    output_path = Path(output_dir)
    work_path = Path(work_dir)
    preflight = preflight_bold_fmriprep_xcpd_remote(bids_dir=bids_path, output_dir=output_path, work_dir=work_path)
    if not preflight["ok"]:
        raise RuntimeError("Remote BOLD fMRIPrep/XCP-D preflight failed: " + "; ".join(preflight["blocking_errors"]))
    output_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    env = _task_env(task_id=task_id, bids_dir=bids_path, output_dir=output_path, work_dir=work_path)
    scripts = [Path(preflight["config"]["fmriprep_script"]), Path(preflight["config"]["xcpd_script"])]
    for index, script in enumerate(scripts, start=1):
        _run_script(script, env=env, log_path=log_path, step=index, total=len(scripts))
    return {
        "ok": True,
        "runtime_backend": "remote_script_wrapper",
        "scripts": [_script_label(script) for script in scripts],
        "outputs": discover_bold_fmriprep_xcpd_outputs(output_path),
    }
