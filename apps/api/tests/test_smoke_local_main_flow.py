import importlib.util
import json
from pathlib import Path

import pytest


def _load_smoke_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_local_main_flow.py"
    assert script.is_file(), "local product main-flow smoke script is missing"
    spec = importlib.util.spec_from_file_location("smoke_local_main_flow", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_local_main_flow_smoke_exercises_upload_series_workflow_and_boundaries(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    calls = []
    output_json = tmp_path / "local-smoke.json"

    def fake_upload_nifti(base, project_id, path):
        calls.append(("UPLOAD", base, project_id, path.name))
        return {
            "file": {"id": 9, "original_name": path.name},
            "series": {
                "id": 21,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w",
            },
        }

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1", "sequence_label": "T1w"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {
                "id": 34,
                "project_id": 13,
                "series_id": 21,
                "workflow_type": "t1_deepprep_mock",
                "status": "queued",
                "log_path": "C:/Users/A/private/task.log",
            }
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [
                {
                    "id": 34,
                    "project_id": 13,
                    "series_id": 21,
                    "workflow_type": "t1_deepprep_mock",
                    "status": "queued",
                    "log_path": "C:/Users/A/private/task.log",
                }
            ]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {
                "configured": False,
                "provider": "OpenAI",
                "model": "gpt-5.5",
                "wire_api": "chat_completions",
                "gateway_diagnostics": {
                    "sdk_method": "chat.completions.create",
                    "model_tool_loop": "skipped",
                },
            }
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {
                "grounding_policy": {
                    "raw_sources_indexed": False,
                    "answer_boundary": "RAG explains vendor docs; backend state remains authoritative",
                },
                "index": {"document_count": 72, "chunk_count": 260},
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--output-json", str(output_json)])

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["health_status"] == "passed"
    assert payload["upload_status"] == "passed"
    assert payload["uploaded_series"] == {
        "project_id": 13,
        "series_id": 21,
        "modality": "T1",
        "sequence_label": "T1w",
    }
    assert payload["workflow_launch_status"] == "passed"
    assert payload["launched_task"] == {
        "project_id": 13,
        "series_id": 21,
        "task_id": 34,
        "workflow_type": "t1_deepprep_mock",
        "status": "queued",
    }
    assert payload["agent_boundary_status"] == "skipped_missing_model_config"
    assert payload["rag_boundary_status"] == "passed"
    assert "C:/Users/A/private" not in json.dumps(payload)
    assert ("POST", "http://api.local/series/21/run", {"workflow_type": "t1_deepprep_mock"}) in calls
    assert any(call[0] == "UPLOAD" and call[3] == "sub-local-smoke_T1w.nii.gz" for call in calls)


def test_local_main_flow_smoke_requires_agent_confirmation_when_requested(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-agent.json"

    def fake_upload_nifti(base, project_id, path):
        return {
            "series": {
                "id": 21,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w",
            },
        }

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1", "sequence_label": "T1w"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {
                "id": 34,
                "project_id": 13,
                "series_id": 21,
                "workflow_type": "t1_deepprep_mock",
                "status": "queued",
            }
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI", "model": "gpt-5.5", "wire_api": "responses"}
        if method == "POST" and url.endswith("/agent/runs"):
            assert payload["project_id"] == 13
            assert "series 21" in payload["message"]
            assert "workflow t1_deepprep_anat_report" in payload["message"]
            return {
                "status": "confirmation_required",
                "thread_id": "thread-safe",
                "confirmation": {
                    "type": "workflow_run",
                    "project_id": 13,
                    "series_id": 21,
                    "workflow_type": "t1_deepprep_anat_report",
                    "summary": "Prepare a deterministic backend workflow launch.",
                },
                "production_task_created": False,
            }
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-agent-confirmation",
            "--agent-workflow-type",
            "t1_deepprep_anat_report",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["agent_boundary_status"] == "passed"
    assert payload["agent_workflow_confirmation"] == {
        "project_id": 13,
        "series_id": 21,
        "workflow_type": "t1_deepprep_anat_report",
        "production_task_created": False,
    }


def test_local_main_flow_smoke_can_create_task_through_agent_resume(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    calls = []
    output_json = tmp_path / "local-smoke-agent-resume.json"
    confirmation = {
        "type": "workflow_run",
        "project_id": 13,
        "series_id": 21,
        "workflow_type": "t1_deepprep_anat_report",
        "summary": "Prepare a deterministic backend workflow launch.",
    }

    def fake_upload_nifti(base, project_id, path):
        return {
            "series": {
                "id": 21,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w",
            },
        }

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1", "sequence_label": "T1w"}]
        if method == "POST" and url.endswith("/agent/runs"):
            return {
                "status": "confirmation_required",
                "thread_id": "thread-safe",
                "confirmation": confirmation,
                "production_task_created": False,
            }
        if method == "POST" and url.endswith("/agent/runs/thread-safe/resume"):
            assert payload == {"approved": True, "confirmation": confirmation}
            return {
                "status": "task_created",
                "agent_run_id": "agent_run_resume",
                "thread_id": "thread-safe",
                "project_id": 13,
                "series_id": 21,
                "task_id": 34,
                "workflow_type": "t1_deepprep_anat_report",
                "production_task_created": True,
                "task": {
                    "id": 34,
                    "project_id": 13,
                    "series_id": 21,
                    "workflow_type": "t1_deepprep_anat_report",
                    "status": "queued",
                    "log_path": "C:/Users/A/private/task.log",
                },
                "safe_metadata": {"confirmation_gate": "fingerprint_verified"},
            }
        if method == "POST" and url.endswith("/series/21/run"):
            raise AssertionError("agent resume smoke must not also call direct /series/{series_id}/run")
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_anat_report", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI", "model": "gpt-5.5", "wire_api": "responses"}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-agent-confirmation",
            "--require-agent-resume",
            "--agent-workflow-type",
            "t1_deepprep_anat_report",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["agent_boundary_status"] == "passed"
    assert payload["workflow_launch_status"] == "passed_via_agent_resume"
    assert payload["agent_workflow_resume_status"] == "passed"
    assert payload["agent_workflow_resume"] == {
        "agent_run_id": "agent_run_resume",
        "thread_id": "thread-safe",
        "status": "task_created",
        "project_id": 13,
        "series_id": 21,
        "task_id": 34,
        "workflow_type": "t1_deepprep_anat_report",
        "production_task_created": True,
        "confirmation_gate": "fingerprint_verified",
    }
    assert payload["launched_task"] == {
        "project_id": 13,
        "series_id": 21,
        "task_id": 34,
        "workflow_type": "t1_deepprep_anat_report",
        "status": "queued",
    }
    assert ("POST", "http://api.local/agent/runs/thread-safe/resume", {"approved": True, "confirmation": confirmation}) in calls
    assert "C:/Users/A/private" not in json.dumps(payload)


def test_local_main_flow_smoke_records_safe_upload_workflow_eligibility(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-eligibility.json"

    workflow_eligibility = {
        "blocked_workflows": [
            {
                "workflow_type": "dwi_fast_gpu_dti",
                "blocking_reasons": ["Requires a DWI series."],
                "debug_path": "C:/Users/A/private/data",
            }
        ],
        "policy_version": "workflow_eligibility_v1",
        "primary_recommendation": {"workflow_type": "t1_deepprep_anat_report"},
        "production_task_created": False,
        "runnable_workflows": [{"workflow_type": "t1_deepprep_anat_report"}],
    }

    def fake_upload_nifti(base, project_id, path):
        return {
            "series": {
                "id": 21,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w",
                "workflow_eligibility": workflow_eligibility,
            },
        }

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [
                {
                    "id": 21,
                    "project_id": 13,
                    "modality": "T1",
                    "sequence_label": "T1w",
                    "workflow_eligibility": workflow_eligibility,
                }
            ]
        if method == "POST" and url.endswith("/series/21/run"):
            return {
                "id": 34,
                "project_id": 13,
                "series_id": 21,
                "workflow_type": "t1_deepprep_mock",
                "status": "queued",
            }
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": False}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--output-json", str(output_json)])

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["uploaded_series"]["workflow_eligibility"] == {
        "blocked_workflows": [
            {
                "blocking_reasons": ["Requires a DWI series."],
                "workflow_type": "dwi_fast_gpu_dti",
            }
        ],
        "policy_version": "workflow_eligibility_v1",
        "primary_recommendation": {"workflow_type": "t1_deepprep_anat_report"},
        "production_task_created": False,
        "runnable_workflows": [{"workflow_type": "t1_deepprep_anat_report"}],
    }
    assert "C:/Users/A/private" not in json.dumps(payload)


def test_local_main_flow_smoke_can_use_distinct_agent_workflow_type(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-agent-workflow.json"

    def fake_upload_nifti(base, project_id, path):
        return {
            "series": {
                "id": 21,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w",
            },
        }

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1", "sequence_label": "T1w"}]
        if method == "POST" and url.endswith("/series/21/run"):
            assert payload == {"workflow_type": "t1_deepprep_mock"}
            return {
                "id": 34,
                "project_id": 13,
                "series_id": 21,
                "workflow_type": "t1_deepprep_mock",
                "status": "queued",
            }
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI", "model": "gpt-5.5", "wire_api": "responses"}
        if method == "POST" and url.endswith("/agent/runs"):
            assert "workflow t1_deepprep_anat_report" in payload["message"]
            return {
                "status": "confirmation_required",
                "thread_id": "thread-safe",
                "confirmation": {
                    "type": "workflow_run",
                    "project_id": 13,
                    "series_id": 21,
                    "workflow_type": "t1_deepprep_anat_report",
                },
                "production_task_created": False,
            }
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--workflow-type",
            "t1_deepprep_mock",
            "--agent-workflow-type",
            "t1_deepprep_anat_report",
            "--require-agent-confirmation",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["workflow_type"] == "t1_deepprep_mock"
    assert payload["agent_workflow_type"] == "t1_deepprep_anat_report"
    assert payload["agent_workflow_confirmation"]["workflow_type"] == "t1_deepprep_anat_report"


def test_local_main_flow_smoke_does_not_call_agent_run_unless_confirmation_required(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-model-configured.json"

    def fake_upload_nifti(base, project_id, path):
        return {
            "series": {
                "id": 21,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w",
            },
        }

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1", "sequence_label": "T1w"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {
                "id": 34,
                "project_id": 13,
                "series_id": 21,
                "workflow_type": "t1_deepprep_mock",
                "status": "queued",
            }
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI", "model": "gpt-5.5", "wire_api": "responses"}
        if method == "POST" and url.endswith("/agent/runs"):
            raise AssertionError("agent run should be optional for fast local smoke")
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--output-json", str(output_json)])

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["agent_boundary_status"] == "model_configured_confirmation_not_required"


def test_local_main_flow_smoke_can_pin_rawchat_gpt55_model_profile(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-rawchat.json"

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1", "sequence_label": "T1w"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1", "sequence_label": "T1w"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "rawchat",
                "provider_profile": "rawchat",
                "model": "gpt-5.5",
                "wire_api": "responses",
                "capabilities": {
                    "text": True,
                    "structured_json": True,
                    "model_tool_loop": True,
                },
            }
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--expected-model-provider-profile",
            "rawchat",
            "--expected-model-wire-api",
            "responses",
            "--expected-model-name",
            "gpt-5.5",
            "--require-model-tool-loop",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["model_status"]["provider_profile"] == "rawchat"
    assert payload["model_status"]["model"] == "gpt-5.5"
    assert payload["model_status"]["wire_api"] == "responses"
    assert payload["model_status"]["capabilities"]["model_tool_loop"] is True


def test_local_main_flow_smoke_rejects_wrong_model_profile(monkeypatch):
    smoke = _load_smoke_module()

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider_profile": "deepseek",
                "model": "deepseek-chat",
                "wire_api": "chat_completions",
                "capabilities": {"model_tool_loop": False},
            }
        raise AssertionError(f"unexpected request after model mismatch: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--expected-model-provider-profile",
                "rawchat",
            ]
        )

    assert "model provider_profile deepseek did not match --expected-model-provider-profile rawchat" in str(exc.value)


