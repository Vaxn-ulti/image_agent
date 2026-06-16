import importlib.util
import json
from pathlib import Path

import pytest

from tests.test_build_stale_task_apply_request import load_module as load_builder
from tests.test_verify_stale_task_approval import _approval_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_stale_task_apply_request.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_stale_task_apply_request", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _request_payload(tmp_path):
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")
    builder = load_builder()
    return builder.build_apply_request(
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:00:00Z",
        output_timestamp="20260612T050000Z",
    )


def test_verify_stale_task_apply_request_accepts_complete_request(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)

    report = verifier.verify_apply_request(
        request,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:30:00Z",
    )

    assert report["status"] == "passed"
    assert report["checked"]["request_type"] == "stale_task_apply_approval"
    assert report["checked"]["authorization_required"] is True
    assert report["checked"]["target_task_ids"] == [83, 84]
    assert report["checked"]["approval_fingerprint"] == request["approval_fingerprint"]
    assert report["checked"]["expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
    assert report["checked"]["followup_step_ids"] == [
        "collect_post_apply_clean_dry_run",
        "verify_post_apply_clean_resolution",
        "restart_api_preflight_only",
        "restart_api_normally",
        "run_strict_remote_smoke_acceptance",
        "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
        "emit_fast_launch_acceptance_env_after_strict_verify",
    ]


def test_verify_stale_task_apply_request_accepts_exact_freshness_boundary(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)

    report = verifier.verify_apply_request(
        request,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-13T04:14:24.156875Z",
    )

    assert report["status"] == "passed"
    assert report["checked"]["expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"


def test_verify_stale_task_apply_request_rejects_after_freshness_boundary(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-13T04:14:25Z",
        )

    assert "verified approval generated_at_utc is older than max_age_hours" in str(exc.value)


def test_verify_stale_task_apply_request_requires_full_main_flow_strict_smoke(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace(" --require-agent-workflow-confirmation", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke command must include --require-agent-workflow-confirmation" in str(exc.value)


@pytest.mark.parametrize(
    "required_flag",
    [
        "--require-deployment-identity",
        "--require-agent-workflow-confirmation",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--deployment-id <accepted_release_or_commit>",
        "--min-documents 60",
        "--min-chunks 200",
        "--require-raw-source-policy",
        "--require-vendor-pointer-integrity",
        "--require-uploaded-series",
        "--upload-nifti-file <remote_nifti_file>",
        "--require-launchability-matrix",
        "--min-native-qc-images 1",
        "--min-scientific-report-images 1",
        "--project-id <project_id>",
        "--upload-session-id <upload_session_id>",
    ],
)
def test_verify_stale_task_apply_request_requires_complete_readiness_smoke_flags(tmp_path, required_flag):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace(f" {required_flag}", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert f"strict smoke command must include {required_flag}" in str(exc.value)


def test_verify_stale_task_apply_request_requires_strict_smoke_marked_mutating(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["mutates_remote_state"] = False
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke step must be marked as mutating remote state" in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: next(
                step for step in request["required_followup_steps"] if step["id"] == "run_strict_remote_smoke_acceptance"
            ).update({"expected_output_json": "/tmp/other-smoke.json"}),
            "strict smoke expected_output_json must match --output-json",
        ),
        (
            lambda request: next(
                step
                for step in request["required_followup_steps"]
                if step["id"] == "verify_strict_remote_smoke_acceptance_json_after_normal_restart"
            ).update(
                {
                    "command": next(
                        step
                        for step in request["required_followup_steps"]
                        if step["id"] == "verify_strict_remote_smoke_acceptance_json_after_normal_restart"
                    )["command"].replace("/tmp/image_agent_remote_smoke_acceptance_20260612T050000Z.json", "/tmp/other-smoke.json")
                }
            ),
            "strict smoke verifier command must verify the smoke output JSON",
        ),
        (
            lambda request: next(
                step
                for step in request["required_followup_steps"]
                if step["id"] == "emit_fast_launch_acceptance_env_after_strict_verify"
            ).update(
                {
                    "command": next(
                        step
                        for step in request["required_followup_steps"]
                        if step["id"] == "emit_fast_launch_acceptance_env_after_strict_verify"
                    )["command"].replace("/tmp/image_agent_remote_smoke_acceptance_20260612T050000Z.json", "/tmp/other-smoke.json")
                }
            ),
            "fast-launch env export command must verify the smoke output JSON",
        ),
    ],
)
def test_verify_stale_task_apply_request_requires_single_strict_smoke_json_path(tmp_path, mutate, message):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    mutate(request)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert message in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["apply_step"].update({"command": request["apply_step"]["command"] + " IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1"}),
            "must not use active-task restart override",
        ),
        (
            lambda request: request.update({"authorization_required": False}),
            "authorization_required must be true",
        ),
        (
            lambda request: request["required_followup_steps"].pop(3),
            "required follow-up step ids mismatch",
        ),
        (
            lambda request: request.update({"approval_expires_at_utc": "2026-06-13T04:14:25+00:00"}),
            "approval_expires_at_utc mismatch",
        ),
    ],
)
def test_verify_stale_task_apply_request_rejects_unsafe_request(tmp_path, mutate, message):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    mutate(request)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert message in str(exc.value)


def test_verify_stale_task_apply_request_cli_prints_passed_report(tmp_path, capsys):
    verifier = load_verifier()
    request_path = tmp_path / "apply-request.json"
    request_path.write_text(json.dumps(_request_payload(tmp_path)), encoding="utf-8")

    verifier.main(
        [
            str(request_path),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-12T05:30:00Z",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["source_json"] == str(request_path)
    assert report["checked"]["expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
