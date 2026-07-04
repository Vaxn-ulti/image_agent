import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = REPO_ROOT / "docs" / "deployment" / "remote-release-gate-command-plan.json"
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "build_release_gate_command_plan.py"
VERIFIER_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_release_gate_command_plan.py"
APPROVAL_FIXTURE_PATH = REPO_ROOT / "apps" / "api" / "tests" / "test_verify_stale_task_approval.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _approval_payload() -> dict:
    fixture = _load_module(APPROVAL_FIXTURE_PATH, "test_verify_stale_task_approval_fixture")
    return fixture._approval_payload()


def _load_builder():
    return _load_module(SCRIPT_PATH, "build_release_gate_command_plan")


def _load_verifier():
    return _load_module(VERIFIER_PATH, "verify_release_gate_command_plan")


def test_build_release_gate_command_plan_materializes_reviewed_approval(tmp_path):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    plan = builder.build_release_gate_plan(
        plan_json=PLAN_PATH,
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-16T02:00:00Z",
        approval_json_command_path=remote_approval_json,
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        remote_nifti_file="/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
        workflow_type="t1_deepprep_anat_report",
        project_id=13,
        upload_session_id=77,
        evidence_timestamp="20260616T020000Z",
        production_cors_origins="https://console.example.com",
        production_public_base_url="https://api.example.com",
    )

    serialized = json.dumps(plan, sort_keys=True)
    assert plan["status"] == "operator_authorization_required"
    assert plan["approval_json"] == remote_approval_json
    assert plan["approval_json_state"] == {
        "status": "fresh_reviewed",
        "previous_approval_json": "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json",
        "verified_approval_generated_at_utc": "2026-06-16T01:00:00+00:00",
        "approval_expires_at_utc": "2026-06-17T01:00:00+00:00",
        "next_required_step": "apply_approved_stale_task_resolution",
    }
    step_serialized = json.dumps(plan["steps"], sort_keys=True)
    assert "<fresh_reviewed_approval_json>" not in serialized
    assert "<accepted_release_or_commit>" not in step_serialized
    assert "<expected_health_version>" not in step_serialized
    assert "<remote_nifti_file>" not in step_serialized
    assert "<real_registered_workflow_type>" not in step_serialized
    assert "<project_id>" not in step_serialized
    assert "<upload_session_id>" not in step_serialized
    assert "<console-hostname>" not in step_serialized
    assert "<api-hostname>" not in step_serialized
    assert "<timestamp>" not in step_serialized
    production_env = next(step for step in plan["steps"] if step["id"] == "apply_production_readiness_env")
    assert "--production-cors-origins https://console.example.com" in production_env["command"]
    assert "--production-public-base-url https://api.example.com" in production_env["command"]
    refresh_serialized = json.dumps(plan["stale_task_approval_refresh"], sort_keys=True)
    assert plan["stale_task_approval_refresh"] == {
        "status": "superseded_by_fresh_reviewed_approval",
        "source_approval_json": remote_approval_json,
        "approval_expires_at_utc": "2026-06-17T01:00:00+00:00",
        "next_required_step": "apply_approved_stale_task_resolution",
        "mutates_remote_state": False,
        "requires_operator_authorization": False,
    }
    assert "<" not in refresh_serialized
    assert ">" not in refresh_serialized
    assert str(approval_json) not in serialized
    apply_step = next(step for step in plan["steps"] if step["id"] == "apply_approved_stale_task_resolution")
    assert f"--approval-json {remote_approval_json}" in apply_step["command"]
    report = verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")
    assert report["checked"]["approval_json_status"] == "fresh_reviewed"


def test_build_release_gate_command_plan_can_reuse_existing_uploaded_series(tmp_path):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    plan = builder.build_release_gate_plan(
        plan_json=PLAN_PATH,
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-16T02:00:00Z",
        approval_json_command_path=remote_approval_json,
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        uploaded_series_id=49,
        workflow_type="t1_deepprep_anat_report",
        project_id=27,
        upload_session_id=10,
        evidence_timestamp="20260616T020000Z",
        production_cors_origins="https://console.example.com",
        production_public_base_url="https://api.example.com",
    )

    strict_smoke = next(step for step in plan["steps"] if step["id"] == "run_strict_remote_smoke_acceptance")
    assert "--uploaded-series-id 49" in strict_smoke["command"]
    assert "--upload-nifti-file" not in strict_smoke["command"]
    assert "<uploaded_series_id>" not in json.dumps(plan["steps"], sort_keys=True)
    assert verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")["status"] == "passed"


