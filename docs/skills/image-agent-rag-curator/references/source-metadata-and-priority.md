# Source Metadata and Priority

## Required Metadata

For each curated RAG item, record:

- source id;
- source path or URL;
- source type: code, contract doc, workflow doc, script, task record, result summary, report, log, external doc, example;
- source date, commit, task id, or version when known;
- modality and workflow type;
- environment: local, remote server, production evidence, validation-only, historical;
- evidence level;
- sensitivity status;
- curator note.

## Official Raw Source Traceability

For curated vendor summaries in `docs/rag/vendor/*.md`, frontmatter must include:

- `source_url`: every official URL summarized by the curated document;
- `raw_source_ids`: comma-separated ids from `docs/rag/vendor/raw-sources/manifest.json`;
- `retrieved_date`;
- `status: curated_summary`.

The `/agent/rag/status` `vendor_raw_sources.curated_sources` field is the machine-readable audit view for this metadata. Each item must show:

- top-level `manifest_schema_version`;
- top-level `source_count`;
- top-level `vendor_doc_count`;
- `vendor_doc`;
- `raw_source_ids`;
- `source_urls`;
- `raw_files`;
- `source_types`;
- `manifest_backed`;
- `source_url_backed`;
- `complete`.

`raw_source_ids` are manifest ids, not `official_source_ids`. Artifact `official_source_ids` must point to curated `docs/rag/vendor/*.md` answer sources; raw-source ids and `docs/rag/vendor/raw-sources/*` files are not accepted artifact source ids.

Remote acceptance with `--require-raw-source-policy` requires `manifest_schema_version`, positive `source_count`, positive `vendor_doc_count`, `curated_provenance_ok=true`, `curated_provenance_issues=[]`, every `curated_sources[*].complete=true`, and per-curated-doc `manifest_backed=true`, `source_url_backed=true`, and non-empty `source_types`. Raw snapshots remain traceability evidence only and must not be indexed wholesale.

The `vendor_pointer_integrity` status is the provenance pointer integrity gate for workflow and contract docs. It proves literal `docs/rag/vendor/*.md` pointers in `docs/rag/workflows/**/*.md` and `docs/rag/contracts/**/*.md` resolve to complete curated vendor summaries whose raw-source manifest rows match the same `vendor_doc`. Curated vendor summaries are answer sources; raw snapshots are provenance evidence only.

The `/agent/rag/status` `vendor_coverage_catalog` field is the human-readable summary view for operators and future frontend source panels. It keeps the same boundary as `vendor_raw_sources`: curated summaries are indexed, while raw snapshots remain provenance evidence. The catalog reports:

- `policy`;
- `manifest_schema_version`;
- `vendor_doc_count`;
- `complete_vendor_doc_count`;
- `incomplete_vendor_doc_count`;
- `raw_source_count`;
- `raw_sources_indexed`;
- `curated_provenance_ok`;
- `pointer_integrity_ok`;
- per-vendor `vendor_doc`, `vendor_path`, `complete`, `manifest_backed`, `source_url_backed`, `raw_source_count`, `source_url_count`, `source_types`, `referenced_by`, and `raw_source_ids`.

Use `vendor_coverage_catalog` to inspect coverage and display source health. Use `vendor_raw_sources.curated_sources` and `raw_source_evidence` when exact raw file ids, URLs, hashes, byte counts, and retrieval timestamps are needed. The catalog does not include raw HTML or raw snapshot text.

## Evidence Levels

Use this priority order:

1. Current backend code and contract tests.
2. Current task/result-summary records from real runs.
3. Current workflow scripts used by the backend.
4. Current product docs and skill references.
5. Validate-only records.
6. Historical review outputs and examples.
7. External neuroimaging docs.
8. User recollection or uncited notes.

RAG may explain product behavior, but backend records remain authoritative during live operation.

## Retrieval Priority

High priority:

- workflow eligibility contracts;
- workflow maturity / launchability matrix: `docs/rag/workflows/workflow_launchability_matrix.md`;
- result-summary contract;
- current production DWI/BOLD/T1 evidence;
- safety and unsupported-sequence wording.

Medium priority:

- implementation notes;
- examples and eval cases;
- historical scripts still used as references.

Low priority:

- stale docs retained for compatibility;
- exploratory notes;
- failed or superseded workflow experiments.
