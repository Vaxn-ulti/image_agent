from __future__ import annotations

import argparse
import gzip
import json
import mimetypes
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


API_ROOT = Path(__file__).resolve().parents[1]
RUN_SERVER_SCRIPT = API_ROOT / "scripts" / "run_isolated_api_server.py"
DEFAULT_PROJECT_NAME = "isolated-upload-agent-smoke"
DEFAULT_AGENT_MESSAGE = "替我分析一下现在的数据"
DEFAULT_REQUIRED_FRAGMENTS = ["项目状态概览", "任务 #", "只读观察"]
DEFAULT_FORBIDDEN_FRAGMENTS = ["Tasks:", "Model gateway is not configured"]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an isolated live upload-to-Agent smoke.")
    parser.add_argument("--root", type=Path, help="Isolated Image Agent root. Defaults to a temporary root.")
    parser.add_argument("--port", type=int, default=0, help="API port. Use 0 to pick a free port.")
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--agent-message", default=DEFAULT_AGENT_MESSAGE)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--required-answer-fragment", action="append")
    parser.add_argument("--forbidden-answer-fragment", action="append")
    return parser.parse_args(argv)


def _request_json(method: str, url: str, payload: dict | None = None) -> dict | list:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {url} failed: HTTP {exc.code} {body}") from exc


