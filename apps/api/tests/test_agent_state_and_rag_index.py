from app.agent.prompt_loader import load_prompt_bundle
import hashlib
import json
import sys
import types
from pathlib import Path

from app.agent.rag_index import _parse_frontmatter, build_local_rag_index, rag_vendor_coverage_catalog, rag_vendor_pointer_integrity, retrieve_from_local_rag_index, vendor_raw_source_status
from app.agent.state import AGENT_STATE_FIELDS
from app.workflows.registry import list_workflows


def _curated_without_snapshots(item):
    return {key: value for key, value in item.items() if key != "raw_snapshots"}


def _production_embedding_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [round(int.from_bytes(digest[offset : offset + 2], "big") / 65535, 6) for offset in range(0, 6, 2)]


def test_agent_state_declares_openai_style_orchestration_fields():
    assert {
        "messages",
        "project_id",
        "action_lane",
        "retrieved_context",
        "selected_skill",
        "selected_workflow_type",
        "proposed_toolchain",
        "preflight",
        "confirmation_result",
        "task_status",
        "result_summary",
    } <= set(AGENT_STATE_FIELDS)


def test_prompt_loader_reads_all_instruction_files():
    bundle = load_prompt_bundle()

    assert "planner" in bundle
    assert "responder" in bundle
    assert "safety" in bundle
    assert "tool-use" in bundle
    assert "rag-use" in bundle
    assert "image_agent" in bundle["planner"]


