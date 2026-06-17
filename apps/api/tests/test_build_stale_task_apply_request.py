import importlib.util
import json
import re
from pathlib import Path

from tests.test_verify_stale_task_approval import _approval_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "build_stale_task_apply_request.py"
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")


def load_module():
    spec = importlib.util.spec_from_file_location("build_stale_task_apply_request", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_stale_task_apply_request_requires_operator_authorization(tmp_path):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    payload = _approval_payload()
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    request = module.build_apply_request(
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:00:00Z",
        output_timestamp="20260612T050000Z",
    )

    assert request["status"] == "operator_authorization_required"
    assert request["request_type"] == "stale_task_apply_approval"
    assert request["authorization_required"] is True
    assert request["approval_json"] == str(approval_json)
    assert request["target_task_ids"] == [83, 84]
    assert request["approval_fingerprint"] == payload["approval_fingerprint"]
    assert request["approval_expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
    assert request["verified_approval"]["status"] == "passed"
    assert request["verified_approval"]["checked"]["generated_at_utc"] == payload["generated_at"]
    assert request["must_not_run_until"] == "operator explicitly approves stale-task apply"

    apply = request["apply_step"]
    assert apply["mutates_remote_state"] is True
    assert apply["requires_operator_authorization"] is True
    assert "set -a; . /home/yyf/project/image_agent/.env; set +a;" in apply["command"]
    assert "reconcile_stale_tasks.py --apply --max-age-hours 24 --task-id 83 --task-id 84" in apply["command"]
    assert f"--approval-json {approval_json}" in apply["command"]
    assert "--reason \"operator confirmed no matching running Image Agent container\"" in apply["command"]
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in apply["command"]
    assert API_KEY_SHAPED_RE.search(json.dumps(request)) is None


def test_build_stale_task_apply_request_includes_post_apply_gates(tmp_path):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    request = module.build_apply_request(
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:00:00Z",
        output_timestamp="20260612T050000Z",
    )

    commands = "\n".join(step["command"] for step in request["required_followup_steps"])
    steps_by_id = {step["id"]: step for step in request["required_followup_steps"]}
    assert "reconcile_stale_tasks.py --max-age-hours 24 --check-containers --task-id 83 --task-id 84" in commands
    assert "verify_stale_task_resolution.py" in commands
    assert "--require-empty-active --max-age-hours 24" in commands
    assert "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands
    assert "restart_api_normally" in json.dumps(request)
    assert "bash tools/restart_remote_image_agent_api.sh" in commands
    assert "smoke_remote_agent.py" in commands
    assert "--require-model" in commands
    assert "--expected-model-wire-api responses" in commands
    assert "--expected-model-provider-profile rawchat" in commands
    assert "--require-model-tool-loop" in commands
    assert "--require-project-agent-context" in commands
    assert "--require-agent-workflow-confirmation" in commands
    assert "--require-agent-workflow-resume" in commands
    assert "--require-production-readiness" in commands
    assert "--expected-health-version <expected_health_version>" in commands
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
    assert "--require-container-native-qc" in commands
    assert "--require-scientific-report-artifacts" in commands
    assert "restart_preflight:ok" in json.dumps(request)
    assert "verify_remote_smoke_acceptance.py" in commands
    assert "--max-age-hours 24" in commands
    assert "--emit-fast-launch-env" in commands
    assert steps_by_id["run_strict_remote_smoke_acceptance"]["mutates_remote_state"] is True
    assert steps_by_id["emit_fast_launch_acceptance_env_after_strict_verify"]["mutates_remote_state"] is False


def test_build_stale_task_apply_request_cli_writes_json(tmp_path, capsys):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    output_json = tmp_path / "apply-request.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    module.main(
        [
            str(approval_json),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-12T05:00:00Z",
            "--output-timestamp",
            "20260612T050000Z",
            "--output-json",
            str(output_json),
        ]
    )

    stdout_report = json.loads(capsys.readouterr().out)
    saved_report = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_report == saved_report
    assert saved_report["status"] == "operator_authorization_required"
    assert saved_report["output_json"] == str(output_json)
    assert saved_report["approval_expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
