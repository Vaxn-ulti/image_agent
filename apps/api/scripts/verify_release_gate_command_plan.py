from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path


PLAN_ID = "remote_release_gate_after_stale_task_approval_v1"
API_KEY_SHAPED_RE = re.compile(r"sk-[A-Za-z0-9_-]{10,}")
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
CURRENT_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"

EXPECTED_STEP_IDS = [
    "verify_fresh_stale_task_approval",
    "apply_approved_stale_task_resolution",
    "collect_post_apply_clean_dry_run",
    "verify_post_apply_clean_resolution",
    "restart_api_preflight_only",
    "restart_api_normally",
    "run_strict_remote_smoke_acceptance",
    "verify_strict_remote_smoke_acceptance_json",
]

REQUIRED_PRIVACY_AND_SAFETY_INVARIANTS = [
    "do_not_store_or_print_api_keys_or_secrets",
    "do_not_store_raw_patient_data",
    "do_not_store_backend_absolute_paths_in_acceptance_json",
    "do_not_use_IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
    "do_not_count_skipped_missing_model_config_as_passed",
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_plan(path: str | Path) -> dict:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "command plan must be a JSON object")
    return payload


def _require_command_contains(command: str, needle: str, *, step_id: str) -> None:
    _require(needle in command, f"{step_id}.command must include {needle}")


def _verify_step_shape(step: object, *, expected_id: str, index: int) -> dict:
    _require(isinstance(step, dict), f"steps[{index}] must be an object")
    _require(step.get("id") == expected_id, f"steps[{index}].id must be {expected_id}")
    command = step.get("command")
    _require(isinstance(command, str) and command.strip(), f"{expected_id}.command must be non-empty")
    _require("\n" not in command, f"{expected_id}.command must be single-line")
    _require("OPENAI_API_KEY" not in command, f"{expected_id}.command must not mention OPENAI_API_KEY")
    _require(
        API_KEY_SHAPED_RE.search(command) is None,
        f"{expected_id}.command must not contain API-key shaped strings",
    )
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command,
        f"{expected_id}.command must not use active-task restart override",
    )
    _require(isinstance(step.get("mutates_remote_state"), bool), f"{expected_id}.mutates_remote_state must be boolean")
    _require(
        isinstance(step.get("requires_operator_authorization"), bool),
        f"{expected_id}.requires_operator_authorization must be boolean",
    )
    expected_success = step.get("expected_success")
    _require(isinstance(expected_success, list) and expected_success, f"{expected_id}.expected_success must be non-empty")
    _require(all(isinstance(item, str) and item for item in expected_success), f"{expected_id}.expected_success entries must be strings")
    return step


def _verify_approval_refresh(plan: dict) -> dict:
    refresh = plan.get("stale_task_approval_refresh")
    _require(isinstance(refresh, dict), "stale_task_approval_refresh must be present")
    _require(
        refresh.get("required_when") == "approval_json_missing_or_older_than_24h",
        "stale_task_approval_refresh.required_when mismatch",
    )
    _require(
        refresh.get("must_be_operator_reviewed_before_apply") is True,
        "stale_task_approval_refresh must require operator review before apply",
    )
    _require(
        refresh.get("mutates_remote_state") is False,
        "stale_task_approval_refresh must be read-only",
    )
    _require(
        refresh.get("output_json_pattern") == "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json",
        "stale_task_approval_refresh.output_json_pattern mismatch",
    )
    command = refresh.get("command")
    _require(isinstance(command, str) and command.strip(), "stale_task_approval_refresh.command must be non-empty")
    _require("\n" not in command, "stale_task_approval_refresh.command must be single-line")
    _require("--apply" not in command, "stale_task_approval_refresh.command must not apply")
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command,
        "stale_task_approval_refresh.command must not use active-task restart override",
    )
    _require(
        API_KEY_SHAPED_RE.search(command) is None and "OPENAI_API_KEY" not in command,
        "stale_task_approval_refresh.command must not expose secrets",
    )
    for required in (
        REMOTE_ENV_LOAD_SNIPPET,
        "reconcile_stale_tasks.py --max-age-hours 24 --check-containers",
        "--task-id 83 --task-id 84",
        "> /tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json",
    ):
        _require(required in command, f"stale_task_approval_refresh.command must include {required}")
    _require(
        refresh.get("next_steps_after_refresh")
        == [
            "operator reviews refreshed dry-run JSON and approval_fingerprint",
            "set approval_json to the refreshed dry-run JSON path",
            "rerun verify_fresh_stale_task_approval before apply",
        ],
        "stale_task_approval_refresh.next_steps_after_refresh mismatch",
    )
    return refresh