def test_local_rag_index_persists_manifest_for_docs_and_skills(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "result-summary.md"
    skill_doc = root / "docs" / "skills" / "image-agent-operator" / "SKILL.md"
    rag_doc.parent.mkdir(parents=True)
    skill_doc.parent.mkdir(parents=True)
    rag_doc.write_text("# Result Summary\nbackend result-summary contract\n", encoding="utf-8")
    skill_doc.write_text("---\nname: image-agent-operator\n---\n# Operator\nbackend grounding\n", encoding="utf-8")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")

    assert manifest["engine"] in {"elasticsearch_hybrid", "llama_index", "local_manifest"}
    assert manifest["document_count"] == 2
    assert (root / ".rag_index" / "manifest.json").exists()
    assert any(item["source"].endswith("result-summary.md") for item in manifest["documents"])
    assert any(item["source"].endswith("SKILL.md") for item in manifest["documents"])


def test_local_rag_index_persists_semantic_chunks_with_hashes_and_filters(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    skill_ref = root / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry-and-preflight.md"
    rag_doc.parent.mkdir(parents=True)
    skill_ref.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\nmodality: BOLD\n"
        "source_url: https://example.org/bold\nretrieved_date: 2026-06-06\n---\n"
        "# BOLD fMRIPrep XCP-D\nXCP-D outputs connectivity tables and HTML reports.\n",
        encoding="utf-8",
    )
    skill_ref.write_text(
        "---\nsource_type: skill_reference\nskill: image-agent-workflow-runner\npriority: policy\n---\n"
        "# Registry and preflight\nFixed workflows require backend preflight and user confirmation.\n",
        encoding="utf-8",
    )

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    result = retrieve_from_local_rag_index(
        "XCP-D connectivity tables",
        root=root,
        persist_dir=root / ".rag_index",
        filters={"workflow_type": "bold_fmriprep_xcpd_report"},
        limit=3,
    )

    assert manifest["semantic_index"] is True
    if manifest["engine"] == "elasticsearch_hybrid":
        assert manifest["hybrid_search"]["contract_persisted"] is True
        assert (root / ".rag_index" / "elasticsearch" / "mapping.json").exists()
    elif manifest["engine"] == "llama_index":
        assert (root / ".rag_index" / "docstore.json").exists()
    else:
        assert manifest["engine"] == "local_manifest"
        assert (root / ".rag_index" / "chunks.jsonl").exists()
    assert all(item["sha256"] for item in manifest["documents"])
    assert result["mode"] in {"elasticsearch_hybrid_fallback", "llama_index", "local_persistent_index"}
    assert result["results"]
    assert result["results"][0]["metadata"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert "sha256" in result["results"][0]["metadata"]


def test_local_rag_index_writes_elasticsearch_hybrid_contract(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    other_doc = root / "docs" / "rag" / "workflows" / "t1_deepprep_anat_report.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\nmodality: BOLD\n---\n"
        "# BOLD fMRIPrep XCP-D\n"
        "XCP-D produces connectivity metrics, native QC, and report artifacts for BOLD workflows.\n",
        encoding="utf-8",
    )
    other_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: t1_deepprep_anat_report\nmodality: T1\n---\n"
        "# T1 DeepPrep\nDeepPrep produces anatomical reports.\n",
        encoding="utf-8",
    )

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    result = retrieve_from_local_rag_index(
        "BOLD XCP-D connectivity native QC",
        root=root,
        persist_dir=root / ".rag_index",
        filters={"workflow_type": "bold_fmriprep_xcpd_report"},
        limit=2,
    )
    es_root = root / ".rag_index" / "elasticsearch"
    mapping = json.loads((es_root / "mapping.json").read_text(encoding="utf-8"))
    query_template = json.loads((es_root / "hybrid-query-template.json").read_text(encoding="utf-8"))

    assert manifest["engine"] == "elasticsearch_hybrid"
    assert manifest["hybrid_search"]["engine"] == "elasticsearch"
    assert manifest["hybrid_search"]["lexical_retriever"] == "standard"
    assert manifest["hybrid_search"]["dense_vector_field"] == "embedding"
    assert manifest["hybrid_search"]["embedding_provider"] == "local_hashing"
    assert manifest["hybrid_search"]["embedding_model"] == "local-token-hash-v1"
    assert manifest["hybrid_search"]["embedding_production_ready"] is False
    assert manifest["hybrid_search"]["fusion"] == "rrf"
    assert manifest["hybrid_search"]["contract_persisted"] is True
    assert "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion" in manifest["hybrid_search"]["official_sources"]
    assert mapping["mappings"]["properties"]["embedding"]["type"] == "dense_vector"
    assert mapping["mappings"]["properties"]["text"]["type"] == "text"
    assert query_template["retriever"]["rrf"]["retrievers"][0]["standard"]
    assert query_template["retriever"]["rrf"]["retrievers"][1]["knn"]["field"] == "embedding"
    assert (es_root / "bulk.ndjson").exists()
    assert result["mode"] in {"elasticsearch_hybrid_fallback", "llama_index", "local_persistent_index"}
    assert result["results"]
    assert result["results"][0]["metadata"]["workflow_type"] == "bold_fmriprep_xcpd_report"


def test_local_rag_index_skips_raw_source_snapshots_in_fallback_results(tmp_path):
    root = tmp_path / "repo"
    persist_dir = root / ".rag_index"
    persist_dir.mkdir(parents=True)
    (persist_dir / "manifest.json").write_text(
        json.dumps({"engine": "local_manifest", "semantic_index": True, "document_count": 2, "chunk_count": 2}),
        encoding="utf-8",
    )
    (persist_dir / "chunks.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "raw",
                        "source": "docs/rag/vendor/raw-sources/evil_snapshot.html",
                        "title": "Raw Snapshot",
                        "text": "hybrid retrieval contract raw snapshot should not be returned",
                        "metadata": {"source_type": "rag_vendor", "priority_score": 100},
                    }
                ),
                json.dumps(
                    {
                        "id": "safe",
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "safe curated hybrid retrieval contract",
                        "metadata": {"source_type": "rag_contract", "priority_score": 1},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = retrieve_from_local_rag_index(
        "hybrid retrieval contract",
        root=root,
        persist_dir=persist_dir,
        limit=5,
    )

    assert result["results"]
    assert all("raw-sources" not in item["source"] for item in result["results"])
    assert result["results"][0]["source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"


class _FakeElasticsearchIndices:
    def __init__(self, *, exists=False):
        self.exists_value = exists
        self.exists_calls = []
        self.delete_calls = []
        self.create_calls = []

    def exists(self, *, index):
        self.exists_calls.append(index)
        return self.exists_value

    def delete(self, *, index):
        self.delete_calls.append(index)
        self.exists_value = False
        return {"acknowledged": True}

    def create(self, *, index, body):
        self.create_calls.append({"index": index, "body": body})
        self.exists_value = True
        return {"acknowledged": True}


class _FakeElasticsearchClient:
    def __init__(self, *, index_exists=False):
        self.indices = _FakeElasticsearchIndices(exists=index_exists)
        self.bulk_calls = []
        self.search_calls = []
        self.search_response = {"hits": {"hits": []}}

    def bulk(self, *, operations, refresh=False):
        self.bulk_calls.append({"operations": operations, "refresh": refresh})
        return {"errors": False, "items": operations[::2]}

    def search(self, *, index, body):
        self.search_calls.append({"index": index, "body": body})
        return self.search_response


class _FakeElasticsearchObjectResponse:
    def __init__(self, body):
        self.body = body


class _FakeElasticsearchObjectResponseClient(_FakeElasticsearchClient):
    def bulk(self, *, operations, refresh=False):
        self.bulk_calls.append({"operations": operations, "refresh": refresh})
        return _FakeElasticsearchObjectResponse({"errors": False, "items": operations[::2]})

    def search(self, *, index, body):
        self.search_calls.append({"index": index, "body": body})
        return _FakeElasticsearchObjectResponse(self.search_response)


class _FakeElasticsearchBulkErrorObjectResponseClient(_FakeElasticsearchClient):
    def bulk(self, *, operations, refresh=False):
        self.bulk_calls.append({"operations": operations, "refresh": refresh})
        return _FakeElasticsearchObjectResponse({"errors": True, "items": [{"index": {"status": 400}}]})


class _FailingElasticsearchIndices:
    def exists(self, *, index):
        raise RuntimeError(
            "failed https://elastic:super-secret-password@es.local:9200 "
            "Authorization: ApiKey sk-elasticsearch-secret-token"
        )


class _FailingElasticsearchClient:
    def __init__(self):
        self.indices = _FailingElasticsearchIndices()


def test_local_rag_index_does_not_write_local_hash_vectors_to_elasticsearch_client(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    raw_doc = root / "docs" / "rag" / "vendor" / "raw-sources" / "raw.md"
    rag_doc.parent.mkdir(parents=True)
    raw_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\n---\n"
        "# BOLD fMRIPrep XCP-D\nElasticsearch hybrid search should index curated chunks only.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("# Raw source\nthis raw provenance snapshot must not be indexed\n", encoding="utf-8")
    client = _FakeElasticsearchClient()

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index", elasticsearch_client=client)

    assert manifest["hybrid_search"]["configured"] is True
    assert manifest["hybrid_search"]["persisted"] is False
    assert manifest["hybrid_search"]["mode"] == "embedding_required"
    assert manifest["hybrid_search"]["indexed_chunk_count"] == 0
    assert manifest["hybrid_search"]["embedding_provider"] == "local_hashing"
    assert manifest["hybrid_search"]["embedding_production_ready"] is False
    assert client.indices.create_calls == []
    assert client.bulk_calls == []
    assert (root / ".rag_index" / "elasticsearch" / "bulk.ndjson").exists()


def test_local_rag_index_uses_configured_embedding_provider_for_elasticsearch_vectors(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nConfigured embedding provider should supply production vectors.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    def embedding_vector(text: str) -> list[float]:
        if text.strip() == "production vector query":
            return [0.1, 0.2, 0.3]
        return [0.25, 0.5, 0.75]

    manifest = build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert manifest["hybrid_search"]["dense_vector_dims"] == 3
    assert manifest["hybrid_search"]["embedding_provider"] == "openai"
    assert manifest["hybrid_search"]["embedding_model"] == "text-embedding-3-small"
    assert manifest["hybrid_search"]["embedding_production_ready"] is True
    assert client.indices.create_calls[0]["body"]["mappings"]["properties"]["embedding"]["dims"] == 3
    assert client.bulk_calls[0]["refresh"] == "wait_for"
    indexed_document = client.bulk_calls[0]["operations"][1]
    assert indexed_document["embedding"] == [0.25, 0.5, 0.75]
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 9.5,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Configured embedding provider should supply production vectors.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                }
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "production vector query",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
        embedding_vector_fn=embedding_vector,
    )

    assert result["mode"] == "elasticsearch_hybrid"
    assert result["elasticsearch_hybrid_query"]["lexical_retriever"] == "standard"
    assert result["elasticsearch_hybrid_query"]["vector_retriever"] == "knn"
    assert result["elasticsearch_hybrid_query"]["dense_vector_field"] == "embedding"
    assert result["elasticsearch_hybrid_query"]["fusion"] == "rrf"

    retrievers = client.search_calls[0]["body"]["retriever"]["rrf"]["retrievers"]
    assert retrievers[1]["knn"]["query_vector"] == [0.1, 0.2, 0.3]


def test_local_rag_index_recreates_existing_elasticsearch_index_on_rebuild(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nRebuild should remove stale Elasticsearch docs.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient(index_exists=True)

    manifest = build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.25, 0.5, 0.75],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert manifest["hybrid_search"]["persisted"] is True
    assert manifest["hybrid_search"]["mode"] == "connected"
    assert client.indices.exists_calls == ["image_agent_rag"]
    assert client.indices.delete_calls == ["image_agent_rag"]
    assert client.indices.create_calls[0]["index"] == "image_agent_rag"
    assert client.bulk_calls[0]["refresh"] == "wait_for"
    indexed_sources = [
        operation["source"]
        for operation in client.bulk_calls[0]["operations"]
        if isinstance(operation, dict) and operation.get("source")
    ]
    assert indexed_sources == ["docs/rag/contracts/elasticsearch-hybrid-search.md"]


def test_local_rag_index_uses_env_configured_elasticsearch_index(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nRelease-specific Elasticsearch indexes keep acceptance evidence isolated.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient(index_exists=True)
    monkeypatch.setenv("IMAGE_AGENT_ELASTICSEARCH_INDEX", "image_agent_rag_release_20260619")

    manifest = build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.25, 0.5, 0.75],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert manifest["hybrid_search"]["index"] == "image_agent_rag_release_20260619"
    assert client.indices.exists_calls == ["image_agent_rag_release_20260619"]
    assert client.indices.delete_calls == ["image_agent_rag_release_20260619"]
    assert client.indices.create_calls[0]["index"] == "image_agent_rag_release_20260619"
    assert client.bulk_calls[0]["operations"][0]["index"]["_index"] == "image_agent_rag_release_20260619"


def test_local_rag_index_uses_env_configured_openai_embedding_provider(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nEnvironment configured embeddings should drive Elasticsearch vectors.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    calls = []

    class FakeEmbeddings:
        def create(self, *, model, input):
            calls.append({"model": model, "input": input})
            text = str(input)
            vector = [0.9, 0.8, 0.7] if "query" in text else [0.4, 0.5, 0.6]
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=vector)])

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, http_client=None):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.http_client = http_client
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://embedding.example/v1")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index", elasticsearch_client=client)

    assert manifest["hybrid_search"]["embedding_provider"] == "openai"
    assert manifest["hybrid_search"]["embedding_model"] == "text-embedding-3-small"
    assert manifest["hybrid_search"]["embedding_transport"] == "sdk"
    assert manifest["hybrid_search"]["embedding_endpoint_configured"] is True
    assert manifest["hybrid_search"]["embedding_production_ready"] is True
    assert client.bulk_calls[0]["operations"][1]["embedding"] == [0.4, 0.5, 0.6]

    retrieve_from_local_rag_index(
        "query vector",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
    )

    retrievers = client.search_calls[0]["body"]["retriever"]["rrf"]["retrievers"]
    assert retrievers[1]["knn"]["query_vector"] == [0.9, 0.8, 0.7]
    assert calls


