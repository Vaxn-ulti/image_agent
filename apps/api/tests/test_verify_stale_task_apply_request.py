import importlib.util
import json
from pathlib import Path

import pytest

from test_build_stale_task_apply_request import load_module as load_builder
from test_verify_stale_task_approval import _approval_payload


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
    assert report["checked"]["followup_step_ids"] == [
        "collect_post_apply_clean_dry_run",
        "verify_post_apply_clean_resolution",
        "restart_api_preflight_only",
        "restart_api_normally",
        "run_strict_remote_smoke_acceptance",
        "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
    ]


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
