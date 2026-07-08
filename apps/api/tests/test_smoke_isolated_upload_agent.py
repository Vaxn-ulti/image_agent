import importlib.util
import json
from pathlib import Path


def _load_smoke_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_isolated_upload_agent.py"
    assert script.is_file(), "isolated upload-agent smoke script is missing"
    spec = importlib.util.spec_from_file_location("smoke_isolated_upload_agent", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_isolated_upload_agent_smoke_writes_safe_payload(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    calls = []
    output_json = tmp_path / "upload-agent-smoke.json"

    class FakeServer:
        base_url = "http://api.local"

        def __enter__(self):
            calls.append(("SERVER_START",))
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("SERVER_STOP",))

    def fake_server(root, port):
        calls.append(("SERVER_ARGS", root.name, port))
        return FakeServer()

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url == "http://api.local/health":
            return {"status": "ok", "app": "image_agent"}
        if method == "GET" and url == "http://api.local/projects":
            return []
        if method == "POST" and url == "http://api.local/projects":
            return {"id": 1, "name": payload["name"]}
        if method == "POST" and url == "http://api.local/agent/runs":
            assert payload == {"project_id": 1, "message": "替我分析一下现在的数据"}
            return {
                "status": "answered",
                "selected_skill": "backend-context-status",
                "response_source": "backend_context",
                "answer": "项目状态概览\n任务 #9001：t1_deepprep_anat_report，状态 运行中，进度 35%\n只读观察：没有启动任何工作流。",
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    def fake_upload(base, project_id, upload_path):
        calls.append(("UPLOAD", base, project_id, upload_path.name))
        return {
            "file": {"id": 7, "original_name": upload_path.name},
            "series": {
                "id": 11,
                "project_id": project_id,
                "modality": "T1",
                "sequence_label": "T1w_MPRAGE",
                "status": "detected",
            },
        }

    def fake_seed(root, project_id, series_id):
        calls.append(("SEED_TASK", root.name, project_id, series_id))
        return {
            "task_id": 9001,
            "project_id": project_id,
            "series_id": series_id,
            "workflow_type": "t1_deepprep_anat_report",
            "status": "running",
            "progress": 35,
        }

    monkeypatch.setattr(smoke, "_isolated_api_server", fake_server)
    monkeypatch.setattr(smoke, "_request_json", fake_request)
    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload)
    monkeypatch.setattr(smoke, "_seed_running_t1_task", fake_seed)

    smoke.main(
        [
            "--root",
            str(tmp_path / "isolated-root"),
            "--port",
            "8123",
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert payload["initial_projects_status"] == "passed_empty"
    assert payload["upload_status"] == "passed"
    assert payload["seed_task_status"] == "passed"
    assert payload["agent_interaction_status"] == "passed"
    assert payload["agent_answer_required_fragments"] == ["项目状态概览", "任务 #", "只读观察"]
    assert payload["uploaded_series"] == {
        "project_id": 1,
        "series_id": 11,
        "modality": "T1",
        "sequence_label": "T1w_MPRAGE",
        "status": "detected",
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "sk-" not in serialized
    assert ("UPLOAD", "http://api.local", 1, "sub-isolated-smoke_T1w.nii.gz") in calls
    assert ("SEED_TASK", "isolated-root", 1, 11) in calls
    assert calls[0] == ("SERVER_ARGS", "isolated-root", 8123)
    assert calls[-1] == ("SERVER_STOP",)
