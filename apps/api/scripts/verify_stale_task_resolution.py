from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _as_int_list(value: object, *, key: str) -> list[int]:
    _require(isinstance(value, list), f"{key} must be a list")
    result: list[int] = []
    for item in value:
        _require(isinstance(item, int) and not isinstance(item, bool), f"{key} entries must be integers")
        result.append(item)
    return result


def _as_task_list(value: object, *, key: str) -> list[dict]:
    _require(isinstance(value, list), f"{key} must be a list")
    result: list[dict] = []
    for item in value:
        _require(isinstance(item, dict), f"{key} entries must be objects")
        result.append(item)
    return result


def _approval_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _verify_fingerprint(payload: dict) -> str:
    approval_payload = payload.get("approval_payload")
    _require(isinstance(approval_payload, dict), "approval_payload must be present")
    actual = payload.get("approval_fingerprint")
    _require(isinstance(actual, str) and len(actual) == 64, "approval_fingerprint must be a SHA-256 hex string")
    _require(actual == _approval_fingerprint(approval_payload), "approval_fingerprint mismatch")
    return actual


def _expected_task_ids(expected_task_ids: Sequence[int]) -> list[int]:
    return sorted(int(task_id) for task_id in expected_task_ids)


def _task_ids(tasks: list[dict]) -> list[int]:
    ids: list[int] = []
    for task in tasks:
        _require("log_path" not in task, "task evidence must not expose log_path")
        task_id = task.get("id")
        _require(isinstance(task_id, int) and not isinstance(task_id, bool), "task id must be an integer")
        ids.append(task_id)
    return ids


def verify_resolution_evidence(
    apply_payload: dict,
    resolution_payload: dict,
    *,
    expected_task_ids: Sequence[int],
    require_empty_active: bool = False,
) -> dict:
    """Verify stale-task apply evidence plus a follow-up clean dry-run report."""

    expected = _expected_task_ids(expected_task_ids)
    _require(expected, "expected task ids are required")
    _require(isinstance(apply_payload, dict), "apply payload must be a JSON object")
    _require(isinstance(resolution_payload, dict), "resolution payload must be a JSON object")

    apply_fingerprint = _verify_fingerprint(apply_payload)
    _require(apply_payload.get("mode") == "apply", "apply mode must be apply")
    _require(apply_payload.get("container_check_status") == "passed", "apply container_check_status must be passed")
    _require(_as_int_list(apply_payload.get("running_container_task_ids"), key="apply.running_container_task_ids") == [], "apply running_container_task_ids must be empty")
    _require(_as_int_list(apply_payload.get("blocked_task_ids"), key="apply.blocked_task_ids") == [], "apply blocked_task_ids must be empty")
    _require(_as_int_list(apply_payload.get("out_of_scope_stale_task_ids"), key="apply.out_of_scope_stale_task_ids") == [], "apply out_of_scope_stale_task_ids must be empty")
    apply_targets = sorted(_as_int_list(apply_payload.get("target_task_ids"), key="apply.target_task_ids"))
    _require(apply_targets == expected, "apply target_task_ids must match expected task ids")
    updated_task_ids = sorted(_as_int_list(apply_payload.get("updated_task_ids"), key="apply.updated_task_ids"))
    _require(updated_task_ids == expected, "updated_task_ids must match expected task ids")
    apply_candidates = _as_task_list(apply_payload.get("stale_candidates"), key="apply.stale_candidates")
    _require(sorted(_task_ids(apply_candidates)) == expected, "apply stale_candidates must match expected task ids")
    for candidate in apply_candidates:
        _require(candidate.get("is_stale") is True, "apply stale_candidates entries must be stale")
        _require(candidate.get("status") in {"queued", "running"}, "apply stale_candidates entries must be active tasks")

    resolution_fingerprint = _verify_fingerprint(resolution_payload)
    _require(resolution_payload.get("mode") == "dry_run", "resolution mode must be dry_run")
    _require(resolution_payload.get("container_check_status") == "passed", "resolution container_check_status must be passed")
    _require(_as_int_list(resolution_payload.get("running_container_task_ids"), key="resolution.running_container_task_ids") == [], "resolution running_container_task_ids must be empty")
    _require(_as_int_list(resolution_payload.get("blocked_task_ids"), key="resolution.blocked_task_ids") == [], "resolution blocked_task_ids must be empty")
    _require(_as_int_list(resolution_payload.get("updated_task_ids"), key="resolution.updated_task_ids") == [], "resolution updated_task_ids must be empty")
    _require(_as_int_list(resolution_payload.get("out_of_scope_stale_task_ids"), key="resolution.out_of_scope_stale_task_ids") == [], "resolution out_of_scope_stale_task_ids must be empty")
    resolution_targets = sorted(_as_int_list(resolution_payload.get("target_task_ids"), key="resolution.target_task_ids"))
    _require(resolution_targets == expected, "resolution target_task_ids must match expected task ids")

    resolution_candidates = _as_task_list(resolution_payload.get("stale_candidates"), key="resolution.stale_candidates")
    _require(resolution_candidates == [], "resolved dry-run stale_candidates must be empty")
    active_tasks = _as_task_list(resolution_payload.get("active_tasks"), key="resolution.active_tasks")
    active_target_ids = sorted(task_id for task_id in _task_ids(active_tasks) if task_id in expected)
    _require(active_target_ids == [], "resolved dry-run must not include target task ids as active")
    if require_empty_active:
        _require(resolution_payload.get("active_task_count") == 0, "resolved dry-run active_task_count must be 0")
        _require(active_tasks == [], "resolved dry-run active_tasks must be empty")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "target_task_ids": expected,
            "updated_task_ids": updated_task_ids,
            "resolved_task_ids": expected,
            "apply_approval_fingerprint": apply_fingerprint,
            "resolution_approval_fingerprint": resolution_fingerprint,
            "require_empty_active": require_empty_active,
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify stale-task apply evidence and a clean follow-up dry-run JSON artifact.")
    parser.add_argument("--apply-json", required=True, help="Path to JSON written by reconcile_stale_tasks.py --apply.")
    parser.add_argument("--resolution-json", required=True, help="Path to follow-up dry-run JSON written after the apply.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", required=True, help="Expected reconciled task id. Repeat for multiple ids.")
    parser.add_argument("--require-empty-active", action="store_true", help="Require the follow-up dry-run to report no active tasks at all.")
    args = parser.parse_args(argv)

    apply_path = Path(args.apply_json)
    resolution_path = Path(args.resolution_json)
    apply_payload = json.loads(apply_path.read_text(encoding="utf-8"))
    resolution_payload = json.loads(resolution_path.read_text(encoding="utf-8"))
    report = verify_resolution_evidence(
        apply_payload,
        resolution_payload,
        expected_task_ids=args.task_ids,
        require_empty_active=args.require_empty_active,
    )
    report["source_json"] = {
        "apply": str(apply_path),
        "resolution": str(resolution_path),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