def _upload_nifti(base: str, project_id: int, upload_path: Path) -> dict:
    boundary = f"imageagent{uuid4().hex}"
    filename = upload_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/gzip"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + upload_path.read_bytes() + footer
    req = urllib.request.Request(
        f"{base}/projects/{project_id}/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"POST /projects/{project_id}/upload failed: HTTP {exc.code} {body_text}") from exc


def _write_minimal_nifti(path: Path) -> None:
    header = bytearray(348)
    struct.pack_into("<i", header, 0, 348)
    struct.pack_into("<8h", header, 40, 3, 64, 64, 32, 1, 1, 1, 1)
    struct.pack_into("<h", header, 70, 16)
    struct.pack_into("<h", header, 72, 32)
    struct.pack_into("<8f", header, 76, 0.0, 1.0, 1.0, 1.2, 1.0, 0.0, 0.0, 0.0)
    header[344:348] = b"n+1\0"
    with gzip.open(path, "wb") as handle:
        handle.write(bytes(header))


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _isolated_api_server(root: Path, port: int) -> Iterator[object]:
    effective_port = port if port > 0 else _find_free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            str(RUN_SERVER_SCRIPT),
            "--root",
            str(root),
            "--port",
            str(effective_port),
        ],
        cwd=str(API_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    server = type("IsolatedApiServer", (), {"base_url": f"http://127.0.0.1:{effective_port}"})()
    try:
        _wait_for_health(server.base_url, process)
        yield server
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _wait_for_health(base_url: str, process: subprocess.Popen, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise SystemExit(f"isolated API server exited early with code {process.returncode}: {stderr[-1200:]}")
        try:
            health = _request_json("GET", f"{base_url}/health")
            if isinstance(health, dict) and health.get("status") == "ok":
                return
        except Exception as exc:  # noqa: BLE001 - startup polling needs the last error only.
            last_error = str(exc)
        time.sleep(0.25)
    raise SystemExit(f"isolated API server did not become healthy: {last_error}")


def _seed_running_t1_task(root: Path, project_id: int, series_id: int) -> dict:
    db_path = root / "data" / "app.db"
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tasks(
              id, project_id, series_id, workflow_type, runtime_workflow_type,
              status, progress, log_path, error_message, created_at, started_at, finished_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                9001,
                project_id,
                series_id,
                "t1_deepprep_anat_report",
                "t1_deepprep_anat_report",
                "running",
                35,
                "logs/task-9001.log",
                None,
                now,
                now,
                None,
            ),
        )
    return {
        "task_id": 9001,
        "project_id": project_id,
        "series_id": series_id,
        "workflow_type": "t1_deepprep_anat_report",
        "status": "running",
        "progress": 35,
    }


def _safe_series(series: dict) -> dict:
    return {
        "project_id": int(series["project_id"]),
        "series_id": int(series["id"]),
        "modality": str(series.get("modality") or ""),
        "sequence_label": str(series.get("sequence_label") or ""),
        "status": str(series.get("status") or ""),
    }


def _safe_agent_run(agent_run: dict) -> dict:
    safe: dict = {}
    for key in ("status", "intent", "action_lane", "selected_skill", "response_source"):
        value = agent_run.get(key)
        if isinstance(value, str) and value and len(value) <= 160:
            safe[key] = value
    return safe


def _validate_answer(answer: str, required_fragments: list[str], forbidden_fragments: list[str]) -> dict:
    missing = [fragment for fragment in required_fragments if fragment not in answer]
    forbidden = [fragment for fragment in forbidden_fragments if fragment in answer]
    if missing:
        raise SystemExit(f"agent answer missing required fragments: {missing}")
    if forbidden:
        raise SystemExit(f"agent answer included forbidden fragments: {forbidden}")
    return {
        "required_fragments": required_fragments,
        "forbidden_fragments_absent": forbidden_fragments,
        "answer_excerpt": answer[:320],
    }


def _write_payload(payload: dict, output_json: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def _run(root: Path, args: argparse.Namespace) -> dict:
    required_fragments = args.required_answer_fragment or list(DEFAULT_REQUIRED_FRAGMENTS)
    forbidden_fragments = args.forbidden_answer_fragment or list(DEFAULT_FORBIDDEN_FRAGMENTS)
    payload: dict = {
        "status": "started",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_scope": "isolated",
        "project_name": args.project_name,
        "agent_message": args.agent_message,
    }
    with _isolated_api_server(root, args.port) as server:
        base = server.base_url.rstrip("/")
        health = _request_json("GET", f"{base}/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise SystemExit("/health did not report ok")
        payload["health_status"] = "passed"

        projects = _request_json("GET", f"{base}/projects")
        if projects != []:
            raise SystemExit("isolated smoke expected an empty project list before creating test data")
        payload["initial_projects_status"] = "passed_empty"

        project = _request_json("POST", f"{base}/projects", {"name": args.project_name, "description": ""})
        if not isinstance(project, dict) or not isinstance(project.get("id"), int):
            raise SystemExit("project creation did not return a project id")
        project_id = int(project["id"])
        payload["project"] = {"project_id": project_id}

        with tempfile.TemporaryDirectory(prefix="image-agent-upload-agent-smoke-") as temp_dir:
            upload_path = Path(temp_dir) / "sub-isolated-smoke_T1w.nii.gz"
            _write_minimal_nifti(upload_path)
            upload = _upload_nifti(base, project_id, upload_path)
        if not isinstance(upload, dict) or not isinstance(upload.get("series"), dict):
            raise SystemExit("upload did not create an imaging series")
        uploaded_series = _safe_series(upload["series"])
        payload["upload_status"] = "passed"
        payload["uploaded_series"] = uploaded_series

        seed_task = _seed_running_t1_task(root, project_id, uploaded_series["series_id"])
        payload["seed_task_status"] = "passed"
        payload["seed_task"] = seed_task

        agent_run = _request_json("POST", f"{base}/agent/runs", {"project_id": project_id, "message": args.agent_message})
        if not isinstance(agent_run, dict):
            raise SystemExit("agent run response must be an object")
        answer = str(agent_run.get("answer") or "")
        if agent_run.get("status") != "answered" or not answer:
            raise SystemExit(f"agent did not return an answered response: {agent_run.get('status')}")
        answer_evidence = _validate_answer(answer, required_fragments, forbidden_fragments)
        payload["agent_interaction_status"] = "passed"
        payload["agent_run"] = _safe_agent_run(agent_run)
        payload["agent_answer_required_fragments"] = answer_evidence["required_fragments"]
        payload["agent_answer_forbidden_fragments_absent"] = answer_evidence["forbidden_fragments_absent"]
        payload["agent_answer_excerpt"] = answer_evidence["answer_excerpt"]
        payload["status"] = "passed"
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.root is not None:
        root = args.root.resolve()
        payload = _run(root, args)
        _write_payload(payload, args.output_json)
        return
    with tempfile.TemporaryDirectory(prefix="image-agent-isolated-upload-agent-") as temp_dir:
        payload = _run(Path(temp_dir), args)
        _write_payload(payload, args.output_json)


if __name__ == "__main__":
    main()