def test_local_rag_index_openai_embedding_provider_ignores_ambient_proxy_by_default(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nEmbedding requests to rawchat should be direct.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    captured = {}

    class FakeEmbeddings:
        def create(self, *, model, input):
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.4, 0.5, 0.6])])

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, http_client=None):
            captured["http_client_present"] = http_client is not None
            captured["trust_env"] = getattr(http_client, "trust_env", None)
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "rawchat")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://rawchat.cn/codex")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index", elasticsearch_client=client)

    assert manifest["hybrid_search"]["embedding_transport"] == "sdk"
    assert captured == {"http_client_present": True, "trust_env": False}


def test_local_rag_index_uses_openai_compatible_http_embedding_provider_without_sdk(tmp_path, monkeypatch):
    import urllib.request

    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nHTTP embeddings should drive connected Elasticsearch without the SDK.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    calls = []

    class BlockingOpenAIImport:
        def __getattr__(self, name):
            raise ImportError("openai SDK unavailable")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            text = self.payload["input"]
            vector = [0.9, 0.8, 0.7] if "query" in text else [0.4, 0.5, 0.6]
            return json.dumps({"data": [{"embedding": vector}]}).encode("utf-8")

    class FakeOpener:
        def open(self, request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            calls.append(
                {
                    "url": request.full_url,
                    "headers": dict(request.header_items()),
                    "payload": payload,
                    "timeout": timeout,
                }
            )
            response = FakeResponse()
            response.payload = payload
            return response

    def fake_build_opener(*_handlers):
        return FakeOpener()

    monkeypatch.setitem(sys.modules, "openai", BlockingOpenAIImport())
    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_TIMEOUT_SECONDS", "17")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index", elasticsearch_client=client)

    assert manifest["hybrid_search"]["mode"] == "connected"
    assert manifest["hybrid_search"]["embedding_provider"] == "openai"
    assert manifest["hybrid_search"]["embedding_model"] == "text-embedding-3-small"
    assert manifest["hybrid_search"]["embedding_transport"] == "openai_compatible_http"
    assert manifest["hybrid_search"]["embedding_endpoint_configured"] is True
    assert manifest["hybrid_search"]["embedding_production_ready"] is True
    assert client.bulk_calls[0]["operations"][1]["embedding"] == [0.4, 0.5, 0.6]
    assert calls[0]["url"] == "https://embedding.example/v1/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer embedding-secret"
    assert calls[0]["payload"] == {
        "model": "text-embedding-3-small",
        "input": "# Elasticsearch Hybrid Search\nHTTP embeddings should drive connected Elasticsearch without the SDK.",
    }
    assert calls[0]["timeout"] == 17

    retrieve_from_local_rag_index(
        "query vector",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
    )

    retrievers = client.search_calls[0]["body"]["retriever"]["rrf"]["retrievers"]
    assert retrievers[1]["knn"]["query_vector"] == [0.9, 0.8, 0.7]


def test_local_rag_index_http_embedding_fallback_uses_no_proxy_opener(tmp_path, monkeypatch):
    import urllib.request

    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nHTTP embedding fallback should bypass ambient proxy.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    captured = {"open_calls": 0, "proxy_handler_seen": False}

    class BlockingOpenAIImport:
        def __getattr__(self, name):
            raise ImportError("openai SDK unavailable")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            text = self.payload["input"]
            vector = [0.9, 0.8, 0.7] if "query" in text else [0.4, 0.5, 0.6]
            return json.dumps({"data": [{"embedding": vector}]}).encode("utf-8")

    class FakeOpener:
        def open(self, request, timeout):
            captured["open_calls"] += 1
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            response = FakeResponse()
            response.payload = json.loads(request.data.decode("utf-8"))
            return response

    def fake_build_opener(*handlers):
        captured["proxy_handler_seen"] = any(type(handler).__name__ == "ProxyHandler" for handler in handlers)
        return FakeOpener()

    monkeypatch.setitem(sys.modules, "openai", BlockingOpenAIImport())
    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://rawchat.cn/codex")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_TIMEOUT_SECONDS", "17")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index", elasticsearch_client=client)

    assert manifest["hybrid_search"]["embedding_transport"] == "openai_compatible_http"
    assert captured["proxy_handler_seen"] is True
    assert captured["open_calls"] >= 1
    assert captured["url"] == "https://rawchat.cn/codex/embeddings"
    assert captured["timeout"] == 17


