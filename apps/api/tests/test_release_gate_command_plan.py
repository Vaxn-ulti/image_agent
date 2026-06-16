import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = REPO_ROOT / "docs" / "deployment" / "remote-release-gate-command-plan.json"
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_release_gate_command_plan.py"
FRESH_APPROVAL_JSON = "<fresh_reviewed_approval_json>"
EXPIRED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"
REVIEWED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_release_gate_command_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operator_authorization_plan() -> dict:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["status"] = "operator_authorization_required"
    plan["approval_json"] = REVIEWED_APPROVAL_JSON
    plan["approval_json_state"] = {
        "status": "fresh_reviewed",
        "previous_approval_json": EXPIRED_APPROVAL_JSON,
        "verified_approval_generated_at_utc": "2026-06-16T01:00:00+00:00",
        "approval_expires_at_utc": "2026-06-17T01:00:00+00:00",
        "next_required_step": "apply_approved_stale_task_resolution",
    }
    for step in plan["steps"]:
        step["command"] = step["command"].replace(FRESH_APPROVAL_JSON, REVIEWED_APPROVAL_JSON)
        step["expected_success"] = [
            item.replace(FRESH_APPROVAL_JSON, REVIEWED_APPROVAL_JSON)
            for item in step["expected_success"]
        ]
    return plan


def test_remote_release_gate_command_plan_is_machine_checkable():
    verifier = load_verifier()
    plan = verifier.load_plan(PLAN_PATH)
    report = verifier.verify_plan(plan)

    assert report["status"] == "passed"
    assert report["checked"]["plan_id"] == "remote_release_gate_after_stale_task_approval_v1"
    assert report["checked"]["step_count"] == 9
    assert report["checked"]["operator_authorization_required_steps"] == [
        "apply_approved_stale_task_resolution"
    ]
    assert report["checked"]["mutating_steps"] == [
        "apply_approved_stale_task_resolution",
        "restart_api_normally",
        "run_strict_remote_smoke_acceptance",
    ]
    assert report["checked"]["approval_request_required_fields"] == [
        "approval_fingerprint",
        "approval_expires_at_utc",
    ]
    assert report["checked"]["approval_json_status"] == "refresh_required"
    assert plan["approval_request_requirements"] == {
        "must_include_fields": [
            "approval_fingerprint",
            "approval_expires_at_utc",
        ],
        "approval_expires_at_utc_source": "verified_approval.checked.generated_at_utc + freshness_hours",
    }


def test_remote_release_gate_command_plan_orders_safe_remote_acceptance_steps():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step_ids = [step["id"] for step in plan["steps"]]

    assert step_ids == [
        "verify_fresh_stale_task_approval",
        "apply_approved_stale_task_resolution",
        "collect_post_apply_clean_dry_run",
        "verify_post_apply_clean_resolution",
        "restart_api_preflight_only",
        "restart_api_normally",
        "run_strict_remote_smoke_acceptance",
        "verify_strict_remote_smoke_acceptance_json",
        "emit_fast_launch_acceptance_env_after_strict_verify",
    ]

    commands = "\n".join(step["command"] for step in plan["steps"])
    assert plan["status"] == "approval_refresh_required"
    assert plan["approval_json"] == FRESH_APPROVAL_JSON
    assert plan["approval_json_state"]["previous_approval_json"] == EXPIRED_APPROVAL_JSON
    assert f"--approval-json {FRESH_APPROVAL_JSON}" in commands
    assert EXPIRED_APPROVAL_JSON not in commands
    assert "approval_fingerprint" in json.dumps(plan, sort_keys=True)
    assert "approval_expires_at_utc" in json.dumps(plan, sort_keys=True)
    assert "--check-containers --task-id 83 --task-id 84" in commands
    assert "--require-empty-active --max-age-hours 24" in commands
    assert "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands
    assert "restart_preflight:ok" in json.dumps(plan, sort_keys=True)
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in commands
    assert "--require-model" in commands
    assert "--expected-model-wire-api responses" in commands
    assert "--expected-model-provider-profile rawchat" in commands
    assert "--require-model-tool-loop" in commands
    assert "--require-project-agent-context" in commands
    assert "--require-agent-workflow-confirmation" in commands
    assert "--require-real-evidence-ids" in commands
    assert "--require-completed-upload" in commands
    assert "--require-uploaded-series" in commands
    assert "--upload-nifti-file <remote_nifti_file>" in commands
    assert "--require-completed-task" in commands
    assert "--require-launched-task" in commands
    assert "--launch-series-id <uploaded_series_id>" not in commands
    assert "--launch-workflow-type <real_registered_workflow_type>" in commands
    assert "--wait-task-completion-timeout-seconds 21600" in commands
    assert "--wait-task-completion-poll-seconds 30" in commands
    assert "--expected-health-version <expected_health_version>" in commands
    assert "--require-container-native-qc" in commands
    assert "--require-scientific-report-artifacts" in commands
    assert "verify_remote_smoke_acceptance.py" in commands
    assert "--emit-fast-launch-env" in commands
    assert "<project_id>" in commands
    assert "<upload_session_id>" in commands
    assert "<completed_task_id>" not in commands
    assert "task_status_status=passed" in json.dumps(plan, sort_keys=True)
    assert "model_status.wire_api=responses" in json.dumps(plan, sort_keys=True)
    assert "checked.model_wire_api=responses" in json.dumps(plan, sort_keys=True)
    assert "checked.model_provider_profile=rawchat" in json.dumps(plan, sort_keys=True)
    assert "checked.model_tool_loop=true" in json.dumps(plan, sort_keys=True)
    assert "uploaded_series_status=passed" in json.dumps(plan, sort_keys=True)
    assert "launched_task_status=passed" in json.dumps(plan, sort_keys=True)
    assert "task_workflow_selection_status=passed" in json.dumps(plan, sort_keys=True)
    assert "agent_project_context_status=passed" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_confirmation_status=passed" in json.dumps(plan, sort_keys=True)
    assert "upload_inventory_completion_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.task_status_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.launched_task_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.task_workflow_selection_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_project_context_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_confirmation_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.upload_inventory_completion_status=passed" in json.dumps(plan, sort_keys=True)


