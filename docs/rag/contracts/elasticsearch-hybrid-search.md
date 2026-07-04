---
source_type: rag_contract
status: current_contract
retrieved_date: 2026-06-18
official_grounding:
  - docs/rag/vendor/elastic_official_hybrid_search.md
  - https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html
  - https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html
  - https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion
  - https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker
  - https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic
  - https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod
unsupported_boundaries:
  - Elasticsearch retrieval is not a task launcher.
  - Raw official snapshots are provenance evidence only and are not indexed wholesale.
  - Ranking evidence does not override backend project, series, workflow, task, QC, or report state.
---

# Elasticsearch Hybrid Search Contract

Image Agent RAG now targets Elasticsearch hybrid search for production acceptance. The index combines lexical BM25 retrieval from Elasticsearch text fields with dense vector retrieval from a `dense_vector` field, then fuses ranked results with RRF. The local deterministic builder persists an Elasticsearch-compatible mapping, bulk NDJSON, and hybrid query template so mock/control-plane tests can validate the contract without requiring a running Elasticsearch service.

## Official Sources

The contract is grounded in the curated, manifest-backed source `docs/rag/vendor/elastic_official_hybrid_search.md`, which summarizes Elastic official documentation retrieved on 2026-06-18:

- `dense_vector` field mapping and vector indexing: https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html
- kNN search over dense vectors: https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html
- Reciprocal rank fusion, including RRF retriever composition: https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion

## Indexed Fields

Required production index name: `image_agent_rag`.

Required lexical fields:

- `title`
- `text`
- `source`: safe repo-relative Markdown path under `docs/rag/` or `docs/skills/`; raw snapshots, URL strings, absolute paths, Windows drive paths, traversal paths, and app/runtime paths must not be returned as RAG citations

Required filter/provenance fields:

- `chunk_id`
- `source_type`
- `workflow_type`
- `skill`
- `priority_score`

Required vector field:

- `embedding`: Elasticsearch `dense_vector`, cosine similarity, 64 dimensions for the current hashing-trick local contract.

The 64-dimensional `local_hashing` vector is a deterministic contract placeholder for local mock/control-plane tests. Production acceptance must use a configured embedding provider, not `local_hashing`, and the deployed `/agent/rag/rebuild` response must report `embedding_provider`, `embedding_model`, `embedding_transport`, `embedding_endpoint_configured`, `dense_vector_dims`, and `embedding_production_ready=true`. A production embedding upgrade may increase dimensions only with an explicit mapping migration, acceptance evidence update, and fresh RAG rebuild. Deployment acceptance must always report the persisted field name as `embedding`.

## Hybrid Query Shape

The query contract is:

1. Elasticsearch standard retriever with `multi_match` over `title^2`, `text`, and `source` for BM25 lexical ranking.
2. Elasticsearch kNN retriever over `embedding` for vector similarity ranking.
3. RRF fusion over the lexical and kNN retrievers.

Saved acceptance evidence must report:

- `smoke_gate.require_elasticsearch_hybrid_rag=true`
- `rag_elasticsearch_hybrid_status=passed`
- `rag_rebuild_elasticsearch_hybrid` present, connected, and matching status `index` and `indexed_chunk_count`
- `rag_elasticsearch_hybrid.engine=elasticsearch`
- `rag_elasticsearch_hybrid.configured=true`
- `rag_elasticsearch_hybrid.index` is a privacy-safe index symbol
- `rag_elasticsearch_hybrid.persisted=true`
- `rag_elasticsearch_hybrid.mode=connected`
- `rag_elasticsearch_hybrid.indexed_chunk_count` greater than zero
- `rag_elasticsearch_hybrid.error` absent
- `rag_elasticsearch_hybrid.embedding_error` absent
- `rag_elasticsearch_hybrid.lexical_retriever=standard`
- `rag_elasticsearch_hybrid.vector_retriever=knn`
- `rag_elasticsearch_hybrid.dense_vector_field=embedding`
- `rag_rebuild_elasticsearch_hybrid.lexical_retriever` matches `rag_elasticsearch_hybrid`
- `rag_rebuild_elasticsearch_hybrid.vector_retriever` matches `rag_elasticsearch_hybrid`
- `rag_rebuild_elasticsearch_hybrid.dense_vector_field` matches `rag_elasticsearch_hybrid`
- `rag_rebuild_elasticsearch_hybrid.fusion` matches `rag_elasticsearch_hybrid`
- `rag_elasticsearch_hybrid.dense_vector_dims` greater than zero, with `rag_rebuild_elasticsearch_hybrid.dense_vector_dims` matching status.
- `rag_elasticsearch_hybrid.embedding_provider` is present and is not `local_hashing`, `mock`, or another deterministic fallback.
- `rag_elasticsearch_hybrid.embedding_model` is present, and `rag_rebuild_elasticsearch_hybrid.embedding_model` matches status.
- `rag_elasticsearch_hybrid.embedding_transport` is present, production-safe (`sdk` or `openai_compatible_http`), and `rag_rebuild_elasticsearch_hybrid.embedding_transport` matches status.
- `rag_elasticsearch_hybrid.embedding_endpoint_configured` is a privacy-safe boolean, and `rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured` matches status.
- `rag_elasticsearch_hybrid.embedding_production_ready=true`
- `rag_elasticsearch_hybrid.fusion=rrf`
- `rag_elasticsearch_hybrid.official_sources` includes the Elastic RRF documentation URL.
- `rag_elasticsearch_hybrid_query_status=passed`
- `rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid`
- `rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid`
- `rag_elasticsearch_hybrid_query_source=docs/rag/contracts/elasticsearch-hybrid-search.md`
- `rag_elasticsearch_hybrid_query_lexical_retriever=standard`
- `rag_elasticsearch_hybrid_query_vector_retriever=knn`
- `rag_elasticsearch_hybrid_query_dense_vector_field=embedding`, and the query-time dense-vector field matches `rag_elasticsearch_hybrid.dense_vector_field`
- `rag_elasticsearch_hybrid_query_fusion=rrf`, and query-time hybrid components match `rag_elasticsearch_hybrid`

Local developer runs may report `persisted=false` with `mode=local_contract` while writing `.rag_index/elasticsearch/mapping.json`, `.rag_index/elasticsearch/hybrid-query-template.json`, and `.rag_index/elasticsearch/bulk.ndjson`. If Elasticsearch is configured but the embedding provider is missing or still local-hash based, status must report `mode=embedding_required`, `persisted=false`, `indexed_chunk_count=0`, `embedding_provider=local_hashing`, and `embedding_production_ready=false`; that state must not create or bulk-write a connected Elasticsearch index. If a configured embedding provider fails during rebuild, status must report `mode=embedding_error`, `persisted=false`, `indexed_chunk_count=0`, `embedding_provider=local_hashing`, `embedding_production_ready=false`, and a redacted `embedding_error`; that state must not bulk-write local hash vectors into a connected Elasticsearch index. These local/error modes are acceptable for mock/control-plane tests but are not production acceptance.

## Runtime Configuration

Deployments that need production acceptance must configure a reachable Elasticsearch service before calling `/agent/rag/rebuild`:

```bash
export IMAGE_AGENT_ELASTICSEARCH_URL=https://<elasticsearch-host>:9200
export IMAGE_AGENT_ELASTICSEARCH_API_KEY=<provided-by-operator>
export IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_<release-or-environment>
export IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai
export IMAGE_AGENT_RAG_EMBEDDING_MODEL=text-embedding-3-small
export IMAGE_AGENT_RAG_EMBEDDING_API_KEY=<provided-by-operator>
export IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=https://<openai-compatible-embedding-endpoint>
```

`IMAGE_AGENT_ELASTICSEARCH_API_KEY` is optional when the deployment uses another authenticated network boundary, but it must never be committed to git or returned by status endpoints. `IMAGE_AGENT_ELASTICSEARCH_INDEX` is optional and defaults to `image_agent_rag`; when set, it must be a privacy-safe symbol containing only letters, numbers, `_`, `.`, or `-`. The backend creates the configured RAG index when missing, writes curated RAG chunks through the official Python Elasticsearch client, and records connected evidence in `.rag_index/manifest.json`.

Configured embedding providers use the OpenAI SDK when available and report `embedding_transport=sdk`. If the SDK cannot be imported or initialized in a deployment image, the backend uses an OpenAI-compatible HTTP `/embeddings` fallback and reports `embedding_transport=openai_compatible_http` with the same `IMAGE_AGENT_RAG_EMBEDDING_*` environment variables. `IMAGE_AGENT_RAG_EMBEDDING_BASE_URL` may point either to a provider root such as `https://<gateway>/v1` or directly to an `/embeddings` endpoint. Status surfaces expose only `embedding_endpoint_configured=true|false`, never the endpoint URL. This fallback is only for embedding vector calls; it does not change Agent model routing, Elasticsearch indexing rules, workflow launch gates, or production acceptance requirements.