def verify_plan(plan: dict) -> dict:
    _require(plan.get("plan_id") == PLAN_ID, f"plan_id must be {PLAN_ID}")
    _require(plan.get("schema_version") == 1, "schema_version must be 1")
    _require(plan.get("status") == "operator_authorization_required", "status must require operator authorization")
    _require(plan.get("remote_host") == "yyf@10.2.32.14", "remote_host must identify the accepted remote server")
    _require(plan.get("remote_project_root") == "/home/yyf/project/image_agent", "remote_project_root mismatch")
    _require(
        plan.get("release_overlay") == "/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132",
        "release_overlay must point at the prepared remote verifier overlay",
    )
    _require(
        plan.get("approval_json") == CURRENT_APPROVAL_JSON,
        "approval_json must point at the reviewed fresh dry-run evidence",
    )
    _require(plan.get("target_task_ids") == [83, 84], "target_task_ids must be [83, 84]")
    _require(plan.get("freshness_hours") == 24, "freshness_hours must be 24")
    _require(
        plan.get("approval_request_requirements")
        == {
            "must_include_fields": [
                "approval_fingerprint",
                "approval_expires_at_utc",
            ],
            "approval_expires_at_utc_source": "verified_approval.checked.generated_at_utc + freshness_hours",
        },
        "approval_request_requirements mismatch",
    )
    _require(
        plan.get("privacy_and_safety_invariants") == REQUIRED_PRIVACY_AND_SAFETY_INVARIANTS,
        "privacy_and_safety_invariants mismatch",
    )
    _require(
        plan.get("frontend_gate")
        == {
            "status_until_all_steps_pass": "blocked",
            "required_final_evidence": "fresh_strict_remote_smoke_acceptance_verified_within_24h",
        },
        "frontend_gate mismatch",
    )
    refresh = _verify_approval_refresh(plan)

    steps = plan.get("steps")
    _require(isinstance(steps, list), "steps must be a list")
    _require(len(steps) == len(EXPECTED_STEP_IDS), "steps must contain the expected release gate sequence")
    verified_steps = [
        _verify_step_shape(step, expected_id=expected_id, index=index)
        for index, (step, expected_id) in enumerate(zip(steps, EXPECTED_STEP_IDS, strict=True))
    ]
    commands_by_step = {step["id"]: step["command"] for step in verified_steps}

    _require_command_contains(
        commands_by_step["verify_fresh_stale_task_approval"],
        f"verify_stale_task_approval.py {CURRENT_APPROVAL_JSON} --task-id 83 --task-id 84 --max-age-hours 24",
        step_id="verify_fresh_stale_task_approval",
    )
    _require_command_contains(
        commands_by_step["apply_approved_stale_task_resolution"],
        f"reconcile_stale_tasks.py --apply --max-age-hours 24 --task-id 83 --task-id 84 --approval-json {CURRENT_APPROVAL_JSON}",
        step_id="apply_approved_stale_task_resolution",
    )
    _require_command_contains(
        commands_by_step["apply_approved_stale_task_resolution"],
        REMOTE_ENV_LOAD_SNIPPET,
        step_id="apply_approved_stale_task_resolution",
    )
    _require_command_contains(
        commands_by_step["collect_post_apply_clean_dry_run"],
        "reconcile_stale_tasks.py --max-age-hours 24 --check-containers --task-id 83 --task-id 84",
        step_id="collect_post_apply_clean_dry_run",
    )
    _require_command_contains(
        commands_by_step["collect_post_apply_clean_dry_run"],
        REMOTE_ENV_LOAD_SNIPPET,
        step_id="collect_post_apply_clean_dry_run",
    )
    _require_command_contains(
        commands_by_step["verify_post_apply_clean_resolution"],
        "verify_stale_task_resolution.py --apply-json /tmp/image_agent_stale_tasks_83_84_apply_<timestamp>.json --resolution-json /tmp/image_agent_stale_tasks_83_84_resolved_dry_run_<timestamp>.json --task-id 83 --task-id 84 --require-empty-active --max-age-hours 24",
        step_id="verify_post_apply_clean_resolution",
    )
    _require_command_contains(
        commands_by_step["restart_api_preflight_only"],
        "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1",
        step_id="restart_api_preflight_only",
    )
    _require_command_contains(
        commands_by_step["restart_api_preflight_only"],
        "bash tools/restart_remote_image_agent_api.sh",
        step_id="restart_api_preflight_only",
    )
    _require_command_contains(
        commands_by_step["restart_api_normally"],
        "bash tools/restart_remote_image_agent_api.sh",
        step_id="restart_api_normally",
    )
    _require(
        "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" not in commands_by_step["restart_api_normally"],
        "restart_api_normally must not run in preflight-only mode",
    )
    for required_flag in (
        "--require-model",
        "--require-deployment-identity",
        "--require-raw-source-policy",
        "--require-vendor-pointer-integrity",
        "--require-real-evidence-ids",
        "--require-launchability-matrix",
        "--require-container-native-qc",
        "--min-native-qc-images 1",
        "--require-scientific-report-artifacts",
        "--min-scientific-report-images 1",
        "--project-id <project_id>",
        "--upload-session-id <upload_session_id>",
        "--task-id <completed_task_id>",
        "--output-json",
    ):
        _require_command_contains(
            commands_by_step["run_strict_remote_smoke_acceptance"],
            required_flag,
            step_id="run_strict_remote_smoke_acceptance",
        )
    _require_command_contains(
        commands_by_step["verify_strict_remote_smoke_acceptance_json"],
        "verify_remote_smoke_acceptance.py",
        step_id="verify_strict_remote_smoke_acceptance_json",
    )
    _require_command_contains(
        commands_by_step["verify_strict_remote_smoke_acceptance_json"],
        "--max-age-hours 24",
        step_id="verify_strict_remote_smoke_acceptance_json",
    )

    mutating_steps = [step["id"] for step in verified_steps if step["mutates_remote_state"]]
    operator_steps = [step["id"] for step in verified_steps if step["requires_operator_authorization"]]
    _require(
        operator_steps == ["apply_approved_stale_task_resolution"],
        "only stale-task apply may require operator authorization in this plan",
    )
    _require(
        mutating_steps == ["apply_approved_stale_task_resolution", "restart_api_normally"],
        "only stale-task apply and normal restart may mutate remote state",
    )

    serialized = json.dumps(plan, sort_keys=True)
    _require("approval_fingerprint" in serialized, "plan must preserve approval_fingerprint evidence requirement")
    _require("approval_expires_at_utc" in serialized, "plan must preserve approval_expires_at_utc evidence requirement")
    _require("restart_preflight:ok" in serialized, "plan must require restart_preflight:ok")
    _require("skipped_missing_model_config" in serialized, "plan must reject skipped_missing_model_config")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "plan_id": plan["plan_id"],
            "step_count": len(verified_steps),
            "target_task_ids": plan["target_task_ids"],
            "freshness_hours": plan["freshness_hours"],
            "approval_request_required_fields": plan["approval_request_requirements"]["must_include_fields"],
            "operator_authorization_required_steps": operator_steps,
            "mutating_steps": mutating_steps,
            "frontend_gate_status": plan["frontend_gate"]["status_until_all_steps_pass"],
            "approval_refresh_required_when": refresh["required_when"],
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify the remote release gate command plan JSON.")
    parser.add_argument("plan_json", help="Path to docs/deployment/remote-release-gate-command-plan.json")
    args = parser.parse_args(argv)
    plan = load_plan(args.plan_json)
    report = verify_plan(plan)
    report["source_json"] = str(Path(args.plan_json))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