def test_remote_release_gate_command_plan_does_not_apply_expired_approval_json():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["status"] = "operator_authorization_required"
    plan["approval_json"] = EXPIRED_APPROVAL_JSON
    plan.pop("approval_json_state", None)
    for step in plan["steps"]:
        step["command"] = step["command"].replace(FRESH_APPROVAL_JSON, EXPIRED_APPROVAL_JSON)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "approval_json_state must describe the approval JSON state" in str(exc.value)


def test_remote_release_gate_command_plan_accepts_fresh_reviewed_approval_after_refresh():
    verifier = load_verifier()
    plan = _operator_authorization_plan()

    report = verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")

    assert report["status"] == "passed"
    assert report["checked"]["approval_json_status"] == "fresh_reviewed"
    assert report["checked"]["approval_json"] == REVIEWED_APPROVAL_JSON
    assert report["checked"]["approval_expires_at_utc"] == "2026-06-17T01:00:00+00:00"


def test_remote_release_gate_command_plan_rejects_expired_reviewed_approval_after_refresh():
    verifier = load_verifier()
    plan = _operator_authorization_plan()

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan, now_utc="2026-06-17T02:00:00Z")

    assert "approval_json_state.approval_expires_at_utc is older than now_utc" in str(exc.value)


def test_remote_release_gate_command_plan_declares_frontend_blocking_invariants():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    assert plan["frontend_gate"] == {
        "status_until_all_steps_pass": "blocked",
        "required_final_evidence": "fresh_strict_remote_smoke_acceptance_verified_within_24h",
    }
    assert plan["privacy_and_safety_invariants"] == [
        "do_not_store_or_print_api_keys_or_secrets",
        "do_not_store_raw_patient_data",
        "do_not_store_backend_absolute_paths_in_acceptance_json",
        "do_not_use_IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
        "do_not_count_skipped_missing_model_config_as_passed",
    ]


def test_remote_release_gate_command_plan_includes_approval_refresh_path():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    refresh = plan["stale_task_approval_refresh"]

    assert refresh["required_when"] == "approval_json_missing_or_older_than_24h"
    assert refresh["must_be_operator_reviewed_before_apply"] is True
    assert refresh["mutates_remote_state"] is False
    assert refresh["output_json_pattern"] == "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json"

    command = refresh["command"]
    assert "reconcile_stale_tasks.py --max-age-hours 24 --check-containers" in command
    assert "--task-id 83 --task-id 84" in command
    assert "--apply" not in command
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command
    assert refresh["materialize_plan_command"] == (
        "cd /home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132/apps/api && "
        "PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python "
        "scripts/build_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json "
        "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --task-id 83 --task-id 84 "
        "--max-age-hours 24 --output-json /tmp/image_agent_remote_release_gate_plan_<timestamp>.json"
    )
    assert refresh["next_steps_after_refresh"] == [
        "operator reviews refreshed dry-run JSON and approval_fingerprint",
        "run build_release_gate_command_plan.py to materialize an operator_authorization_required plan",
        "verify the materialized plan with verify_release_gate_command_plan.py before apply",
    ]


def test_remote_release_gate_reconcile_commands_load_remote_env_for_docker_checks():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    env_prefix = "set -a; . /home/yyf/project/image_agent/.env; set +a;"

    refresh_command = plan["stale_task_approval_refresh"]["command"]
    assert env_prefix in refresh_command

    commands_by_step = {step["id"]: step["command"] for step in plan["steps"]}
    for step_id in (
        "apply_approved_stale_task_resolution",
        "collect_post_apply_clean_dry_run",
    ):
        assert env_prefix in commands_by_step[step_id]


def test_remote_release_gate_command_plan_requires_single_strict_smoke_json_path():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    for step in plan["steps"]:
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["command"] = step["command"].replace(
                "/tmp/image_agent_remote_smoke_acceptance_<timestamp>.json",
                "/tmp/other_remote_smoke_acceptance_<timestamp>.json",
            )
            break

    try:
        verifier.verify_plan(plan)
    except SystemExit as exc:
        assert "strict smoke verifier command must verify the smoke output JSON" in str(exc)
    else:
        raise AssertionError("verify_plan should reject mismatched strict smoke JSON paths")


def test_remote_release_gate_command_plan_requires_fast_launch_env_export_after_strict_verify():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["steps"] = [
        step for step in plan["steps"] if step["id"] != "emit_fast_launch_acceptance_env_after_strict_verify"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected release gate sequence" in str(exc.value)


@pytest.mark.parametrize(
    "required_flag",
    [
        "--require-project-agent-context",
        "--require-agent-workflow-confirmation",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--require-production-readiness",
        "--deployment-id <accepted_release_or_commit>",
        "--min-documents 60",
        "--min-chunks 200",
        "--require-completed-upload",
        "--require-completed-task",
    ],
)
def test_remote_release_gate_command_plan_requires_full_strict_smoke_flags(required_flag):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace(f" {required_flag}", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert f"run_strict_remote_smoke_acceptance.command must include {required_flag}" in str(exc.value)
