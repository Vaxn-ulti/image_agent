import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def _load_verifier_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_stale_task_resolution.py"
    spec = importlib.util.spec_from_file_location("verify_stale_task_resolution", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fingerprint(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _apply_payload():
    approval_payload = {
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
    }
    return {
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
        "approval_payload": approval_payload,
        "approval_fingerprint": _fingerprint(approval_payload),
        "blocked_task_ids": [],
        "container_check_status": "passed",
        "generated_at": "2026-06-11T04:20:24.156875+00:00",
        "max_age_hours": 24.0,
        "mode": "apply",
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
        "updated_task_ids": [83, 84],
    }


def _resolved_payload():
    approval_payload = {
        "blocked_task_ids": [],
        "container_check_status": "passed",
        "max_age_hours": 24.0,
        "out_of_scope_stale_task_ids": [],
        "running_container_task_ids": [],
        "stale_candidate_ids": [],
        "stale_candidates": [],
        "target_task_ids": [83, 84],
    }
    return {
        "active_task_count": 0,
        "active_tasks": [],
        "approval_payload": approval_payload,
        "approval_fingerprint": _fingerprint(approval_payload),
        "blocked_task_ids": [],
        "container_check_status": "passed",
        "generated_at": "2026-06-11T04:25:24.156875+00:00",
        "max_age_hours": 24.0,
        "mode": "dry_run",
        "out_of_scope_stale_task_ids": [],
        "running_container_task_ids": [],
        "stale_candidates": [],
        "target_task_ids": [83, 84],
        "updated_task_ids": [],
    }


def test_verify_stale_task_resolution_accepts_apply_and_clean_followup():
    verifier = _load_verifier_module()

    report = verifier.verify_resolution_evidence(
        _apply_payload(),
        _resolved_payload(),
        expected_task_ids=[83, 84],
        require_empty_active=True,
    )

    assert report["status"] == "passed"
    assert report["checked"]["updated_task_ids"] == [83, 84]
    assert report["checked"]["resolved_task_ids"] == [83, 84]


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (lambda apply_payload, resolved_payload: apply_payload.update({"updated_task_ids": [83]}), "updated_task_ids must match expected task ids"),
        (
            lambda apply_payload, resolved_payload: apply_payload["stale_candidates"][0].update({"log_path": "/home/yyf/project/image_agent/data/task-83.log"}),
            "task evidence must not expose log_path",
        ),
        (
            lambda apply_payload, resolved_payload: resolved_payload["active_tasks"].append({"id": 99, "log_path": "/home/yyf/project/image_agent/data/task-99.log"}),
            "task evidence must not expose log_path",
        ),
        (
            lambda apply_payload, resolved_payload: resolved_payload.update(
                {
                    "active_task_count": 1,
                    "active_tasks": [
                        {
                            "id": 83,
                            "is_stale": False,
                            "status": "running",
                            "project_id": 15,
                            "series_id": 27,
                            "workflow_type": "dwi_qsirecon",
                            "progress": 20,
                        }
                    ],
                }
            ),
            "resolved dry-run must not include target task ids as active",
        ),
        (
            lambda apply_payload, resolved_payload: resolved_payload.update(
                {
                    "stale_candidates": [
                        {
                            "id": 83,
                            "is_stale": True,
                            "status": "running",
                            "project_id": 15,
                            "series_id": 27,
                            "workflow_type": "dwi_qsirecon",
                            "progress": 20,
                        }
                    ]
                }
            ),
            "resolved dry-run stale_candidates must be empty",
        ),
    ],
)
def test_verify_stale_task_resolution_rejects_weak_evidence(mutate, expected_message):
    verifier = _load_verifier_module()
    apply_payload = _apply_payload()
    resolved_payload = _resolved_payload()
    mutate(apply_payload, resolved_payload)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_resolution_evidence(
            apply_payload,
            resolved_payload,
            expected_task_ids=[83, 84],
            require_empty_active=True,
        )

    assert expected_message in str(exc.value)


def test_verify_stale_task_resolution_cli_prints_passed_report(tmp_path, capsys):
    verifier = _load_verifier_module()
    apply_path = tmp_path / "stale-apply.json"
    resolved_path = tmp_path / "stale-resolved.json"
    apply_path.write_text(json.dumps(_apply_payload()), encoding="utf-8")
    resolved_path.write_text(json.dumps(_resolved_payload()), encoding="utf-8")

    verifier.main(
        [
            "--apply-json",
            str(apply_path),
            "--resolution-json",
            str(resolved_path),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--require-empty-active",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["source_json"]["apply"] == str(apply_path)
    assert report["source_json"]["resolution"] == str(resolved_path)
