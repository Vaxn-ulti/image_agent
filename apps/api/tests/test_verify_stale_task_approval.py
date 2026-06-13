import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _load_verifier_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_stale_task_approval.py"
    spec = importlib.util.spec_from_file_location("verify_stale_task_approval", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _approval_payload():
    payload = {
        "active_task_count": 2,
        "active_tasks": [
            {
                "age_hours": 540.7,
                "created_at": "2026-05-19T15:32:11.565728+00:00",
                "id": 83,
                "is_stale": True,
                "progress": 20,
                "project_id": 15,
                "series_id": 27,
                "started_at": "2026-05-19T15:32:11.914924+00:00",
                "status": "running",
                "workflow_type": "dwi_qsirecon",
            },
            {
                "age_hours": 540.6,
                "created_at": "2026-05-19T15:32:30.370596+00:00",
                "id": 84,
                "is_stale": True,
                "progress": 20,
                "project_id": 15,
                "series_id": 27,
                "started_at": "2026-05-19T15:32:30.658947+00:00",
                "status": "running",
                "workflow_type": "dwi_qsirecon",
            },
        ],
        "approval_payload": {
            "blocked_task_ids": [],
            "container_check_status": "passed",
            "max_age_hours": 24.0,
            "out_of_scope_stale_task_ids": [],
            "running_container_task_ids": [],
            "stale_candidate_ids": [83, 84],
            "stale_candidates": [
                {
                    "created_at": "2026-05-19T15:32:11.565728+00:00",
                    "id": 83,
                    "progress": 20,
                    "project_id": 15,
                    "series_id": 27,
                    "started_at": "2026-05-19T15:32:11.914924+00:00",
                    "status": "running",
                    "workflow_type": "dwi_qsirecon",
                },
                {
                    "created_at": "2026-05-19T15:32:30.370596+00:00",
                    "id": 84,
                    "progress": 20,
                    "project_id": 15,
                    "series_id": 27,
                    "started_at": "2026-05-19T15:32:30.658947+00:00",
                    "status": "running",
                    "workflow_type": "dwi_qsirecon",
                },
            ],
            "target_task_ids": [83, 84],
        },
        "blocked_task_ids": [],
        "container_check_status": "passed",
        "generated_at": "2026-06-12T04:14:24.156875+00:00",
        "max_age_hours": 24.0,
        "mode": "dry_run",
        "out_of_scope_stale_task_ids": [],
        "running_container_task_ids": [],
        "stale_candidates": [
            {
                "age_hours": 540.7,
                "created_at": "2026-05-19T15:32:11.565728+00:00",
                "id": 83,
                "is_stale": True,
                "progress": 20,
                "project_id": 15,
                "series_id": 27,
                "started_at": "2026-05-19T15:32:11.914924+00:00",
                "status": "running",
                "workflow_type": "dwi_qsirecon",
            },
            {
                "age_hours": 540.6,
                "created_at": "2026-05-19T15:32:30.370596+00:00",
                "id": 84,
                "is_stale": True,
                "progress": 20,
                "project_id": 15,
                "series_id": 27,
                "started_at": "2026-05-19T15:32:30.658947+00:00",
                "status": "running",
                "workflow_type": "dwi_qsirecon",
            },
        ],
        "target_task_ids": [83, 84],
        "updated_task_ids": [],
    }
    verifier = _load_verifier_module()
    payload["approval_fingerprint"] = verifier.approval_fingerprint(payload["approval_payload"])
    return payload


def test_verify_stale_task_approval_accepts_reviewed_dry_run():
    verifier = _load_verifier_module()

    report = verifier.verify_approval_payload(
        _approval_payload(),
        expected_task_ids=[83, 84],
        now=datetime(2026, 6, 12, 5, 0, tzinfo=timezone.utc),
    )

    assert report["status"] == "passed"
    assert report["checked"]["target_task_ids"] == [83, 84]
    assert report["checked"]["stale_candidate_ids"] == [83, 84]


def test_verify_stale_task_approval_rejects_stale_evidence_by_max_age():
    verifier = _load_verifier_module()

    with pytest.raises(SystemExit) as exc:
        verifier.verify_approval_payload(
            _approval_payload(),
            expected_task_ids=[83, 84],
            now=datetime(2026, 6, 13, 5, 0, tzinfo=timezone.utc),
        )

    assert "generated_at is older than max_age_hours" in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (lambda payload: payload.update({"approval_fingerprint": "0" * 64}), "approval_fingerprint mismatch"),
        (lambda payload: payload.update({"running_container_task_ids": [83]}), "running_container_task_ids must be empty"),
        (lambda payload: payload.update({"updated_task_ids": [83]}), "updated_task_ids must be empty"),
        (lambda payload: payload.update({"mode": "apply"}), "mode must be dry_run"),
        (lambda payload: payload.update({"target_task_ids": [83]}), "target_task_ids must match expected task ids"),
        (lambda payload: payload.update({"generated_at": ""}), "generated_at must be an ISO-8601 timestamp"),
        (lambda payload: payload.update({"generated_at": "2026-06-11T04:14:24"}), "generated_at must be timezone-aware"),
        (
            lambda payload: payload["approval_payload"].update({"debug_output_dir": "/home/yyf/project/image_agent/data/projects/15"}),
            "stale-task evidence must not expose backend paths",
        ),
        (
            lambda payload: payload["active_tasks"][0].update({"debug_log": "C:\\Users\\A\\Documents\\task.log"}),
            "stale-task evidence must not expose backend paths",
        ),
    ],
)
def test_verify_stale_task_approval_rejects_weak_evidence(mutate, expected_message):
    verifier = _load_verifier_module()
    payload = _approval_payload()
    mutate(payload)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_approval_payload(
            payload,
            expected_task_ids=[83, 84],
            now=datetime(2026, 6, 12, 5, 0, tzinfo=timezone.utc),
        )

    assert expected_message in str(exc.value)


def test_verify_stale_task_approval_cli_prints_passed_report(tmp_path, capsys):
    verifier = _load_verifier_module()
    payload_path = tmp_path / "stale-approval.json"
    payload = _approval_payload()
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    verifier.main([str(payload_path), "--task-id", "83", "--task-id", "84"])

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["source_json"] == str(payload_path)
    assert report["checked"]["max_age_hours"] == 24.0
    assert report["checked"]["generated_at_utc"] == payload["generated_at"]


def test_verify_stale_task_approval_cli_max_age_hours_overrides_loose_payload(tmp_path):
    verifier = _load_verifier_module()
    payload_path = tmp_path / "stale-approval.json"
    payload = _approval_payload()
    payload["generated_at"] = "2026-06-12T04:14:24.156875+00:00"
    payload["max_age_hours"] = 999.0
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        verifier.main(
            [
                str(payload_path),
                "--task-id",
                "83",
                "--task-id",
                "84",
                "--max-age-hours",
                "24",
                "--now-utc",
                "2026-06-13T05:00:00Z",
            ]
        )

    assert "generated_at is older than max_age_hours" in str(exc.value)
