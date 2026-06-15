import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = REPO_ROOT / "docs" / "deployment" / "remote-release-gate-command-plan.json"
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_release_gate_command_plan.py"
CURRENT_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_release_gate_command_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_remote_release_gate_command_plan_is_machine_checkable():
    verifier = load_verifier()
    plan = verifier.load_plan(PLAN_PATH)
    report = verifier.verify_plan(plan)

    assert report["status"] == "passed"
    assert report["checked"]["plan_id"] == "remote_release_gate_after_stale_task_approval_v1"
    assert report["checked"]["step_count"] == 8
    assert report["checked"]["operator_authorization_required_steps"] == [
        "apply_approved_stale_task_resolution"
    ]
    assert report["checked"]["mutating_steps"] == [
        "apply_approved_stale_task_resolution",
        "restart_api_normally",
    ]
    assert report["checked"]["approval_request_required_fields"] == [
        "approval_fingerprint",
        "approval_expires_at_utc",
    ]
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
    ]

    commands = "\n".join(step["command"] for step in plan["steps"])
    assert f"--approval-json {CURRENT_APPROVAL_JSON}" in commands
    assert "approval_fingerprint" in json.dumps(plan, sort_keys=True)
    assert "approval_expires_at_utc" in json.dumps(plan, sort_keys=True)
    assert "--check-containers --task-id 83 --task-id 84" in commands
    assert "--require-empty-active --max-age-hours 24" in commands
    assert "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands
    assert "restart_preflight:ok" in json.dumps(plan, sort_keys=True)
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in commands
    assert "--require-model" in commands
    assert "--require-real-evidence-ids" in commands
    assert "--expected-health-version <expected_health_version>" in commands
    assert "--require-container-native-qc" in commands
    assert "--require-scientific-report-artifacts" in commands
    assert "verify_remote_smoke_acceptance.py" in commands
    assert "<project_id>" in commands
    assert "<upload_session_id>" in commands
    assert "<completed_task_id>" in commands


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
    assert refresh["next_steps_after_refresh"] == [
        "operator reviews refreshed dry-run JSON and approval_fingerprint",
        "set approval_json to the refreshed dry-run JSON path",
        "rerun verify_fresh_stale_task_approval before apply",
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
