import json


def _prepare_db(tmp_path, monkeypatch):
    from app.core import config
    from app.db import database

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()


def test_agent_run_ledger_rejects_retrieved_source_query_secret(tmp_path, monkeypatch):
    from app.agent.run_ledger import finish_agent_run, load_agent_run, start_agent_run

    _prepare_db(tmp_path, monkeypatch)
    agent_run_id = start_agent_run(request_type="run", project_id=7, message="safe query")

    finish_agent_run(
        agent_run_id,
        result={
            "status": "answered",
            "retrieved_context": {
                "mode": "local_persistent_index",
                "results": [
                    {
                        "source": "docs/rag/contracts/result-summary.md",
                        "metadata": {"source_type": "rag_contract"},
                    },
                    {
                        "source": "docs/rag/contracts/result-summary.md?api_key=sk-test-secret",
                        "metadata": {"source_type": "rag_contract"},
                    },
                ],
            },
        },
    )

    loaded = load_agent_run(agent_run_id)

    assert loaded is not None
    assert loaded["retrieved_sources"] == [
        {"source": "docs/rag/contracts/result-summary.md", "source_type": "rag_contract"}
    ]
    loaded_json = json.dumps(loaded, ensure_ascii=False)
    assert "api_key" not in loaded_json
    assert "sk-test-secret" not in loaded_json
