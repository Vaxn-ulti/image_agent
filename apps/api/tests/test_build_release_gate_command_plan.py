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
    assert "<fresh_reviewed_approval_json>" not in serialized
    assert str(approval_json) not in serialized
    apply_step = next(step for step in plan["steps"] if step["id"] == "apply_approved_stale_task_resolution")
    assert f"--approval-json {remote_approval_json}" in apply_step["command"]
    report = verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")
    assert report["checked"]["approval_json_status"] == "fresh_reviewed"


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
            "--output-json",
            str(output_json),
        ]
    )

    stdout_plan = json.loads(capsys.readouterr().out)
    saved_plan = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_plan == saved_plan
    assert saved_plan["approval_json"] == remote_approval_json
    assert verifier.verify_plan(saved_plan, now_utc="2026-06-16T02:00:00Z")["status"] == "passed"


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
