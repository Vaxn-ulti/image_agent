from fastapi.testclient import TestClient
import hashlib
import json


def test_agent_model_status_uses_model_gateway(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8080")
    from app.main import app

    result = TestClient(app).get("/agent/model/status")

    assert result.status_code == 200
    body = result.json()
    assert body["provider"] == "OpenAI"
    assert body["configured"] is True
    assert "api_key" not in body


def test_agent_run_returns_answer_and_persists_privacy_safe_ledger(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": "hello",
                "context_project_id": project_context["project_id"],
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "retrieved_context": {
                    "mode": "local_persistent_index",
                    "results": [
                        {
                            "source": "docs/rag/contracts/result-summary.md",
                            "snippet": "raw snippets must stay out of the ledger",
                        }
                    ],
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "hi"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "answered"
    assert body["answer"] == "hello"
    assert body["agent_run_id"]

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
        event_types = [
            item["event_type"]
            for item in conn.execute(
                "SELECT event_type FROM agent_run_events WHERE agent_run_id=? ORDER BY id",
                (body["agent_run_id"],),
            ).fetchall()
        ]

    assert row["request_type"] == "run"
    assert row["project_id"] == 7
    assert row["status"] == "answered"
    assert row["intent"] == "answer_question"
    assert row["selected_skill"] == "image-agent-operator"
    assert row["model_gateway_access"] == "openai_sdk_gateway"
    assert row["message_sha256"] == hashlib.sha256("hi".encode("utf-8")).hexdigest()
    assert "message" not in row.keys()
    assert "hi" not in json.dumps(dict(row), ensure_ascii=False)
    assert event_types == ["agent_run_created", "agent_run_started", "agent_run_completed"]


def test_agent_api_openapi_declares_stable_response_contracts():
    from app.main import app

    schema = TestClient(app).get("/openapi.json").json()

    assert (
        schema["paths"]["/agent/runs"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentRunResponse"
    )
    assert (
        schema["paths"]["/agent/runs/{agent_run_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentRunLookupResponse"
    )
    assert (
        schema["paths"]["/agent/runs/{thread_id}/resume"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/AgentRunResponse"
    )
    assert (
        schema["paths"]["/projects/{project_id}/agent-runs"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ProjectAgentRunHistoryResponse"
    )
    assert (
        schema["paths"]["/chat"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ChatCompatibilityResponse"
    )


def test_agent_run_contract_normalizes_unknown_runner_status(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "surprising_new_status",
                "answer": "hello",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "hi"})

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "agent_run.v1"
    assert body["status"] == "failed"
    assert body["safe_metadata"]["contract_status_normalized_from"] == "surprising_new_status"

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
    assert row["status"] == "failed"


def test_agent_rag_rebuild_endpoint_builds_persistent_index(tmp_path, monkeypatch):
    from app import main
    from app.main import app

    rag_doc = tmp_path / "docs" / "rag" / "contracts" / "result-summary.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text("# Result Summary\nbackend result contract\n", encoding="utf-8")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).post("/agent/rag/rebuild")

    assert result.status_code == 200
    body = result.json()
    assert body["semantic_index"] is True
    assert body["document_count"] == 1
    assert (tmp_path / ".rag_index" / "chunks.jsonl").exists()


def test_agent_rag_status_reports_persistent_index(tmp_path, monkeypatch):
    from app import main
    from app.agent.rag_index import build_local_rag_index
    from app.main import app

    rag_doc = tmp_path / "docs" / "rag" / "contracts" / "result-summary.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text("# Result Summary\nbackend result contract\n", encoding="utf-8")
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).get("/agent/rag/status")

    assert result.status_code == 200
    body = result.json()
    assert body["index"]["manifest_exists"] is True
    assert body["index"]["chunks_exists"] is True
    assert body["index"]["document_count"] == 1
    assert body["index"]["chunk_count"] >= 1
    assert body["index"]["missing_sources"] == []
    assert body["vendor_raw_sources"]["manifest_exists"] is False


def test_agent_rag_status_reports_vendor_raw_source_traceability(tmp_path, monkeypatch):
    from app import main
    from app.agent.rag_index import build_local_rag_index
    from app.main import app

    rag_doc = tmp_path / "docs" / "rag" / "vendor" / "fmriprep_official_container_usage.md"
    raw_root = tmp_path / "docs" / "rag" / "vendor" / "raw-sources"
    raw_doc = raw_root / "fmriprep_usage.html"
    workflow_doc = tmp_path / "docs" / "rag" / "workflows" / "t1_deepprep_anat_report.md"
    rag_doc.parent.mkdir(parents=True)
    raw_root.mkdir(parents=True)
    workflow_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n"
        "Curated summary only.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("<html>official raw source</html>", encoding="utf-8")
    workflow_doc.write_text(
        "# Workflow\n"
        "Grounding: docs/rag/vendor/fmriprep_official_container_usage.md.\n",
        encoding="utf-8",
    )
    raw_bytes = raw_doc.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-06T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": rag_doc.name,
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_doc.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).get("/agent/rag/status")

    assert result.status_code == 200
    raw_status = result.json()["vendor_raw_sources"]
    assert raw_status["manifest_exists"] is True
    assert raw_status["source_count"] == 1
    assert raw_status["vendor_doc_count"] == 1
    assert raw_status["missing_files"] == []
    assert raw_status["hash_mismatches"] == []
    assert raw_status["raw_sources_indexed"] is False
    assert raw_status["curated_provenance_issues"] == []
    assert raw_status["curated_provenance_ok"] is True
    assert [
        {key: value for key, value in item.items() if key != "raw_snapshots"}
        for item in raw_status["curated_sources"]
    ] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_usage.html"],
            "source_types": ["official_docs"],
            "manifest_backed": True,
            "source_url_backed": True,
            "complete": True,
        }
    ]
    assert raw_status["curated_sources"][0]["raw_snapshots"] == [
        {
            "id": "fmriprep_usage",
            "file": "docs/rag/vendor/raw-sources/fmriprep_usage.html",
            "url": "https://fmriprep.org/en/stable/usage.html",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "bytes": len(raw_bytes),
            "retrieved_at": "2026-06-06T00:00:00Z",
            "source_type": "official_docs",
            "status": "downloaded",
        }
    ]
    pointer_status = result.json()["vendor_pointer_integrity"]
    assert pointer_status["ok"] is True
    assert pointer_status["issue_count"] == 0
    catalog = result.json()["vendor_coverage_catalog"]
    assert catalog["status"] == "complete"
    assert catalog["policy"] == "curated summaries are indexed; raw snapshots are provenance evidence only"
    assert catalog["vendor_doc_count"] == 1
    assert catalog["complete_vendor_doc_count"] == 1
    assert catalog["raw_source_count"] == 1
    assert catalog["pointer_integrity_ok"] is True
    assert catalog["vendors"][0]["vendor_doc"] == "fmriprep_official_container_usage.md"
    assert catalog["vendors"][0]["referenced_by"] == ["docs/rag/workflows/t1_deepprep_anat_report.md"]
    assert catalog["vendors"][0]["raw_source_ids"] == ["fmriprep_usage"]
    serialized_catalog = json.dumps(catalog)
    assert "official raw source" not in serialized_catalog
    assert "manifest_path" not in serialized_catalog
    assert "persist_dir" not in serialized_catalog
    assert str(tmp_path) not in serialized_catalog
    assert "raw_snapshots" not in serialized_catalog
    assert "sha256" not in serialized_catalog
    assert "docs/rag/vendor/raw-sources" not in serialized_catalog


def test_agent_run_requires_message():
    from app.main import app

    result = TestClient(app).post("/agent/runs", json={"project_id": None, "message": ""})

    assert result.status_code == 422


def test_agent_run_failure_ledger_redacts_sensitive_error_text(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def run(self, *, message, project_context):
            raise RuntimeError("OPENAI_API_KEY=sk-test-secret failed at C:/Users/A/private/patient-001")

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "patient John Doe"})

    assert result.status_code == 502
    detail_json = json.dumps(result.json()["detail"], ensure_ascii=False)
    assert "agent_run_id" in result.json()["detail"]
    assert "sk-test-secret" not in detail_json
    assert "patient-001" not in detail_json
    assert "C:/Users/A/private" not in detail_json
    assert "patient John Doe" not in detail_json
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT 1").fetchone()
        event_types = [
            item["event_type"]
            for item in conn.execute(
                "SELECT event_type FROM agent_run_events WHERE agent_run_id=? ORDER BY id",
                (row["agent_run_id"],),
            ).fetchall()
        ]

    row_json = json.dumps(dict(row), ensure_ascii=False)
    assert row["status"] == "failed"
    assert row["message_sha256"] == hashlib.sha256("patient John Doe".encode("utf-8")).hexdigest()
    assert "patient John Doe" not in row_json
    assert "sk-test-secret" not in row_json
    assert "patient-001" not in row_json
    assert "C:/Users/A/private" not in row_json
    assert event_types == ["agent_run_created", "agent_run_started", "agent_run_failed"]


def test_agent_run_lookup_returns_safe_ledger_trace(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": "hello",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "recommended_next_step": "do not echo patient Jane Doe from C:/Users/A/private",
                "tool_chain_hint": "OPENAI_API_KEY=sk-test-secret should never be shown",
                "retrieved_context": {
                    "mode": "local_persistent_index",
                    "results": [
                        {
                            "source": "docs/rag/contracts/result-summary.md",
                            "title": "Result Summary",
                            "snippet": "raw RAG snippet must not be exposed",
                            "metadata": {"source_type": "rag_contract"},
                        },
                        {
                            "source": "C:/Users/A/private/patient-001/notes.md",
                            "title": "Sensitive Source",
                            "snippet": "absolute host path must not be exposed",
                        }
                    ],
                },
                "tool_trace": [
                    {
                        "stage": "planner",
                        "tool": "retrieve_reference_context",
                        "status": "ok",
                        "secret": "sk-test-secret",
                    }
                ],
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    run_result = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "patient John Doe"})
    lookup = TestClient(app).get(f"/agent/runs/{run_result.json()['agent_run_id']}")

    assert lookup.status_code == 200
    body = lookup.json()
    assert body["contract_version"] == "agent_run_lookup.v1"
    assert body["agent_run_id"] == run_result.json()["agent_run_id"]
    assert body["status"] == "answered"
    assert body["request_type"] == "run"
    assert body["project_id"] == 7
    assert body["intent"] == "answer_question"
    assert body["selected_skill"] == "image-agent-operator"
    assert body["model_gateway_access"] == "openai_sdk_gateway"
    assert body["message_sha256"] == hashlib.sha256("patient John Doe".encode("utf-8")).hexdigest()
    assert body["retrieved_sources"] == [
        {
            "source": "docs/rag/contracts/result-summary.md",
            "source_type": "rag_contract",
        }
    ]
    assert body["safe_metadata"] == {
        "rag_mode": "local_persistent_index",
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
    }
    assert body["tool_invocations"] == [
        {"stage": "planner", "status": "ok", "tool": "retrieve_reference_context"}
    ]
    assert [event["event_type"] for event in body["events"]] == [
        "agent_run_created",
        "agent_run_started",
        "agent_run_completed",
    ]
    body_json = json.dumps(body, ensure_ascii=False)
    assert "patient John Doe" not in body_json
    assert "patient Jane Doe" not in body_json
    assert "raw RAG snippet must not be exposed" not in body_json
    assert "sk-test-secret" not in body_json
    assert "C:/Users/A/private" not in body_json


def test_agent_run_lookup_returns_404_for_unknown_run(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    result = TestClient(app).get("/agent/runs/agent_run_missing")

    assert result.status_code == 404
    assert result.json()["detail"] == "Agent run not found"


def test_agent_run_lookup_redacts_free_text_error_message(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def run(self, *, message, project_context):
            raise RuntimeError("patient John Doe failed validation in C:/Users/A/private")

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    failed = TestClient(app).post("/agent/runs", json={"project_id": 7, "message": "patient John Doe"})
    lookup = TestClient(app).get(f"/agent/runs/{failed.json()['detail']['agent_run_id']}")

    assert lookup.status_code == 200
    body_json = json.dumps(lookup.json(), ensure_ascii=False)
    assert "patient John Doe" not in body_json
    assert "C:/Users/A/private" not in body_json
    assert lookup.json()["error_message"] == "redacted_error_summary"


def test_agent_run_lookup_resanitizes_persisted_json_fields(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(
              agent_run_id, request_type, thread_id, project_id, status, message_sha256,
              model_gateway_access, retrieved_sources_json, tool_invocations_json,
              safe_metadata_json, error_message, created_at, updated_at, finished_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "agent_run_unsafe",
                "run",
                "thread-unsafe",
                7,
                "failed",
                "hash",
                "openai_sdk_gateway",
                json.dumps(
                    [
                        {
                            "source": "docs/rag/contracts/result-summary.md",
                            "title": "Patient Jane Doe notes",
                            "source_type": "rag_contract",
                            "snippet": "raw RAG snippet",
                        },
                        {
                            "source": "data/projects/7/raw/patient-John-Doe/notes.md",
                            "title": "Sensitive relative path",
                        },
                        {"source": "C:/Users/A/private/patient-001/notes.md"},
                    ]
                ),
                json.dumps(
                    [
                        {
                            "stage": "planner sk-test-secret",
                            "tool": "retrieve_reference_context",
                            "status": "ok",
                            "secret": "sk-test-secret",
                        },
                        {"stage": "resume", "tool": "read_task", "status": "ok sk-test-secret"},
                    ]
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "trace_kind": "privacy-safe lifecycle traceability",
                        "rag_mode": "local_persistent_index",
                        "recommended_next_step": "patient Jane Doe from C:/Users/A/private",
                        "tool_chain_hint": "OPENAI_API_KEY=sk-test-secret",
                        "confirmation_fingerprint": "a" * 64,
                    }
                ),
                "patient Jane Doe in C:/Users/A/private",
                now,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_run_events(agent_run_id, event_type, status, metadata_json, created_at)
            VALUES(?,?,?,?,?)
            """,
            (
                "agent_run_unsafe",
                "agent_run_failed",
                "failed",
                json.dumps(
                    {
                        "thread_id": "thread-unsafe",
                        "workflow_type": "t1_deepprep",
                        "task_id": 12,
                        "secret": "sk-test-secret",
                        "path": "C:/Users/A/private",
                    }
                ),
                now,
            ),
        )

    result = TestClient(app).get("/agent/runs/agent_run_unsafe")

    assert result.status_code == 200
    body = result.json()
    body_json = json.dumps(body, ensure_ascii=False)
    assert "Patient Jane Doe" not in body_json
    assert "patient-John-Doe" not in body_json
    assert "raw RAG snippet" not in body_json
    assert "sk-test-secret" not in body_json
    assert "C:/Users/A/private" not in body_json
    assert body["retrieved_sources"] == [
        {"source": "docs/rag/contracts/result-summary.md", "source_type": "rag_contract"}
    ]
    assert body["safe_metadata"] == {
        "confirmation_fingerprint": "a" * 64,
        "rag_mode": "local_persistent_index",
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
    }
    assert body["tool_invocations"] == [
        {"status": "ok", "tool": "retrieve_reference_context"},
        {"stage": "resume", "tool": "read_task"},
    ]
    assert body["events"][0]["metadata"] == {
        "task_id": 12,
        "thread_id": "thread-unsafe",
        "workflow_type": "t1_deepprep",
    }
    assert body["error_message"] == "redacted_error_summary"


def test_project_agent_runs_list_resanitizes_persisted_json_fields(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(
              agent_run_id, request_type, thread_id, project_id, status, message_sha256,
              model_gateway_access, retrieved_sources_json, tool_invocations_json,
              safe_metadata_json, error_message, created_at, updated_at, finished_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "agent_run_list_unsafe",
                "run",
                "thread-list",
                7,
                "failed",
                "hash",
                "openai_sdk_gateway",
                "[]",
                "[]",
                json.dumps(
                    {
                        "schema_version": 1,
                        "trace_kind": "privacy-safe lifecycle traceability",
                        "rag_mode": "local_persistent_index",
                        "recommended_next_step": "patient Jane Doe",
                    }
                ),
                "patient Jane Doe OPENAI_API_KEY=sk-test-secret",
                now,
                now,
                now,
            ),
        )

    result = TestClient(app).get("/projects/7/agent-runs")

    assert result.status_code == 200
    body = result.json()
    body_json = json.dumps(body, ensure_ascii=False)
    assert "patient Jane Doe" not in body_json
    assert "sk-test-secret" not in body_json
    assert "error_message" not in body_json
    assert body["agent_runs"][0]["safe_metadata"] == {
        "rag_mode": "local_persistent_index",
        "schema_version": 1,
        "trace_kind": "privacy-safe lifecycle traceability",
    }


def test_project_agent_runs_lists_only_safe_project_history(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def run(self, *, message, project_context):
            return {
                "status": "answered",
                "answer": f"raw answer for {message}",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "retrieved_context": {
                    "mode": "local_persistent_index",
                    "results": [
                        {
                            "source": "docs/rag/contracts/agent-run-ledger.md",
                            "title": "Agent Run Ledger",
                            "snippet": f"raw snippet for {message}",
                        }
                    ],
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())
    monkeypatch.setattr(
        main,
        "read_project_context",
        lambda project_id, *, rows_fn, workflows: {"project_id": project_id, "workflows": workflows},
    )

    client = TestClient(app)
    first = client.post("/agent/runs", json={"project_id": 7, "message": "patient one"}).json()
    second = client.post("/agent/runs", json={"project_id": 7, "message": "patient two"}).json()
    other_project = client.post("/agent/runs", json={"project_id": 8, "message": "patient other"}).json()

    result = client.get("/projects/7/agent-runs")

    assert result.status_code == 200
    body = result.json()
    assert body["contract_version"] == "project_agent_run_history.v1"
    assert body["project_id"] == 7
    ids = {item["agent_run_id"] for item in body["agent_runs"]}
    assert ids == {first["agent_run_id"], second["agent_run_id"]}
    assert other_project["agent_run_id"] not in ids
    assert all(item["status"] == "answered" for item in body["agent_runs"])
    assert all(item["project_id"] == 7 for item in body["agent_runs"])
    assert all(item["model_gateway_access"] == "openai_sdk_gateway" for item in body["agent_runs"])
    assert all(item["event_count"] == 3 for item in body["agent_runs"])
    body_json = json.dumps(body, ensure_ascii=False)
    assert "error_message" not in body_json
    assert "patient one" not in body_json
    assert "patient two" not in body_json
    assert "patient other" not in body_json
    assert "raw answer" not in body_json
    assert "raw snippet" not in body_json


def test_project_agent_runs_empty_history_returns_empty_list(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    result = TestClient(app).get("/projects/7/agent-runs")

    assert result.status_code == 200
    assert result.json() == {
        "contract_version": "project_agent_run_history.v1",
        "project_id": 7,
        "agent_runs": [],
    }


def test_legacy_chat_prefers_openai_model_gateway_for_freeform_answers(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")

    class FakeModelGateway:
        def complete_text(self, messages, *, purpose):
            assert purpose == "chat_answer"
            assert any("Backend project context JSON" in item["content"] for item in messages if item["role"] == "user")
            return "OpenAI SDK chat response"

    def fail_deepseek(_message, _context):
        raise AssertionError("DeepSeek fallback should not be called when OpenAI gateway answers")

    monkeypatch.setattr(main, "ModelGateway", lambda: FakeModelGateway())
    monkeypatch.setattr(main, "complete_chat", fail_deepseek)

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-openai-chat"}).json()
    result = client.post("/chat", json={"project_id": project["id"], "message": "please explain this workspace"}).json()

    assert result["contract_version"] == "chat_compat.v1"
    assert result["legacy_endpoint"] is True
    assert result["primary_endpoint"] == "/agent/runs"
    assert result["provider"] == "OpenAI"
    assert result["reply"] == "OpenAI SDK chat response"


def test_agent_rag_query_launchability_uses_matrix_citations(tmp_path, monkeypatch):
    from app import main
    from app.main import app

    matrix = tmp_path / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    matrix.parent.mkdir(parents=True)
    matrix.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: workflow_launchability_matrix\n---\n"
        "# Workflow Launchability Matrix\n"
        "MRIQC is `incubation_reference`, DPABI is `unsupported_external`, and QSIPrep is legacy/explicit.\n"
        "Do not create production tasks from this matrix. `workflow_eligibility` remains authoritative for launchability.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).post(
        "/agent/rag/query",
        json={"query": "Can Image Agent run MRIQC DPABI QSIPrep in production?"},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["intent"] == "launchability"
    assert body["citations"][0]["path"].endswith("workflow_launchability_matrix.md")
    assert "workflow_eligibility remains authoritative" in body["answer"]


def test_agent_rag_query_returns_raw_source_evidence_for_vendor_citations(tmp_path, monkeypatch):
    from app import main
    from app.agent.rag_index import build_local_rag_index
    from app.main import app

    vendor_doc = tmp_path / "docs" / "rag" / "vendor" / "fmriprep_official_outputs.md"
    raw_root = vendor_doc.parent / "raw-sources"
    raw_doc = raw_root / "fmriprep_outputs.html"
    vendor_doc.parent.mkdir(parents=True)
    raw_root.mkdir()
    vendor_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "---\n"
        "# fMRIPrep Official Outputs\n"
        "fMRIPrep writes visual reports for quality review.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("<html>official fMRIPrep outputs</html>", encoding="utf-8")
    raw_bytes = raw_doc.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-07T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": vendor_doc.name,
                        "url": "https://fmriprep.org/en/stable/outputs.html",
                        "file": raw_doc.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    result = TestClient(app).post(
        "/agent/rag/query",
        json={"query": "fMRIPrep visual reports"},
    )

    assert result.status_code == 200
    evidence = result.json()["raw_source_evidence"]
    assert evidence["policy"] == "raw snapshots are traceability evidence and are not indexed wholesale"
    assert evidence["sources"][0]["curated_source"] == "docs/rag/vendor/fmriprep_official_outputs.md"
    assert evidence["sources"][0]["raw_source_ids"] == ["fmriprep_outputs"]
    assert evidence["sources"][0]["raw_snapshots"][0]["sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert evidence["raw_sources_indexed"] is False


def test_chat_launchability_uses_rules_and_does_not_call_model_gateway(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "REPO_ROOT", tmp_path)

    matrix = tmp_path / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    matrix.parent.mkdir(parents=True)
    matrix.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: workflow_launchability_matrix\n---\n"
        "# Workflow Launchability Matrix\n"
        "MRIQC is `incubation_reference`, DPABI is `unsupported_external`, and QSIPrep is legacy/explicit.\n"
        "Do not create production tasks from this matrix. `workflow_eligibility` remains authoritative for launchability.\n",
        encoding="utf-8",
    )

    class ForbiddenModelGateway:
        def complete_text(self, messages, *, purpose):
            raise AssertionError("launchability chat must not call the model gateway")

    def fail_deepseek(_message, _context):
        raise AssertionError("launchability chat must not call fallback model")

    monkeypatch.setattr(main, "ModelGateway", lambda: ForbiddenModelGateway())
    monkeypatch.setattr(main, "complete_chat", fail_deepseek)

    database.init_db()
    client = TestClient(app)
    project = client.post("/projects", json={"name": "P-launchability-chat"}).json()
    result = client.post(
        "/chat",
        json={"project_id": project["id"], "message": "Can Image Agent run MRIQC DPABI QSIPrep in production?"},
    ).json()

    assert result["contract_version"] == "chat_compat.v1"
    assert result["legacy_endpoint"] is True
    assert result["primary_endpoint"] == "/agent/runs"
    assert result["provider"] == "rules"
    assert result["intent"] == "launchability"
    assert "workflow_eligibility remains authoritative" in result["reply"]
    assert result["references"][0]["source"].endswith("workflow_launchability_matrix.md")


def test_agent_resume_returns_ready_to_launch(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    class FakeRunner:
        def resume(self, *, thread_id, approved, confirmation, create_task_fn=None):
            return {
                "status": "ready_to_launch",
                "thread_id": thread_id,
                "backend_tool": "create_workflow_task",
                "tool_input": {
                    "project_id": confirmation["project_id"],
                    "series_id": confirmation["series_id"],
                    "workflow_type": confirmation["workflow_type"],
                },
            }

    monkeypatch.setattr(main, "AgentRunner", lambda: FakeRunner())

    result = TestClient(app).post(
        "/agent/runs/thread-1/resume",
        json={
            "approved": True,
            "confirmation": {
                "type": "workflow_execution",
                "project_id": 1,
                "series_id": 11,
                "workflow_type": "t1_deepprep",
            },
        },
    )

    assert result.status_code == 200
    assert result.json()["status"] == "ready_to_launch"
    assert result.json()["tool_input"]["workflow_type"] == "t1_deepprep"


def test_agent_resume_approved_confirmation_creates_real_task(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(main, "run_pipeline_task", lambda task_id, qsiprep_task_id=None: None)
    store = AgentThreadStore(tmp_path / "agent_threads")
    original_runner = main.AgentRunner
    monkeypatch.setattr(main, "AgentRunner", lambda: original_runner(thread_store=store))

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "t1.nii.gz", str(tmp_path / "t1.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (11, 1, 1, "T1_MPRAGE", 1, "", "T1", "NIFTI", 0.9, json.dumps({}), "detected", database.now_iso()),
        )

    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "action_lane": "fixed_workflow",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": confirmation},
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "task_created"
    assert body["task"]["workflow_type"] == "t1_deepprep"
    assert body["task"]["status"] == "queued"
    assert body["agent_run_id"]

    with database.connect() as conn:
        row = conn.execute("SELECT * FROM agent_runs WHERE agent_run_id=?", (body["agent_run_id"],)).fetchone()
        event_types = [
            item["event_type"]
            for item in conn.execute(
                "SELECT event_type FROM agent_run_events WHERE agent_run_id=? ORDER BY id",
                (body["agent_run_id"],),
            ).fetchall()
        ]

    assert row["request_type"] == "resume"
    assert row["thread_id"] == thread["thread_id"]
    assert row["status"] == "task_created"
    assert row["project_id"] == 1
    assert row["series_id"] == 11
    assert row["workflow_type"] == "t1_deepprep"
    assert row["task_id"] == body["task"]["id"]
    assert row["approved"] == 1
    assert event_types == ["agent_run_created", "agent_run_started", "agent_run_completed"]


def test_agent_resume_rejects_confirmation_mismatch(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app.agent.thread_store import AgentThreadStore
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()

    store = AgentThreadStore(tmp_path / "agent_threads")
    original_runner = main.AgentRunner
    monkeypatch.setattr(main, "AgentRunner", lambda: original_runner(thread_store=store))
    confirmation = {
        "type": "workflow_execution",
        "project_id": 1,
        "series_id": 11,
        "workflow_type": "t1_deepprep_anat_report",
        "action_lane": "fixed_workflow",
    }
    thread = store.create_pending_confirmation(
        confirmation=confirmation,
        decision={"intent": "run_workflow"},
        selected_skill="image-agent-workflow-runner",
        retrieved_context={},
    )

    result = TestClient(app).post(
        f"/agent/runs/{thread['thread_id']}/resume",
        json={"approved": True, "confirmation": {**confirmation, "series_id": 99}},
    )

    assert result.status_code == 200
    assert result.json()["status"] == "blocked"
    assert result.json()["production_task_created"] is False


def test_series_run_rejects_incubation_workflow_without_creating_task(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database
    from app import main
    from app.main import app

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(main, "PROJECTS_ROOT", tmp_path / "projects")

    database.init_db()
    with database.connect() as conn:
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", database.now_iso()))
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (1, 1, "dwi.nii.gz", str(tmp_path / "dwi.nii.gz"), "NIFTI", 1, "x", database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                11,
                1,
                1,
                "DWI",
                1,
                "",
                "DWI",
                "NIFTI",
                0.9,
                json.dumps({"has_bval": True, "has_bvec": True}),
                "detected",
                database.now_iso(),
            ),
        )

    result = TestClient(app).post("/series/11/run", json={"workflow_type": "dwi_qsiprep"})

    assert result.status_code == 400
    assert "Unknown workflow_type" in result.json()["detail"]
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
