---
source_type: rag_vendor
source_url: https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html, https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html, https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion, https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker, https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic, https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod
raw_source_ids: elastic_dense_vector, elastic_knn_search, elastic_rrf, elastic_docker_install, elastic_docker_basic, elastic_docker_prod
retrieved_date: 2026-06-18
status: curated_summary
unsupported_boundaries:
  - Elasticsearch retrieval is not a task launcher.
  - Raw official snapshots are provenance evidence only and are not indexed wholesale.
  - Backend project, series, workflow, task, QC, and report state remain authoritative.
  - Unknown workflows remain IncubationLedger/proposal only and do not create production tasks.
  - ObserveRepair remains read-only observation and repair advice with no automatic rerun.
---

# Elastic Official Hybrid Search

## Purpose / Scope

Use this curated source for Image Agent RAG's Elasticsearch hybrid retrieval contract. It summarizes the official Elastic documentation that backs the production RAG index shape: lexical BM25 retrieval, dense vector retrieval, and reciprocal rank fusion.

This source is retrieval infrastructure evidence. It is not a task launcher, workflow registry, preflight result, confirmation fingerprint, task row, QC result, or report artifact.

## Indexed Fields And Vectors

Elastic documents `dense_vector` fields for vector search. Image Agent uses the stable field name `embedding` for dense vectors and stores only curated RAG chunks from `docs/rag/` and `docs/skills/`, never raw official snapshots.

Local development may use deterministic `local_hashing` vectors for contract artifacts. Production acceptance requires a configured embedding provider, non-empty embedding model, positive dense vector dimensions, and `embedding_production_ready=true`.

## Hybrid Retrieval Shape

Image Agent production retrieval combines:

- BM25 lexical retrieval through an Elasticsearch standard retriever over curated text fields;
- kNN vector retrieval over the `embedding` dense vector field;
- RRF fusion over the lexical and vector retrievers.

Strict remote acceptance must prove `mode=connected`, `persisted=true`, `configured=true`, `lexical_retriever=standard`, `vector_retriever=knn`, `dense_vector_field=embedding`, and `fusion=rrf`.

## Docker Runtime Boundary

Elastic's official Docker installation guidance is used only to support an operator-reviewed local single-node acceptance/dev-test runtime when no managed Elasticsearch endpoint exists on the deployment server. The handoff pins `docker.elastic.co/elasticsearch/elasticsearch:9.4.2`, forbids floating image tags, keeps generated credentials in the operator-managed secret store, and treats production high availability as outside the single-node acceptance container boundary.

## Boundaries

- Elasticsearch ranks curated RAG chunks only.
- Raw Elastic snapshots remain provenance evidence and are not indexed wholesale.
- RAG answers may explain retrieval behavior and cite this curated source, but backend project, series, workflow, task, QC, and report state remain authoritative.
- Unknown workflows still go only to IncubationLedger/proposal; Elasticsearch retrieval must not create production tasks.
- ObserveRepair remains read-only observation and repair advice; retrieval evidence must not automatically rerun tasks.