def test_local_main_flow_smoke_fails_when_agent_confirmation_required_but_model_unconfigured(monkeypatch):
    smoke = _load_smoke_module()

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": False}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-agent-confirmation"])

    assert "agent confirmation required but model gateway is not configured" in str(exc.value)


def test_local_main_flow_smoke_can_require_minimum_rag_documents(monkeypatch):
    smoke = _load_smoke_module()

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": False}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 0}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--min-rag-documents", "1"])

    assert "RAG document_count 0 is below required minimum 1" in str(exc.value)


def test_local_main_flow_smoke_can_rebuild_rag_before_threshold_check(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    calls = []
    output_json = tmp_path / "local-smoke-rag-rebuild.json"

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": False}
        if method == "POST" and url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72, "chunk_count": 260}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--rebuild-rag",
            "--min-rag-documents",
            "60",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert ("POST", "http://api.local/agent/rag/rebuild", None) in calls
    assert payload["rag_rebuild_status"] == "passed"
    assert payload["rag_rebuild"] == {
        "document_count": 72,
        "chunk_count": 260,
        "semantic_index": True,
    }
    assert payload["rag_status"]["document_count"] == 72
    assert payload["rag_status"]["min_documents_required"] == 60


def test_local_main_flow_smoke_can_wait_for_completed_task_and_outputs(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-completed.json"
    task_polls = []

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/tasks/34"):
            task_polls.append(url)
            status = "running" if len(task_polls) == 1 else "completed"
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": status}
        if method == "GET" and url.endswith("/tasks/34/outputs"):
            return [
                {
                    "id": 44,
                    "task_id": 34,
                    "output_type": "json",
                    "relative_path": "summary/result-summary.json",
                    "content_type": "application/json",
                    "size_bytes": 123,
                    "path": "C:/Users/A/private/result-summary.json",
                }
            ]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": False}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--wait-task-completion-timeout-seconds",
            "3",
            "--wait-task-completion-poll-seconds",
            "0",
            "--require-task-outputs",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert len(task_polls) == 2
    assert payload["task_completion_status"] == "passed"
    assert payload["completed_task"]["status"] == "completed"
    assert payload["task_outputs_status"] == "passed"
    assert payload["task_outputs"] == [
        {
            "id": 44,
            "output_type": "json",
            "relative_path": "summary/result-summary.json",
            "content_type": "application/json",
            "size_bytes": 123,
        }
    ]
    assert "C:/Users/A/private" not in json.dumps(payload)


def test_local_main_flow_smoke_can_require_result_contracts(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-result-contracts.json"

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/tasks/34/result-summary"):
            return {
                "contract_version": "result_summary_v1",
                "task_id": 34,
                "project_id": 13,
                "workflow_type": "t1_deepprep_mock",
                "modality": "T1",
                "outputs": {"native_qc": [{"path": "C:/Users/A/private/qc.png"}]},
                "summary_path": "C:/Users/A/private/t1_result_summary.json",
            }
        if method == "GET" and url.endswith("/tasks/34/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 34,
                "project_id": 13,
                "result_summary": {
                    "available": True,
                    "summary_path": "summary/t1_result_summary.json",
                },
                "artifacts": [
                    {
                        "relative_path": "qc/qc_report.html",
                        "download_url": "/tasks/34/artifacts/qc/qc_report.html",
                        "path": "C:/Users/A/private/qc_report.html",
                    }
                ],
            }
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": False}
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-result-summary",
            "--require-artifact-manifest",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["result_summary_status"] == "passed"
    assert payload["result_summary"] == {
        "contract_version": "result_summary_v1",
        "task_id": 34,
        "project_id": 13,
        "workflow_type": "t1_deepprep_mock",
        "modality": "T1",
    }
    assert payload["artifact_manifest_status"] == "passed"
    assert payload["artifact_manifest"] == {
        "contract_version": "artifact_manifest_v1",
        "task_id": 34,
        "project_id": 13,
        "result_summary_available": True,
        "artifact_count": 1,
    }
    assert "C:/Users/A/private" not in json.dumps(payload)


def test_local_main_flow_smoke_writes_safe_failure_json_for_bad_agent_confirmation(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    output_json = tmp_path / "local-smoke-agent-failed.json"

    def fake_upload_nifti(base, project_id, path):
        return {"series": {"id": 21, "project_id": project_id, "modality": "T1"}}

    def fake_request(method, url, payload=None):
        if method == "GET" and url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if method == "POST" and url.endswith("/projects"):
            return {"id": 13, "name": payload["name"]}
        if method == "GET" and url.endswith("/projects/13/series"):
            return [{"id": 21, "project_id": 13, "modality": "T1"}]
        if method == "POST" and url.endswith("/series/21/run"):
            return {"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}
        if method == "GET" and url.endswith("/projects/13/tasks"):
            return [{"id": 34, "project_id": 13, "series_id": 21, "workflow_type": "t1_deepprep_mock", "status": "queued"}]
        if method == "GET" and url.endswith("/agent/model/status"):
            return {"configured": True}
        if method == "POST" and url.endswith("/agent/runs"):
            return {
                "status": "answered",
                "agent_run_id": "run_123",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "answer": "Use C:/Users/A/private/raw.nii.gz and key sk-test-secret.",
                "production_task_created": False,
            }
        if method == "GET" and url.endswith("/agent/rag/status"):
            return {"grounding_policy": {"raw_sources_indexed": False}, "index": {"document_count": 72}}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-agent-confirmation",
                "--output-json",
                str(output_json),
            ]
        )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "agent did not return confirmation_required" in str(exc.value)
    assert payload["status"] == "failed"
    assert payload["agent_boundary_status"] == "failed"
    assert payload["agent_run"] == {
        "agent_run_id": "run_123",
        "status": "answered",
        "intent": "answer_question",
        "selected_skill": "image-agent-operator",
        "production_task_created": False,
    }
    assert "C:/Users/A/private" not in json.dumps(payload)
    assert "sk-test-secret" not in json.dumps(payload)
