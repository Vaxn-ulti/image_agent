from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path


PLAN_ID = "remote_release_overlay_sync_plan_v1"
DEFAULT_REMOTE_HOST = "yyf@10.2.32.14"
DEFAULT_REMOTE_PROJECT_ROOT = "/home/yyf/project/image_agent"
DEFAULT_REMOTE_RELEASE_ROOT = "/home/yyf/project/image_agent_releases"
RELEASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,80}")
ARCHIVE_PATH_RE = re.compile(r"/tmp/image_agent_release_[A-Za-z0-9_.-]{3,80}\.tar\.gz")
REQUIRED_OVERLAY_FILES = [
    "apps/api/app/scripts/probe_runtime_environment.py",
    "apps/api/scripts/build_stale_task_apply_request.py",
    "apps/api/scripts/verify_stale_task_apply_request.py",
    "apps/api/scripts/build_elasticsearch_hybrid_config_plan.py",
    "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py",
    "apps/api/scripts/setup_elasticsearch_hybrid_rag.py",
    "apps/api/scripts/setup_local_embedding_service.py",
    "apps/api/scripts/verify_elasticsearch_hybrid_prerequisites.py",
    "apps/api/scripts/smoke_remote_agent.py",
    "apps/api/scripts/verify_remote_smoke_acceptance.py",
    "apps/api/scripts/verify_release_gate_command_plan.py",
    "docs/deployment/remote-elasticsearch-hybrid-config-plan.json",
    "docs/rag/contracts/elasticsearch-hybrid-search.md",
    "apps/console/package.json",
    "apps/console/package-lock.json",
    "apps/console/src/lib/api.test.ts",
    "apps/console/src/lib/workflows.test.ts",
    "apps/console/src/routes/AgentPage.test.tsx",
    "apps/console/src/routes/WorkflowsPage.test.tsx",
    "apps/console/src/routes/ResultDetailPage.test.tsx",
    "scripts/check_repository_hygiene.py",
    "scripts/configure_docker_access.py",
    "scripts/run_frontend_contract_tests.py",
    "scripts/verify_rawchat_direct_connectivity.py",
    "tools/restart_remote_image_agent_api.sh",
]
PRIVACY_AND_SAFETY_INVARIANTS = [
    "do_not_copy_dotenv_or_secret_files",
    "do_not_copy_git_or_dependency_caches",
    "do_not_copy_raw_patient_data",
    "do_not_modify_remote_live_tree",
    "do_not_overwrite_existing_release_overlay",
]
EXCLUDED_PATH_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".rag_index",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "node_modules",
}
EXCLUDED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "api.pid",
    "desktop.pid",
}

FRONTEND_API_CONTRACT_TEST_COMMAND = (
    "python scripts/run_frontend_contract_tests.py --console-dir apps/console "
    "src/lib/api.test.ts "
    "src/lib/workflows.test.ts "
    "src/routes/AgentPage.test.tsx "
    "src/routes/WorkflowsPage.test.tsx "
    "src/routes/ResultDetailPage.test.tsx"
)


def _required_release_id(value: str) -> str:
    text = (value or "").strip()
    if not RELEASE_ID_RE.fullmatch(text):
        raise SystemExit("release_id must be a privacy-safe release symbol")
    return text


def _required_archive_path(value: str) -> str:
    text = (value or "").replace("\\", "/").strip()
    if not ARCHIVE_PATH_RE.fullmatch(text):
        raise SystemExit("archive_path must be /tmp/image_agent_release_<release_id>.tar.gz")
    return text


