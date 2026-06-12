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


def _looks_like_backend_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith("/")
        or (len(normalized) >= 3 and normalized[1] == ":" and normalized[0].isalpha() and normalized[2] == "/")
        or "/home/yyf/" in normalized
        or "/project/image_agent/" in normalized
        or "/data/projects/" in normalized
    )


def _assert_no_backend_paths(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _require(key != "log_path", "task evidence must not expose log_path")
            _assert_no_backend_paths(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_backend_paths(item)
        return
    if isinstance(value, str):
        _require(not _looks_like_backend_path(value), "stale-task evidence must not expose backend paths")


def approval_fingerprint(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_approval_payload(payload: dict, *, expected_task_ids: Sequence[int] | None = None) -> dict:
    _require(isinstance(payload, dict), "approval payload must be a JSON object")
    _assert_no_backend_paths(payload)
    _require(payload.get("mode") == "dry_run", "mode must be dry_run")
    _require(payload.get("container_check_status") == "passed", "container_check_status must be passed")
    _require(_as_int_list(payload.get("running_container_task_ids"), key="running_container_task_ids") == [], "running_container_task_ids must be empty")
    _require(_as_int_list(payload.get("blocked_task_ids"), key="blocked_task_ids") == [], "blocked_task_ids must be empty")
    _require(_as_int_list(payload.get("updated_task_ids"), key="updated_task_ids") == [], "updated_task_ids must be empty")
    _require(_as_int_list(payload.get("out_of_scope_stale_task_ids"), key="out_of_scope_stale_task_ids") == [], "out_of_scope_stale_task_ids must be empty")

    target_task_ids = _as_int_list(payload.get("target_task_ids"), key="target_task_ids")
    if expected_task_ids is not None:
        expected = sorted(int(task_id) for task_id in expected_task_ids)
        _require(sorted(target_task_ids) == expected, "target_task_ids must match expected task ids")

    stale_candidates = payload.get("stale_candidates")
    _require(isinstance(stale_candidates, list) and stale_candidates, "stale_candidates must be non-empty")
    stale_candidate_ids = []
    for candidate in stale_candidates:
        _require(isinstance(candidate, dict), "stale_candidates entries must be objects")
        _require("log_path" not in candidate, "stale_candidates must not expose log_path")
        _require(candidate.get("is_stale") is True, "stale_candidates entries must be stale")
        _require(candidate.get("status") in {"queued", "running"}, "stale_candidates entries must be active tasks")
        task_id = candidate.get("id")
        _require(isinstance(task_id, int) and not isinstance(task_id, bool), "stale_candidates id must be an integer")
        stale_candidate_ids.append(task_id)
    _require(sorted(stale_candidate_ids) == sorted(target_task_ids), "stale_candidate ids must match target_task_ids")

    reviewed_payload = payload.get("approval_payload")
    _require(isinstance(reviewed_payload, dict), "approval_payload must be present")
    _require(
        _as_int_list(reviewed_payload.get("target_task_ids"), key="approval_payload.target_task_ids") == target_task_ids,
        "approval_payload.target_task_ids must match target_task_ids",
    )
    _require(
        _as_int_list(reviewed_payload.get("stale_candidate_ids"), key="approval_payload.stale_candidate_ids") == stale_candidate_ids,
        "approval_payload.stale_candidate_ids must match stale_candidates",
    )
    _require(
        _as_int_list(reviewed_payload.get("running_container_task_ids"), key="approval_payload.running_container_task_ids") == [],
        "approval_payload.running_container_task_ids must be empty",
    )
    _require(
        _as_int_list(reviewed_payload.get("blocked_task_ids"), key="approval_payload.blocked_task_ids") == [],
        "approval_payload.blocked_task_ids must be empty",
    )
    _require(reviewed_payload.get("container_check_status") == "passed", "approval_payload.container_check_status must be passed")

    actual_fingerprint = payload.get("approval_fingerprint")
    _require(isinstance(actual_fingerprint, str) and len(actual_fingerprint) == 64, "approval_fingerprint must be a SHA-256 hex string")
    expected_fingerprint = approval_fingerprint(reviewed_payload)
    _require(actual_fingerprint == expected_fingerprint, "approval_fingerprint mismatch")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "target_task_ids": target_task_ids,
            "stale_candidate_ids": stale_candidate_ids,
            "approval_fingerprint": actual_fingerprint,
            "container_check_status": payload["container_check_status"],
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify a reviewed stale-task dry-run approval JSON artifact.")
    parser.add_argument("approval_json", help="Path to JSON written by reconcile_stale_tasks.py dry-run.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", help="Expected target task id. Repeat for multiple ids.")
    args = parser.parse_args(argv)
    source_path = Path(args.approval_json)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    report = verify_approval_payload(payload, expected_task_ids=args.task_ids)
    report["source_json"] = str(source_path)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
