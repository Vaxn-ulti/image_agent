"""Safe container recovery for image_agent orphaned containers.

An API restart or port conflict does not stop Docker containers launched by the
API.  This module reconciles living containers with database task state without
touching unrelated containers or running workflows.

Safety rules enforced here:
- Only operate on containers that carry the ``image_agent.app=image_agent`` label.
- Only touch containers whose project directory exists under PROJECTS_ROOT.
- Never stop, kill, or restart a container.
- Only recover tasks whose container exited successfully (rc=0) and whose output
  directory contains files.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.core.config import PROJECTS_ROOT
from app.db.database import connect, now_iso
from app.workflows.docker_command import docker_command_prefix, docker_stdin_for_prefix

APP_LABEL_FILTER = "image_agent.app=image_agent"

# ── helpers ──────────────────────────────────────────────────────────────────


def _sudo_docker_prefix():
    prefix = docker_command_prefix(default=["sudo", "-S", "docker"])
    return prefix, docker_stdin_for_prefix(prefix, purpose="docker commands")


def _docker(args, timeout=30):
    prefix, input_text = _sudo_docker_prefix()
    proc = subprocess.run(
        prefix + args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return proc


# ── container listing ────────────────────────────────────────────────────────


def list_image_agent_containers():
    """Return list of dicts for every container launched by image_agent."""
    proc = _docker([
        "ps", "-a",
        "--filter", f"label={APP_LABEL_FILTER}",
        "--format",
        "{{.ID}}\t{{.Label \"image_agent.task_id\"}}\t{{.Label \"image_agent.project_id\"}}"
        "\t{{.Label \"image_agent.workflow_type\"}}\t{{.State}}\t{{.Status}}\t{{.Image}}",
    ])
    if proc.returncode != 0:
        return []
    containers = []
    for line in proc.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        containers.append({
            "container_id": parts[0],
            "task_id": parts[1],
            "project_id": parts[2],
            "workflow_type": parts[3],
            "state": parts[4],
            "status": parts[5],
            "image": parts[6],
        })
    return containers


def container_inspect(container_id):
    """Return parsed ``docker inspect`` dict for *container_id*."""
    proc = _docker(["inspect", container_id], timeout=15)
    if proc.returncode != 0:
        return None
    data = json.loads(proc.stdout)
    return data[0] if data else None


# ── safety predicates ────────────────────────────────────────────────────────


def _project_dir_exists(project_id):
    if not project_id:
        return False
    try:
        pid = int(project_id)
    except (ValueError, TypeError):
        return False
    return (PROJECTS_ROOT / str(pid)).is_dir()


def _container_in_project_tree(inspect_data):
    """True if at least one bind mount source is under PROJECTS_ROOT and every outside mount is read-only."""
    mounts = inspect_data.get("Mounts", [])
    if not mounts:
        return False
    projects_root = PROJECTS_ROOT.resolve()
    has_project_mount = False
    for m in mounts:
        src = m.get("Source", "")
        if not src:
            continue
        if Path(src).resolve().is_relative_to(projects_root):
            has_project_mount = True
            continue
        if m.get("RW", True):
            return False
    return has_project_mount


def _output_has_files(project_id, task_id):
    output_dir = PROJECTS_ROOT / str(project_id) / "derivatives" / str(task_id) / "output"
    if not output_dir.is_dir():
        return False
    return any(output_dir.iterdir())


def _task_in_db(task_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return dict(row) if row else None


# ── recovery actions ─────────────────────────────────────────────────────────


def dry_run_report():
    """Return a safe summary of image_agent containers and their DB state."""
    report = {"containers": [], "recoverable": [], "warnings": []}
    containers = list_image_agent_containers()
    for c in containers:
        entry = dict(c)
        task_id_raw = c["task_id"]
        project_id_raw = c["project_id"]

        entry["db_task"] = None
        entry["recoverable"] = False
        entry["safety_checks"] = []

        if not task_id_raw or not project_id_raw:
            entry["safety_checks"].append("missing labels (task_id or project_id)")
            report["containers"].append(entry)
            continue

        try:
            task_id = int(task_id_raw)
        except (ValueError, TypeError):
            entry["safety_checks"].append("task_id label is not an integer")
            report["containers"].append(entry)
            continue

        # DB check
        db_task = _task_in_db(task_id)
        entry["db_task"] = db_task
        if db_task is None:
            entry["safety_checks"].append("no DB task row")
        elif db_task["status"] == "completed":
            entry["safety_checks"].append("DB already completed")

        # Project dir check
        if not _project_dir_exists(project_id_raw):
            entry["safety_checks"].append("project dir missing under PROJECTS_ROOT")

        # Container state
        if c["state"] != "exited":
            entry["safety_checks"].append(f"container state is {c['state']}, not exited")

        # Check if recoverable: container exited 0, DB says running, output has files
        if (
            c["state"] == "exited"
            and db_task is not None
            and db_task["status"] in ("running", "queued")
            and _project_dir_exists(project_id_raw)
            and _output_has_files(project_id_raw, task_id)
        ):
            # Check exit code by inspecting container
            inspect_data = container_inspect(c["container_id"])
            if inspect_data is not None:
                exit_code = inspect_data.get("State", {}).get("ExitCode", -1)
                if exit_code == 0:
                    if _container_in_project_tree(inspect_data):
                        entry["recoverable"] = True
                        report["recoverable"].append(entry)
                    else:
                        entry["safety_checks"].append("container mounts outside PROJECTS_ROOT")
                else:
                    entry["safety_checks"].append(f"container exit code {exit_code} != 0")

        report["containers"].append(entry)
    return report


def recover_task(task_id):
    """Recover a single orphaned task whose container completed successfully.

    Returns (recovered: bool, message: str).
    """
    task_id = int(task_id)
    containers = list_image_agent_containers()
    matched = [c for c in containers if c["task_id"] == str(task_id)]

    if not matched:
        return False, f"No image_agent container found for task {task_id}"

    c = matched[0]
    if c["state"] != "exited":
        return False, f"Container for task {task_id} is {c['state']}, not exited"

    project_id = c["project_id"]
    if not _project_dir_exists(project_id):
        return False, f"Project directory for project {project_id} does not exist under PROJECTS_ROOT"

    db_task = _task_in_db(task_id)
    if db_task is None:
        return False, f"Task {task_id} not found in database"
    if db_task["status"] not in ("running", "queued"):
        return False, f"Task {task_id} has status {db_task['status']}; only running/queued tasks can be recovered"

    inspect_data = container_inspect(c["container_id"])
    if inspect_data is None:
        return False, f"Could not inspect container {c['container_id']}"

    exit_code = inspect_data.get("State", {}).get("ExitCode", -1)
    if exit_code != 0:
        return False, f"Container exited with code {exit_code}, not recoverable"

    if not _container_in_project_tree(inspect_data):
        return False, "Container has mounts outside PROJECTS_ROOT; refusing to recover"

    if not _output_has_files(project_id, task_id):
        return False, "Output directory is empty or missing; cannot confirm successful completion"

    # Register outputs and mark completed
    from app.workflows.pipeline import _register_outputs, _append

    output_dir = PROJECTS_ROOT / str(project_id) / "derivatives" / str(task_id) / "output"
    log_path = db_task.get("log_path", str(PROJECTS_ROOT / str(project_id) / "logs" / f"{task_id}.log"))
    _append(log_path, f"Orphan recovery: container {c['container_id']} exited 0, registering outputs from {output_dir}")
    count = _register_outputs(task_id, output_dir)
    _append(log_path, f"Orphan recovery: registered {count} outputs")

    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status='completed', progress=100, finished_at=? WHERE id=?",
            (now_iso(), task_id),
        )

    return True, f"Recovered task {task_id}: registered {count} outputs, marked completed"


def recover_all():
    """Recover all eligible orphaned tasks. Returns list of (task_id, recovered, message)."""
    report = dry_run_report()
    results = []
    for entry in report.get("recoverable", []):
        tid = int(entry["task_id"])
        ok, msg = recover_task(tid)
        results.append((tid, ok, msg))
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m app.workflows.recovery <list|dry-run|recover TASK_ID|recover-all>", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]

    if action == "list":
        for c in list_image_agent_containers():
            print(json.dumps(c, default=str))
    elif action == "dry-run":
        report = dry_run_report()
        print(f"Total containers: {len(report['containers'])}")
        print(f"Recoverable: {len(report['recoverable'])}")
        for entry in report["recoverable"]:
            print(f"  task {entry['task_id']} container {entry['container_id']} ({entry['workflow_type']})")
        for c in report["containers"]:
            if c["safety_checks"]:
                print(f"  task {c.get('task_id','?')} container {c['container_id']}: {c['safety_checks']}")
    elif action == "recover":
        if len(sys.argv) < 3:
            print("usage: python -m app.workflows.recovery recover TASK_ID", file=sys.stderr)
            sys.exit(1)
        ok, msg = recover_task(int(sys.argv[2]))
        print(f"{'OK' if ok else 'SKIP'}: {msg}")
    elif action == "recover-all":
        results = recover_all()
        for tid, ok, msg in results:
            print(f"{'OK' if ok else 'SKIP'} task {tid}: {msg}")
        if not results:
            print("No recoverable tasks found.")
    else:
        print(f"Unknown action: {action}", file=sys.stderr)
        sys.exit(1)