def _is_safe_archive_member(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if not parts or normalized.startswith("/") or ".." in parts:
        return False
    if any(part in EXCLUDED_PATH_PARTS for part in parts):
        return False
    if parts[-1] in EXCLUDED_FILENAMES:
        return False
    if parts[-1].endswith((".pem", ".key", ".p12")):
        return False
    return True


def _git_archive_members(repo_root: Path) -> list[str]:
    output = subprocess.check_output(
        ["git", "-C", str(repo_root), "ls-files", "-co", "--exclude-standard", "-z"],
    )
    paths = output.decode("utf-8").split("\0")
    return sorted(path for path in paths if path and _is_safe_archive_member(path))


def write_current_worktree_archive(*, repo_root: Path, archive_path: Path) -> dict:
    members = _git_archive_members(repo_root)
    member_set = set(members)
    missing_required_files = [path for path in REQUIRED_OVERLAY_FILES if path not in member_set]
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        for member in members:
            archive.add(repo_root / member, arcname=member, recursive=False)
    archive_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return {
        "status": "passed",
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha256,
        "member_count": len(members),
        "excluded_secret_and_runtime_paths": True,
        "required_gate_files_present": not missing_required_files,
        "missing_required_gate_files": missing_required_files,
    }


def _verify_files_command(prefix: str) -> str:
    file_checks = " && ".join(f"test -f {path}" for path in REQUIRED_OVERLAY_FILES)
    return (
        f"cd {prefix} && {file_checks} && "
        'printf "%s\\n" release_overlay_current=true '
        "required_gate_scripts_present=true elasticsearch_hybrid_contract_present=true"
    )


def build_release_overlay_sync_plan(
    *,
    release_id: str,
    archive_path: str,
    remote_host: str = DEFAULT_REMOTE_HOST,
    remote_project_root: str = DEFAULT_REMOTE_PROJECT_ROOT,
    remote_release_root: str = DEFAULT_REMOTE_RELEASE_ROOT,
) -> dict:
    release_id_text = _required_release_id(release_id)
    archive_path_text = _required_archive_path(archive_path)
    release_overlay = f"{remote_release_root}/{release_id_text}"
    incoming_overlay = f"{release_overlay}.incoming"
    remote_archive = f"/tmp/image_agent_release_{release_id_text}.tar.gz"
    build_archive_command = (
        "python apps/api/scripts/build_release_overlay_sync_plan.py "
        f"--write-archive --release-id {release_id_text} --archive-path {archive_path_text}"
    )
    upload_command = f"scp {archive_path_text} {remote_host}:{remote_archive}"
    extract_command = (
        f"ssh {remote_host} "
        f"'set -eu; test ! -e {incoming_overlay}; mkdir -p {incoming_overlay}; "
        f"tar -xzf {remote_archive} -C {incoming_overlay}'"
    )
    promote_command = (
        f"ssh {remote_host} "
        f"'set -eu; test ! -e {release_overlay}; mv {incoming_overlay} {release_overlay}; "
        "printf %s\\\\n release_overlay_promoted=true'"
    )
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "status": "operator_review_required",
        "remote_host": remote_host,
        "remote_project_root": remote_project_root,
        "remote_release_root": remote_release_root,
        "release_id": release_id_text,
        "archive_path": archive_path_text,
        "release_overlay": release_overlay,
        "incoming_release_overlay": incoming_overlay,
        "privacy_and_safety_invariants": PRIVACY_AND_SAFETY_INVARIANTS,
        "steps": [
            {
                "id": "local_preflight",
                "purpose": "Check local diff hygiene and release-gate plan validity before packaging the current worktree.",
                "command": (
                    "git diff --check && "
                    "python scripts/check_repository_hygiene.py "
                    "--paths README.md scripts apps/api/scripts docs/deployment docs/rag docs/skills && "
                    f"{FRONTEND_API_CONTRACT_TEST_COMMAND} && "
                    "printf \"%s\\n\" frontend_api_contract_tests=passed && "
                    "python apps/api/scripts/verify_release_gate_command_plan.py "
                    "docs/deployment/remote-release-gate-command-plan.json"
                ),
                "runs_on": "local",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "git diff --check has no whitespace errors",
                    "repository_hygiene_status=passed",
                    "frontend_api_contract_tests=passed",
                    "release_gate_command_plan status=passed",
                ],
            },
            {
                "id": "build_current_worktree_archive",
                "purpose": "Create a local tar.gz from git tracked files plus unignored untracked files, excluding secret, dependency, cache, and patient-data paths.",
                "command": build_archive_command,
                "runs_on": "local",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "status=passed",
                    "excluded_secret_and_runtime_paths=true",
                    "member_count>0",
                ],
            },
            {
                "id": "upload_archive_to_remote_tmp",
                "purpose": "Upload the reviewed release archive to a temporary path on yyf without touching the live project tree.",
                "command": upload_command,
                "runs_on": "local",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    f"remote_archive={remote_archive}",
                    "live_project_tree_untouched=true",
                ],
            },
            {
                "id": "extract_archive_to_incoming_overlay",
                "purpose": "Extract into a new incoming release overlay only if it does not already exist.",
                "command": extract_command,
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    f"incoming_release_overlay={incoming_overlay}",
                    "existing_incoming_overlay_absent=true",
                    "live_project_tree_untouched=true",
                ],
            },
            {
                "id": "verify_incoming_overlay_contents",
                "purpose": "Verify the incoming overlay contains the current gate scripts and Elasticsearch hybrid contract before promotion.",
                "command": f"ssh {remote_host} '{_verify_files_command(incoming_overlay)}'",
                "runs_on": "remote",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "release_overlay_current=true",
                    "required_gate_scripts_present=true",
                    "elasticsearch_hybrid_contract_present=true",
                ],
            },
            {
                "id": "promote_incoming_overlay",
                "purpose": "Promote the verified incoming overlay to the final release path without overwriting an existing release.",
                "command": promote_command,
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    "release_overlay_promoted=true",
                    "existing_release_overlay_absent=true",
                    "live_project_tree_untouched=true",
                ],
            },
            {
                "id": "verify_promoted_overlay_contents",
                "purpose": "Re-run the same content check against the promoted release overlay before using it in the release gate.",
                "command": f"ssh {remote_host} '{_verify_files_command(release_overlay)}'",
                "runs_on": "remote",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "release_overlay_current=true",
                    "required_gate_scripts_present=true",
                    "elasticsearch_hybrid_contract_present=true",
                ],
            },
        ],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a safe command plan for syncing the current worktree to a remote release overlay.")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--archive-path", required=True)
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-project-root", default=DEFAULT_REMOTE_PROJECT_ROOT)
    parser.add_argument("--remote-release-root", default=DEFAULT_REMOTE_RELEASE_ROOT)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--write-archive", action="store_true")
    args = parser.parse_args(argv)

    if args.write_archive:
        report = write_current_worktree_archive(
            repo_root=Path(__file__).resolve().parents[3],
            archive_path=Path(args.archive_path),
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    plan = build_release_overlay_sync_plan(
        release_id=args.release_id,
        archive_path=args.archive_path,
        remote_host=args.remote_host,
        remote_project_root=args.remote_project_root,
        remote_release_root=args.remote_release_root,
    )
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