def test_local_rag_index_safely_downgrades_when_configured_embedding_provider_fails(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nFailed production embeddings must not leak secrets.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()

    class FakeEmbeddings:
        def create(self, *, model, input):
            raise RuntimeError(
                "embedding failed for https://embedding.example/v1 "
                "Authorization: Bearer embedding-secret-token"
            )

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, http_client=None):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.http_client = http_client
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret-token")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://embedding.example/v1")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index", elasticsearch_client=client)
    persisted = json.loads((root / ".rag_index" / "manifest.json").read_text(encoding="utf-8"))
    serialized = json.dumps({"manifest": manifest, "persisted": persisted}, sort_keys=True)

    assert manifest["hybrid_search"]["mode"] == "embedding_error"
    assert manifest["hybrid_search"]["persisted"] is False
    assert manifest["hybrid_search"]["indexed_chunk_count"] == 0
    assert manifest["hybrid_search"]["embedding_provider"] == "openai"
    assert manifest["hybrid_search"]["embedding_model"] == "text-embedding-3-small"
    assert manifest["hybrid_search"]["embedding_transport"] == "sdk"
    assert manifest["hybrid_search"]["embedding_endpoint_configured"] is True
    assert manifest["hybrid_search"]["embedding_production_ready"] is False
    assert manifest["hybrid_search"]["embedding_error"]
    assert "embedding-secret-token" not in serialized
    assert "Authorization" not in serialized
    assert "https://embedding.example/v1" not in serialized
    assert "[redacted-secret]" in serialized
    assert client.bulk_calls == []
    assert (root / ".rag_index" / "elasticsearch" / "bulk.ndjson").exists()


def test_retrieve_from_local_rag_index_skips_elasticsearch_when_query_embedding_provider_fails(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nRRF query evidence and production embedding boundary.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()

    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.1, 0.2, 0.3],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_calls.clear()

    class FakeEmbeddings:
        def create(self, *, model, input):
            raise RuntimeError("Authorization: Bearer embedding-secret-token at https://embedding.example/v1")

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_API_KEY", "embedding-secret-token")
    monkeypatch.setenv("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", "https://embedding.example/v1")

    result = retrieve_from_local_rag_index(
        "Elasticsearch hybrid query evidence",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
    )

    assert result["mode"] == "elasticsearch_hybrid_fallback"
    assert result["results"]
    assert client.search_calls == []


def test_retrieve_from_local_rag_index_skips_elasticsearch_when_runtime_embedding_is_unconfigured(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nRuntime query embeddings must be production configured.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 12.5,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Runtime query embeddings must be production configured.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                }
            ]
        }
    }
    client.search_calls.clear()

    result = retrieve_from_local_rag_index(
        "Runtime query embeddings production configured",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
    )

    assert result["mode"] == "elasticsearch_hybrid_fallback"
    assert result["results"]
    assert client.search_calls == []


def test_retrieve_from_local_rag_index_skips_elasticsearch_when_runtime_embedding_model_differs_from_manifest(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nRuntime query embeddings must match the connected index manifest.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 12.5,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Runtime query embeddings must match the connected index manifest.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                }
            ]
        }
    }
    client.search_calls.clear()

    result = retrieve_from_local_rag_index(
        "Runtime query embeddings manifest model",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-large",
    )

    assert result["mode"] == "elasticsearch_hybrid_fallback"
    assert result["results"]
    assert client.search_calls == []


def test_local_rag_index_redacts_elasticsearch_connection_errors(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "# Elasticsearch Hybrid Search\nBM25 dense-vector kNN RRF retrieval contract.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IMAGE_AGENT_ELASTICSEARCH_URL", "https://elastic:super-secret-password@es.local:9200")
    monkeypatch.setenv("IMAGE_AGENT_ELASTICSEARCH_API_KEY", "sk-elasticsearch-secret-token")

    manifest = build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=_FailingElasticsearchClient(),
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    persisted = json.loads((root / ".rag_index" / "manifest.json").read_text(encoding="utf-8"))
    serialized = json.dumps({"manifest": manifest, "persisted": persisted}, sort_keys=True)

    assert manifest["hybrid_search"]["mode"] == "connection_error"
    assert "super-secret-password" not in serialized
    assert "sk-elasticsearch-secret-token" not in serialized
    assert "Authorization" not in serialized
    assert "elastic:super-secret-password" not in serialized
    assert "[redacted-secret]" in serialized