`IMAGE_AGENT_RAG_EMBEDDING_API_KEY` may reuse the model gateway key when the same OpenAI-compatible provider serves embeddings, but it must remain an environment secret and must not be committed, logged, indexed, or returned by status endpoints. Without a configured embedding provider the backend uses `local_hashing` only for local contract artifacts, reports `mode=embedding_required` when Elasticsearch is configured, reports `embedding_production_ready=false`, and must not create or bulk-write a connected Elasticsearch index. That is useful for local development but blocks strict production acceptance. If the configured embedding provider is unreachable or returns invalid vectors, the backend must redact the failure, skip connected Elasticsearch writes for that rebuild, and fall back to local retrieval for queries instead of sending local-hash query vectors to a production vector index.

When a deployment server has no existing operator-managed Elasticsearch endpoint, the remote handoff may provision a local Docker single-node acceptance/dev-test runtime using the pinned Elastic image `docker.elastic.co/elasticsearch/elasticsearch:9.4.2`. This handoff is grounded in Elastic's official Docker installation and production Docker guidance and remains operator-authorized only: generated credentials must be captured in the operator-managed secret store, the container must bind only to the deployment server loopback interface or an equivalent protected boundary, floating image tags are forbidden, and production high availability still requires an operator-managed Elasticsearch deployment rather than relying on the single-node acceptance container.

Connected rebuild owns the configured RAG index, which defaults to `image_agent_rag`. If that index already exists, rebuild deletes it, recreates the current mapping, and bulk-writes only the current curated chunks with `refresh=wait_for`. This prevents stale Elasticsearch documents from surviving across source, metadata, or embedding-dimension changes. Other indexes are outside the Image Agent RAG contract and must not be used for strict acceptance evidence.

Elasticsearch connection failures may be summarized in `/agent/rag/status.index.hybrid_search.error`, but the summary must redact API keys, Authorization headers, and URL credentials before it is written to `.rag_index/manifest.json` or returned by the API.

After rebuild, `/agent/rag/rebuild.hybrid_search` and `/agent/rag/status.index.hybrid_search` must both report `configured=true`, `persisted=true`, `mode=connected`, matching privacy-safe `index`, matching `indexed_chunk_count`, matching `lexical_retriever=standard`, matching `vector_retriever=knn`, matching `dense_vector_field=embedding`, matching `fusion=rrf`, matching `dense_vector_dims`, matching production `embedding_provider`, matching non-empty `embedding_model`, matching production-safe `embedding_transport`, matching boolean `embedding_endpoint_configured`, and `embedding_production_ready=true`. The strict smoke gate must also call `/agent/rag/query` and record `retrieval_mode=elasticsearch_hybrid`, `retrieval_source=elasticsearch_hybrid`, and a citation to this contract. If Elasticsearch or the embedding provider is not configured or is unreachable, the backend keeps the local contract artifacts and deterministic fallback retrieval, but production acceptance remains blocked.

## Boundaries

Elasticsearch ranks curated RAG chunks only. raw snapshots are provenance evidence only and must not be indexed wholesale.

Connected Elasticsearch query results are filtered before citation assembly. A hit is ignored unless `_source.source` is a safe repo-relative Markdown path under `docs/rag/` or `docs/skills/`, is not under `docs/rag/vendor/raw-sources/`, and is present in the current local RAG manifest. This keeps raw provenance snapshots, deployment paths, URLs, backend/app files, and stale Elasticsearch documents out of Agent/RAG answers even if a stale or manually altered Elasticsearch index contains them. Stale or unsafe hits are ignored individually; if filtering leaves at least one current safe hit, the backend still returns `retrieval_mode=elasticsearch_hybrid`. If filtering leaves no current safe hits, the backend treats the Elasticsearch response as having no usable citation evidence and falls back to deterministic local retrieval; strict production acceptance still requires `retrieval_mode=elasticsearch_hybrid` and this contract citation.

The backend registry, preflight, confirmation, fingerprint, task_service.create_series_task(), and pipeline runner remain authoritative for production task creation. Agent and RAG may explain workflow capability, evidence, and launchability, but fixed workflow execution still must pass registry, preflight, human confirmation, confirmation fingerprint, `task_service.create_series_task()`, and the pipeline runner.

Unknown workflows must remain incubation proposals only. They may be recorded in the IncubationLedger or proposal flow, but Elasticsearch retrieval must not create a production task for them.

ObserveRepair remains read-only observation and repair recommendation. Retrieval evidence can inform suggestions, but it must not automatically rerun tasks.