def test_build_release_gate_command_plan_materializes_private_network_deployment(tmp_path):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    plan = builder.build_release_gate_plan(
        plan_json=PLAN_PATH,
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-16T02:00:00Z",
        approval_json_command_path=remote_approval_json,
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        uploaded_series_id=49,
        acceptance_task_id=137,
        agent_state_db="/home/yyf/project/image_agent/data/app.db",
        workflow_type="t1_deepprep_anat_report",
        project_id=27,
        upload_session_id=10,
        evidence_timestamp="20260616T020000Z",
        deployment_scope="private_network",
        production_cors_origins="http://127.0.0.1:5173",
        production_public_base_url="http://127.0.0.1:8000",
    )

    production_env = next(step for step in plan["steps"] if step["id"] == "apply_production_readiness_env")
    assert "--deployment-scope private_network" in production_env["command"]
    assert "--production-cors-origins http://127.0.0.1:5173" in production_env["command"]
    assert "--production-public-base-url http://127.0.0.1:8000" in production_env["command"]
    strict_smoke = next(step for step in plan["steps"] if step["id"] == "run_strict_remote_smoke_acceptance")
    assert "--reuse-persisted-agent-launch-evidence" in strict_smoke["command"]
    assert verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")["status"] == "passed"


def test_build_release_gate_command_plan_can_reuse_completed_agent_launch_evidence(tmp_path):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    plan = builder.build_release_gate_plan(
        plan_json=PLAN_PATH,
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-16T02:00:00Z",
        approval_json_command_path=remote_approval_json,
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        uploaded_series_id=50,
        acceptance_task_id=137,
        agent_state_db="/home/yyf/project/image_agent/data/app.db",
        workflow_type="t1_deepprep_anat_report",
        project_id=28,
        upload_session_id=11,
        evidence_timestamp="20260616T020000Z",
        production_cors_origins="https://console.example.com",
        production_public_base_url="https://api.example.com",
    )

    strict_smoke = next(step for step in plan["steps"] if step["id"] == "run_strict_remote_smoke_acceptance")
    command = strict_smoke["command"]
    assert "--uploaded-series-id 50" in command
    assert "--upload-nifti-file" not in command
    assert "--reuse-persisted-agent-launch-evidence" in command
    assert "--agent-state-db /home/yyf/project/image_agent/data/app.db" in command
    assert "--task-id 137" in command
    assert "--launch-series-id 50" in command
    assert verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")["status"] == "passed"


def test_build_release_gate_command_plan_rejects_reuse_launch_series_mismatch(tmp_path):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")
    plan = builder.build_release_gate_plan(
        plan_json=PLAN_PATH,
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-16T02:00:00Z",
        approval_json_command_path=remote_approval_json,
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        uploaded_series_id=50,
        acceptance_task_id=137,
        agent_state_db="/home/yyf/project/image_agent/data/app.db",
        workflow_type="t1_deepprep_anat_report",
        project_id=28,
        upload_session_id=11,
        evidence_timestamp="20260616T020000Z",
        production_cors_origins="https://console.example.com",
        production_public_base_url="https://api.example.com",
    )
    strict_smoke = next(step for step in plan["steps"] if step["id"] == "run_strict_remote_smoke_acceptance")
    strict_smoke["command"] = strict_smoke["command"].replace("--launch-series-id 50", "--launch-series-id 51")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")

    assert "launch-series-id must match uploaded-series-id" in str(exc.value)


def test_build_release_gate_command_plan_rejects_reuse_without_uploaded_series(tmp_path):
    builder = _load_builder()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        builder.build_release_gate_plan(
            plan_json=PLAN_PATH,
            approval_json=approval_json,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-16T02:00:00Z",
            approval_json_command_path="/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json",
            deployment_id="codex-gate-verifiers-efca895b",
            expected_health_version="0.2.0-efca895b",
            remote_nifti_file="/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
            acceptance_task_id=137,
            agent_state_db="/home/yyf/project/image_agent/data/app.db",
            workflow_type="t1_deepprep_anat_report",
            project_id=28,
            upload_session_id=11,
            evidence_timestamp="20260616T020000Z",
            production_cors_origins="https://console.example.com",
            production_public_base_url="https://api.example.com",
        )

    assert "acceptance_task_id requires uploaded_series_id" in str(exc.value)


def test_build_release_gate_command_plan_rejects_stale_approval(tmp_path):
    builder = _load_builder()
    approval_json = tmp_path / "stale-approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        builder.build_release_gate_plan(
            plan_json=PLAN_PATH,
            approval_json=approval_json,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-17T02:00:00Z",
        )

    assert "generated_at is older than max_age_hours" in str(exc.value)


def test_build_release_gate_command_plan_rejects_missing_materialization_args(tmp_path):
    builder = _load_builder()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        builder.build_release_gate_plan(
            plan_json=PLAN_PATH,
            approval_json=approval_json,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-16T02:00:00Z",
            approval_json_command_path="/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json",
            expected_health_version="0.2.0-efca895b",
            remote_nifti_file="/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
            workflow_type="t1_deepprep_anat_report",
            project_id=13,
            upload_session_id=77,
            evidence_timestamp="20260616T020000Z",
            production_cors_origins="https://console.example.com",
            production_public_base_url="https://api.example.com",
        )

    assert "deployment_id is required" in str(exc.value)