def test_retrieve_from_local_rag_index_uses_elasticsearch_hybrid_client_when_persisted(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\n---\n"
        "# BOLD fMRIPrep XCP-D\nNative QC and connectivity report evidence.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 12.5,
                    "_source": {
                        "source": "docs/rag/workflows/bold_fmriprep_xcpd_report.md",
                        "title": "BOLD fMRIPrep XCP-D",
                        "text": "Native QC and connectivity report evidence.",
                        "source_type": "rag_workflow",
                        "workflow_type": "bold_fmriprep_xcpd_report",
                        "priority_score": 50,
                        "metadata": {
                            "source_type": "rag_workflow",
                            "workflow_type": "bold_fmriprep_xcpd_report",
                        },
                    },
                }
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "BOLD native QC connectivity",
        root=root,
        persist_dir=root / ".rag_index",
        filters={"workflow_type": "bold_fmriprep_xcpd_report"},
        limit=2,
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert result["mode"] == "elasticsearch_hybrid"
    assert result["results"][0]["metadata"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert client.search_calls[0]["index"] == "image_agent_rag"
    retrievers = client.search_calls[0]["body"]["retriever"]["rrf"]["retrievers"]
    assert retrievers[0]["standard"]["query"]["bool"]["filter"] == [
        {"term": {"workflow_type": "bold_fmriprep_xcpd_report"}}
    ]
    assert retrievers[1]["knn"]["filter"] == [{"term": {"workflow_type": "bold_fmriprep_xcpd_report"}}]


def test_retrieve_from_local_rag_index_uses_manifest_elasticsearch_index_for_query_evidence(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nCustom deployment index evidence must match query evidence.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    manifest_path = root / ".rag_index" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["hybrid_search"]["index"] = "image_agent_rag_release_20260619"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 7.5,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Custom deployment index evidence must match query evidence.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                }
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "Custom deployment index evidence",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert result["mode"] == "elasticsearch_hybrid"
    assert client.search_calls[0]["index"] == "image_agent_rag_release_20260619"
    assert result["elasticsearch_hybrid_query"]["index"] == "image_agent_rag_release_20260619"


def test_local_rag_index_handles_elasticsearch_python_object_responses(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nOfficial Python client response objects should be accepted.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchObjectResponseClient()
    manifest = build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 9.25,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Official Python client response objects should be accepted.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                }
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "Official Python client response objects",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert manifest["hybrid_search"]["persisted"] is True
    assert manifest["hybrid_search"]["mode"] == "connected"
    assert result["mode"] == "elasticsearch_hybrid"
    assert result["results"][0]["source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"
    assert result["results"][0]["metadata"]["source_type"] == "rag_contract"


def test_retrieve_from_elasticsearch_hybrid_falls_back_when_rrf_license_is_unavailable(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nRRF license fallback should still use BM25 plus kNN.",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    class RrfLicenseError(Exception):
        pass

    original_search = client.search

    def search_with_rrf_license_error(*, index, body):
        if "retriever" in body:
            raise RrfLicenseError("current license is non-compliant for [Reciprocal Rank Fusion (RRF)]")
        client.search_response = {
            "hits": {
                "hits": [
                    {
                        "_score": 8.0,
                        "_source": {
                            "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                            "title": "Elasticsearch Hybrid Search",
                            "text": "RRF license fallback should still use BM25 plus kNN.",
                            "metadata": {"source_type": "rag_contract"},
                        },
                    }
                ]
            }
        }
        return original_search(index=index, body=body)

    client.search = search_with_rrf_license_error

    result = retrieve_from_local_rag_index(
        "RRF license fallback",
        root=root,
        persist_dir=root / ".rag_index",
        limit=1,
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert result["mode"] == "elasticsearch_hybrid"
    assert result["results"][0]["source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"
    assert result["elasticsearch_hybrid_query"]["fusion"] == "query_plus_knn"
    assert result["elasticsearch_hybrid_query"]["rrf_unavailable_reason"] == "license_non_compliant"
    assert "query" in client.search_calls[-1]["body"]
    assert "knn" in client.search_calls[-1]["body"]


def test_retrieve_from_elasticsearch_hybrid_skips_hits_without_safe_source(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    skill_ref = root / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry-and-preflight.md"
    rag_doc.parent.mkdir(parents=True)
    skill_ref.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nSafe source paths are required for production citations.\n",
        encoding="utf-8",
    )
    skill_ref.write_text(
        "---\nsource_type: skill_reference\n---\n"
        "# Registry and Preflight\nFixed workflow launches require registry and preflight gates.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {"_score": 30.0, "_source": {"title": "Missing source", "text": "unsafe missing source"}},
                {
                    "_score": 29.0,
                    "_source": {
                        "source": "C:/secrets/backend.log",
                        "title": "Absolute source",
                        "text": "unsafe absolute source",
                    },
                },
                {
                    "_score": 28.0,
                    "_source": {
                        "source": "../outside.md",
                        "title": "Traversal source",
                        "text": "unsafe traversal source",
                    },
                },
                {
                    "_score": 27.0,
                    "_source": {
                        "source": "https://example.org/vendor.md",
                        "title": "URL source",
                        "text": "unsafe URL source",
                    },
                },
                {
                    "_score": 26.0,
                    "_source": {
                        "source": "apps/api/README.md",
                        "title": "App source",
                        "text": "outside the indexed RAG and skill source domains",
                    },
                },
                {
                    "_score": 25.0,
                    "_source": {
                        "source": "docs/rag/vendor/raw-sources/raw.md",
                        "title": "Raw source",
                        "text": "raw source snapshots are provenance only",
                    },
                },
                {
                    "_score": 10.0,
                    "_source": {
                        "source": "docs/skills/image-agent-workflow-runner/references/registry-and-preflight.md",
                        "title": "Registry and Preflight",
                        "text": "Fixed workflow launches require registry and preflight gates.",
                        "metadata": {"source_type": "skill_reference"},
                    },
                },
                {
                    "_score": 9.0,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Safe source paths are required for production citations.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                },
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "Safe source paths production citations",
        root=root,
        persist_dir=root / ".rag_index",
        limit=5,
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert result["mode"] == "elasticsearch_hybrid"
    assert [item["source"] for item in result["results"]] == [
        "docs/skills/image-agent-workflow-runner/references/registry-and-preflight.md",
        "docs/rag/contracts/elasticsearch-hybrid-search.md"
    ]


def test_retrieve_from_elasticsearch_hybrid_ignores_stale_hits_when_current_hits_remain(tmp_path):
    root = tmp_path / "repo"
    current_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    current_doc.parent.mkdir(parents=True)
    current_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nCurrent manifest source should win.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 50.0,
                    "_source": {
                        "source": "docs/rag/workflows/stale-but-safe.md",
                        "title": "Stale Safe Workflow",
                        "text": "This safe-looking hit came from an old Elasticsearch index.",
                        "metadata": {"source_type": "rag_workflow", "workflow_type": "stale_safe_workflow"},
                    },
                },
                {
                    "_score": 10.0,
                    "_source": {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "title": "Elasticsearch Hybrid Search",
                        "text": "Current manifest source should win.",
                        "metadata": {"source_type": "rag_contract"},
                    },
                },
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "Current manifest source",
        root=root,
        persist_dir=root / ".rag_index",
        limit=5,
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert result["mode"] == "elasticsearch_hybrid"
    assert [item["source"] for item in result["results"]] == ["docs/rag/contracts/elasticsearch-hybrid-search.md"]


def test_retrieve_from_elasticsearch_hybrid_falls_back_when_no_safe_hits(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_contract\n---\n"
        "# Elasticsearch Hybrid Search\nFallback usable citation evidence remains in curated local docs.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchClient()
    build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    client.search_response = {
        "hits": {
            "hits": [
                {"_score": 30.0, "_source": {"title": "Missing source", "text": "unsafe missing source"}},
                {
                    "_score": 29.0,
                    "_source": {
                        "source": "https://example.org/vendor.md",
                        "title": "URL source",
                        "text": "unsafe URL source",
                    },
                },
                {
                    "_score": 28.0,
                    "_source": {
                        "source": "docs/rag/vendor/raw-sources/raw.md",
                        "title": "Raw source",
                        "text": "raw source snapshots are provenance only",
                    },
                },
            ]
        }
    }

    result = retrieve_from_local_rag_index(
        "Fallback usable citation evidence",
        root=root,
        persist_dir=root / ".rag_index",
        limit=2,
        elasticsearch_client=client,
        embedding_vector_fn=lambda text: [0.2, 0.4, 0.6],
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert client.search_calls
    assert result["mode"] == "elasticsearch_hybrid_fallback"
    assert [item["source"] for item in result["results"]] == [
        "docs/rag/contracts/elasticsearch-hybrid-search.md"
    ]


def test_local_rag_index_rejects_elasticsearch_object_bulk_errors(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "elasticsearch-hybrid-search.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "# Elasticsearch Hybrid Search\nBulk errors from object responses must not pass acceptance.\n",
        encoding="utf-8",
    )
    client = _FakeElasticsearchBulkErrorObjectResponseClient()

    manifest = build_local_rag_index(
        root=root,
        persist_dir=root / ".rag_index",
        elasticsearch_client=client,
        embedding_vector_fn=_production_embedding_vector,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )

    assert manifest["hybrid_search"]["persisted"] is False
    assert manifest["hybrid_search"]["mode"] == "bulk_errors"
    assert manifest["hybrid_search"]["indexed_chunk_count"] == 0


def test_local_rag_index_excludes_vendor_raw_sources_even_when_markdown(tmp_path):
    root = tmp_path / "repo"
    curated = root / "docs" / "rag" / "vendor" / "openai_official_responses_function_tools.md"
    raw_root = root / "docs" / "rag" / "vendor" / "raw-sources"
    raw_source = raw_root / "openai_python_sdk_readme.md"
    curated.parent.mkdir(parents=True)
    raw_root.mkdir(parents=True)
    curated.write_text("# OpenAI SDK Contract\nofficial OpenAI Python SDK responses.create\n", encoding="utf-8")
    raw_source.write_text("# Raw SDK README\nunique_raw_sdk_phrase_should_not_be_indexed\n", encoding="utf-8")
    raw_bytes = raw_source.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "openai_python_sdk_readme",
                        "vendor_doc": "openai_official_responses_function_tools.md",
                        "url": "https://raw.githubusercontent.com/openai/openai-python/main/README.md",
                        "file": raw_source.name,
                        "source_type": "official_repository",
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

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    status = vendor_raw_source_status(root=root, indexed_sources=[doc["source"] for doc in manifest["documents"]])
    result = retrieve_from_local_rag_index(
        "unique_raw_sdk_phrase_should_not_be_indexed",
        root=root,
        persist_dir=root / ".rag_index",
        limit=5,
    )

    assert [doc["source"] for doc in manifest["documents"]] == ["docs/rag/vendor/openai_official_responses_function_tools.md"]
    assert status["raw_sources_indexed"] is False
    assert all("docs/rag/vendor/raw-sources" not in item["source"] for item in result["results"])


def test_local_rag_index_infers_vendor_source_type_from_vendor_path(tmp_path):
    root = tmp_path / "repo"
    vendor_doc = root / "docs" / "rag" / "vendor" / "fsl_official_fast_dti_tools.md"
    vendor_doc.parent.mkdir(parents=True)
    vendor_doc.write_text(
        "# FSL Official Fast DTI Tools\n"
        "Official FSL dtifit and eddy references for fast DTI workflow grounding.\n",
        encoding="utf-8",
    )

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    result = retrieve_from_local_rag_index(
        "FSL dtifit eddy",
        root=root,
        persist_dir=root / ".rag_index",
        filters={"source_type": "rag_vendor"},
        limit=3,
    )

    document = manifest["documents"][0]
    assert document["metadata"]["source_type"] == "rag_vendor"
    assert document["metadata"]["priority_score"] == 50
    assert result["results"]
    assert result["results"][0]["metadata"]["source_type"] == "rag_vendor"


def test_local_rag_index_parses_frontmatter_lists_for_workflow_grounding(tmp_path):
    root = tmp_path / "repo"
    workflow_doc = root / "docs" / "rag" / "workflows" / "t1_deepprep_anat_report.md"
    workflow_doc.parent.mkdir(parents=True)
    workflow_doc.write_text(
        "---\n"
        "source_type: rag_workflow\n"
        "workflow_type: t1_deepprep_anat_report\n"
        "official_grounding:\n"
        "  - docs/rag/vendor/deepprep_official_container_usage.md\n"
        "  - docs/rag/vendor/freesurfer_official_container_reconall.md\n"
        "expected_artifacts:\n"
        "  - reports/index.html\n"
        "  - reports/report_manifest.json\n"
        "---\n"
        "# T1 DeepPrep Anatomy Report\n"
        "DeepPrep and FreeSurfer outputs ground native anatomy QC and report artifacts.\n",
        encoding="utf-8",
    )

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    result = retrieve_from_local_rag_index(
        "DeepPrep FreeSurfer anatomy QC",
        root=root,
        persist_dir=root / ".rag_index",
        filters={"official_grounding": "docs/rag/vendor/deepprep_official_container_usage.md"},
        limit=3,
    )

    metadata = manifest["documents"][0]["metadata"]
    assert metadata["official_grounding"] == [
        "docs/rag/vendor/deepprep_official_container_usage.md",
        "docs/rag/vendor/freesurfer_official_container_reconall.md",
    ]
    assert metadata["expected_artifacts"] == ["reports/index.html", "reports/report_manifest.json"]
    assert result["results"]
    assert result["results"][0]["metadata"]["official_grounding"] == metadata["official_grounding"]


def test_real_workflow_rag_docs_embed_public_workflow_metadata():
    repo_root = Path(__file__).resolve().parents[3]
    required_fields = {
        "display_name",
        "capability_summary",
        "workflow_family",
        "workflow_role",
        "runtime_workflow_type",
        "agent_selectable",
        "pipeline_stages",
        "primary_outputs",
        "qc_outputs",
        "report_outputs",
        "limitations",
        "is_report_only",
    }

    for workflow in list_workflows(lane="fixed_workflow", agent_selectable=True):
        workflow_type = workflow["type"]
        doc_path = repo_root / "docs" / "rag" / "workflows" / f"{workflow_type}.md"
        assert doc_path.exists(), f"{workflow_type} missing RAG workflow doc"
        metadata, _body = _parse_frontmatter(doc_path.read_text(encoding="utf-8"))

        assert required_fields <= set(metadata), f"{workflow_type} RAG frontmatter missing public workflow metadata"
        assert metadata["workflow_type"] == workflow_type
        assert metadata["display_name"] == workflow["display_name"]
        assert metadata["capability_summary"] == workflow["capability_summary"]
        assert metadata["workflow_family"] == workflow["workflow_family"]
        assert metadata["workflow_role"] == workflow["workflow_role"]
        assert metadata["runtime_workflow_type"] == workflow["runtime_workflow_type"]
        assert metadata["agent_selectable"] == "true"
        assert metadata["is_report_only"] == "false"
        for key in ("pipeline_stages", "primary_outputs", "qc_outputs", "report_outputs", "limitations"):
            assert isinstance(metadata[key], list) and metadata[key], f"{workflow_type} {key} must be indexed"


def test_vendor_raw_source_status_verifies_hashes_without_indexing_raw_html(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    raw_root.mkdir(parents=True)
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "generated_at": "2026-06-06T00:00:00Z",
        "sources": [
            {
                "id": "fmriprep_usage",
                "vendor_doc": "fmriprep_official_container_usage.md",
                "url": "https://fmriprep.org/en/stable/usage.html",
                "file": raw_file.name,
                "source_type": "official_docs",
                "retrieved_at": "2026-06-06T00:00:00Z",
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "bytes": len(raw_bytes),
                "status": "downloaded",
            }
        ],
    }
    (raw_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["manifest_exists"] is True
    assert status["source_count"] == 1
    assert status["vendor_doc_count"] == 1
    assert status["missing_files"] == []
    assert status["hash_mismatches"] == []
    assert status["raw_sources_indexed"] is False
    assert status["curated_provenance_issues"] == []
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
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
    assert status["curated_sources"][0]["raw_snapshots"] == [
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


def test_rag_vendor_pointer_integrity_requires_complete_vendor_docs(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    workflow = root / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    contract = root / "docs" / "rag" / "contracts" / "container-qc-artifacts.md"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    workflow.parent.mkdir(parents=True)
    contract.parent.mkdir(parents=True)
    raw_file = raw_root / "fmriprep_outputs.html"
    raw_file.write_text("<html>official outputs</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_outputs.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "---\n"
        "# fMRIPrep Outputs\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": "fmriprep_official_outputs.md",
                        "url": "https://fmriprep.org/en/stable/outputs.html",
                        "file": raw_file.name,
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
    workflow.write_text(
        "# Matrix\n"
        "Official grounding: `docs/rag/vendor/fmriprep_official_outputs.md`.\n",
        encoding="utf-8",
    )
    contract.write_text(
        "# Contract\n"
        "Accepted `official_source_ids` include `docs/rag/vendor/fmriprep_official_outputs.md`.\n",
        encoding="utf-8",
    )

    status = rag_vendor_pointer_integrity(root=root)

    assert status["ok"] is True
    assert status["pointer_count"] == 2
    assert status["issue_count"] == 0
    assert sorted(status["referenced_vendor_docs"]) == ["fmriprep_official_outputs.md"]
    assert status["pointers_by_doc"] == {
        "docs/rag/contracts/container-qc-artifacts.md": ["docs/rag/vendor/fmriprep_official_outputs.md"],
        "docs/rag/workflows/workflow_launchability_matrix.md": ["docs/rag/vendor/fmriprep_official_outputs.md"],
    }

    contract.write_text(
        "# Contract\n"
        "Bad pointer: `docs/rag/vendor/missing_official_outputs.md`.\n",
        encoding="utf-8",
    )
    failed = rag_vendor_pointer_integrity(root=root)

    assert failed["ok"] is False
    assert {
        "source_doc": "docs/rag/contracts/container-qc-artifacts.md",
        "vendor_doc": "missing_official_outputs.md",
        "vendor_path": "docs/rag/vendor/missing_official_outputs.md",
        "issue": "missing_or_incomplete_vendor_doc",
    } in failed["issues"]


def test_rag_vendor_coverage_catalog_summarizes_vendor_docs_without_raw_text(tmp_path):
    root = tmp_path
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    workflow_root = root / "docs" / "rag" / "workflows"
    vendor_doc = vendor_root / "fmriprep_official_outputs.md"
    raw_doc = raw_root / "fmriprep_outputs.html"
    workflow_doc = workflow_root / "bold_fmriprep_xcpd_report.md"
    raw_root.mkdir(parents=True)
    workflow_root.mkdir(parents=True)
    vendor_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "---\n"
        "# fMRIPrep outputs\n"
        "Curated summary.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("<html>raw official fMRIPrep output page text</html>", encoding="utf-8")
    raw_bytes = raw_doc.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-06T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": vendor_doc.name,
                        "url": "https://fmriprep.org/en/stable/outputs.html",
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
    workflow_doc.write_text(
        "# Workflow\n"
        "Native reports are grounded by docs/rag/vendor/fmriprep_official_outputs.md.\n",
        encoding="utf-8",
    )

    catalog = rag_vendor_coverage_catalog(root=root, indexed_sources=[])

    assert catalog["status"] == "complete"
    assert catalog["policy"] == "curated summaries are indexed; raw snapshots are provenance evidence only"
    assert catalog["vendor_doc_count"] == 1
    assert catalog["complete_vendor_doc_count"] == 1
    assert catalog["raw_source_count"] == 1
    assert catalog["raw_sources_indexed"] is False
    assert catalog["pointer_integrity_ok"] is True
    assert catalog["vendors"] == [
        {
            "vendor_doc": "fmriprep_official_outputs.md",
            "vendor_path": "docs/rag/vendor/fmriprep_official_outputs.md",
            "complete": True,
            "manifest_backed": True,
            "source_url_backed": True,
            "raw_source_count": 1,
            "source_url_count": 1,
            "source_types": ["official_docs"],
            "referenced_by": ["docs/rag/workflows/bold_fmriprep_xcpd_report.md"],
            "raw_source_ids": ["fmriprep_outputs"],
        }
    ]
    serialized = json.dumps(catalog)
    assert "raw official fMRIPrep output page text" not in serialized
    assert "manifest_path" not in serialized
    assert "persist_dir" not in serialized
    assert str(root) not in serialized
    assert "raw_snapshots" not in serialized
    assert "sha256" not in serialized
    assert "docs/rag/vendor/raw-sources" not in serialized


def test_vendor_raw_source_status_flags_raw_html_if_indexed(tmp_path):
    root = tmp_path / "repo"
    raw_root = root / "docs" / "rag" / "vendor" / "raw-sources"
    raw_root.mkdir(parents=True)
    raw_file = raw_root / "xcp_d_usage.html"
    raw_file.write_text("<html>XCP-D usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "xcp_d_usage",
                        "vendor_doc": "xcp_d_official_container_usage.md",
                        "url": "https://xcp-d.readthedocs.io/en/stable/usage.html",
                        "file": raw_file.name,
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

    status = vendor_raw_source_status(
        root=root,
        indexed_sources=["docs/rag/vendor/raw-sources/xcp_d_usage.html"],
    )

    assert status["raw_sources_indexed"] is True
    assert status["indexed_raw_sources"] == ["docs/rag/vendor/raw-sources/xcp_d_usage.html"]


def test_vendor_raw_source_status_flags_unknown_curated_raw_source_ids(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage, missing_source\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_file.name,
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

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["curated_provenance_issues"] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "issue": "unknown_raw_source_id",
            "raw_source_id": "missing_source",
        }
    ]
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage", "missing_source"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_usage.html"],
            "source_types": ["official_docs"],
            "manifest_backed": False,
            "source_url_backed": True,
            "complete": False,
        }
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == [
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


def test_vendor_raw_source_status_audits_vendor_docs_not_named_by_manifest(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (vendor_root / "unbacked_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://example.org/unbacked.html\n"
        "raw_source_ids: unbacked_source\n"
        "---\n"
        "# Unbacked\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_file.name,
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

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert {
        "vendor_doc": "unbacked_official_container_usage.md",
        "issue": "unknown_raw_source_id",
        "raw_source_id": "unbacked_source",
    } in status["curated_provenance_issues"]
    assert [item["vendor_doc"] for item in status["curated_sources"]] == [
        "fmriprep_official_container_usage.md",
        "unbacked_official_container_usage.md",
    ]
    assert status["curated_sources"][1]["complete"] is False


def test_vendor_raw_source_status_rejects_raw_source_id_from_other_vendor_doc(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "xcp_d_usage.html"
    raw_file.write_text("<html>official XCP-D usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://xcp-d.readthedocs.io/en/stable/usage.html\n"
        "raw_source_ids: xcp_d_usage\n"
        "---\n"
        "# fMRIPrep wrongly citing XCP-D\n",
        encoding="utf-8",
    )
    (vendor_root / "xcp_d_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://xcp-d.readthedocs.io/en/stable/usage.html\n"
        "raw_source_ids: xcp_d_usage\n"
        "---\n"
        "# XCP-D\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "xcp_d_usage",
                        "vendor_doc": "xcp_d_official_container_usage.md",
                        "url": "https://xcp-d.readthedocs.io/en/stable/usage.html",
                        "file": raw_file.name,
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

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert {
        "vendor_doc": "fmriprep_official_container_usage.md",
        "issue": "raw_source_vendor_doc_mismatch",
        "raw_source_id": "xcp_d_usage",
        "manifest_vendor_doc": "xcp_d_official_container_usage.md",
    } in status["curated_provenance_issues"]
    fmriprep_entry = next(item for item in status["curated_sources"] if item["vendor_doc"] == "fmriprep_official_container_usage.md")
    assert fmriprep_entry["manifest_backed"] is False
    assert fmriprep_entry["complete"] is False


def test_vendor_raw_source_status_rejects_manifest_file_path_escape(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": "../fmriprep_usage.html",
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": "",
                        "bytes": 12,
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert {
        "vendor_doc": "fmriprep_official_container_usage.md",
        "issue": "raw_source_file_path_unsafe",
        "raw_source_id": "fmriprep_usage",
        "file": "../fmriprep_usage.html",
    } in status["curated_provenance_issues"]
    assert status["missing_files"] == ["../fmriprep_usage.html"]
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": [],
            "source_types": [],
            "manifest_backed": False,
            "source_url_backed": False,
            "complete": False,
        }
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == []


def test_vendor_raw_source_status_marks_curated_doc_incomplete_when_raw_file_hash_bad(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage changed</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": "0" * 64,
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["hash_mismatches"] == ["fmriprep_usage.html"]
    assert {
        "vendor_doc": "fmriprep_official_container_usage.md",
        "issue": "raw_source_file_integrity_failed",
        "raw_source_id": "fmriprep_usage",
        "file": "fmriprep_usage.html",
    } in status["curated_provenance_issues"]
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": [],
            "source_types": [],
            "manifest_backed": False,
            "source_url_backed": False,
            "complete": False,
        }
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == []


def test_vendor_raw_source_status_flags_curated_source_url_not_backed_by_manifest(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "templateflow_installation.html"
    raw_file.write_text("<html>official TemplateFlow installation</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "templateflow_official_cache_archive_client.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://www.templateflow.org/usage/client/\n"
        "raw_source_ids: templateflow_installation\n"
        "---\n"
        "# TemplateFlow\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "templateflow_installation",
                        "vendor_doc": "templateflow_official_cache_archive_client.md",
                        "url": "https://github.com/templateflow/python-client/blob/master/docs/installation.rst",
                        "file": raw_file.name,
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

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["curated_provenance_issues"] == [
        {
            "vendor_doc": "templateflow_official_cache_archive_client.md",
            "issue": "source_url_not_backed_by_raw_source_ids",
            "source_url": "https://www.templateflow.org/usage/client/",
            "raw_source_ids": ["templateflow_installation"],
        }
    ]

def test_vendor_raw_source_status_flags_raw_source_with_windows_path(tmp_path):
    root = tmp_path / "repo"
    raw_root = root / "docs" / "rag" / "vendor" / "raw-sources"
    raw_root.mkdir(parents=True)
    raw_file = raw_root / "openai_python_sdk_readme.md"
    raw_file.write_text("# OpenAI Python SDK raw source\n", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "openai_python_sdk_readme",
                        "vendor_doc": "openai_official_responses_function_tools.md",
                        "url": "https://raw.githubusercontent.com/openai/openai-python/main/README.md",
                        "file": raw_file.name,
                        "source_type": "official_repository",
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

    status = vendor_raw_source_status(
        root=root,
        indexed_sources=[r"docs\rag\vendor\raw-sources\openai_python_sdk_readme.md"],
    )

    assert status["raw_sources_indexed"] is True
    assert status["indexed_raw_sources"] == ["docs/rag/vendor/raw-sources/openai_python_sdk_readme.md"]