def test_build_release_gate_command_plan_rejects_unsafe_deployment_id(tmp_path):
    builder = _load_builder()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        builder.build_release_gate_plan(
            plan_json=PLAN_PATH,
            approval_json=approval_json,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-16T02:00:00Z",
            approval_json_command_path="/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json",
            deployment_id="/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b",
            expected_health_version="0.2.0-efca895b",
            remote_nifti_file="/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
            workflow_type="t1_deepprep_anat_report",
            project_id=13,
            upload_session_id=77,
            evidence_timestamp="20260616T020000Z",
        )

    assert "deployment_id must be a privacy-safe release symbol" in str(exc.value)


@pytest.mark.parametrize(
    ("production_cors_origins", "production_public_base_url", "message"),
    [
        (
            "https://console.example.com",
            "https://10.2.32.14",
            "production_public_base_url must be a public HTTPS origin",
        ),
        (
            "https://console.example.com",
            "https://api",
            "production_public_base_url must be a public HTTPS origin",
        ),
        (
            "https://10.2.32.14",
            "https://api.example.com",
            "production_cors_origins must be a public HTTPS origin",
        ),
        (
            "https://console",
            "https://api.example.com",
            "production_cors_origins must be a public HTTPS origin",
        ),
    ],
)
def test_build_release_gate_command_plan_rejects_non_public_production_origins(
    tmp_path,
    production_cors_origins,
    production_public_base_url,
    message,
):
    builder = _load_builder()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        builder.build_release_gate_plan(
            plan_json=PLAN_PATH,
            approval_json=approval_json,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-16T02:00:00Z",
            approval_json_command_path="/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json",
            deployment_id="codex-gate-verifiers-efca895b",
            expected_health_version="0.2.0-efca895b",
            remote_nifti_file="/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
            workflow_type="t1_deepprep_anat_report",
            project_id=13,
            upload_session_id=77,
            evidence_timestamp="20260616T020000Z",
            production_cors_origins=production_cors_origins,
            production_public_base_url=production_public_base_url,
        )

    assert message in str(exc.value)


def test_build_release_gate_command_plan_cli_writes_json(tmp_path, capsys):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    output_json = tmp_path / "release-gate-plan.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    builder.main(
        [
            str(PLAN_PATH),
            str(approval_json),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-16T02:00:00Z",
            "--approval-json-command-path",
            remote_approval_json,
            "--deployment-id",
            "codex-gate-verifiers-efca895b",
            "--expected-health-version",
            "0.2.0-efca895b",
            "--remote-nifti-file",
            "/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
            "--workflow-type",
            "t1_deepprep_anat_report",
            "--project-id",
            "13",
            "--upload-session-id",
            "77",
            "--evidence-timestamp",
            "20260616T020000Z",
            "--production-cors-origins",
            "https://console.example.com",
            "--production-public-base-url",
            "https://api.example.com",
            "--output-json",
            str(output_json),
        ]
    )

    stdout_plan = json.loads(capsys.readouterr().out)
    saved_plan = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_plan == saved_plan
    assert saved_plan["approval_json"] == remote_approval_json
    assert verifier.verify_plan(saved_plan, now_utc="2026-06-16T02:00:00Z")["status"] == "passed"


def test_build_release_gate_command_plan_cli_can_reuse_existing_uploaded_series(tmp_path, capsys):
    builder = _load_builder()
    verifier = _load_verifier()
    approval_json = tmp_path / "image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    remote_approval_json = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    builder.main(
        [
            str(PLAN_PATH),
            str(approval_json),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-16T02:00:00Z",
            "--approval-json-command-path",
            remote_approval_json,
            "--deployment-id",
            "codex-gate-verifiers-efca895b",
            "--expected-health-version",
            "0.2.0-efca895b",
            "--uploaded-series-id",
            "49",
            "--workflow-type",
            "t1_deepprep_anat_report",
            "--project-id",
            "27",
            "--upload-session-id",
            "10",
            "--evidence-timestamp",
            "20260616T020000Z",
            "--production-cors-origins",
            "https://console.example.com",
            "--production-public-base-url",
            "https://api.example.com",
        ]
    )

    stdout_plan = json.loads(capsys.readouterr().out)
    strict_smoke = next(step for step in stdout_plan["steps"] if step["id"] == "run_strict_remote_smoke_acceptance")
    assert "--uploaded-series-id 49" in strict_smoke["command"]
    assert "--upload-nifti-file" not in strict_smoke["command"]
    assert verifier.verify_plan(stdout_plan, now_utc="2026-06-16T02:00:00Z")["status"] == "passed"


def test_build_release_gate_command_plan_rejects_non_remote_command_path(tmp_path):
    builder = _load_builder()
    approval_json = tmp_path / "approval.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-16T01:00:00+00:00"
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        builder.build_release_gate_plan(
            plan_json=PLAN_PATH,
            approval_json=approval_json,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-16T02:00:00Z",
            approval_json_command_path="C:/Users/A/approval.json",
        )

    assert "approval_json_command_path must be a /tmp/image_agent_*.json remote path" in str(exc.value)
