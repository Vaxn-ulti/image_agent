from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path
from typing import Any, TypedDict

from app.agent.rag_index import vendor_raw_source_status, retrieve_from_local_rag_index

DEFAULT_KNOWLEDGE_GLOBS = [
    ".planning/**/*.md",
    "docs/**/*.md",
    "docs/rag/**/*.md",
    "docs/skills/**/SKILL.md",
    "docs/skills/**/references/*.md",
    "apps/api/README.md",
]
LAUNCHABILITY_MATRIX_SOURCE = "docs/rag/workflows/workflow_launchability_matrix.md"


def _package_available(package: str) -> bool:
    return importlib.util.find_spec(package) is not None


def dependency_status() -> dict:
    return {
        "langgraph": {
            "available": _package_available("langgraph"),
            "role": "stateful_long_running_agent_orchestration",
        },
        "llama_index": {
            "available": _package_available("llama_index"),
            "role": "document_ingestion_indexing_and_rag_retrieval",
        },
        "local_file_search": {
            "available": True,
            "role": "OpenAI file_search-like retrieval over docs/rag and docs/skills",
        },
    }


def grounding_policy() -> dict:
    return {
        "source_priority": [
            "backend_task_records",
            "registered_outputs",
            "result_summary_json",
            "planning_files",
            "skill_references",
            "rag_documents",
        ],
        "rag_may_override_backend": False,
        "rule": "Backend DB task/output records outrank retrieved documents for current project state.",
    }


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_\\-]+", text) if len(token) > 2}


def _is_launchability_query(query: str) -> bool:
    lowered = query.lower()
    return any(token in lowered for token in ("launch", "launchable", "run ", "run?", "runnable", "supported", "production", "workflow_eligibility", "mriqc", "dpabi", "qsiprep", "qsirecon")) or any(
        token in lowered for token in ("能跑", "能不能", "支持", "可运行", "生产")
    )


def _excerpt(text: str, query_terms: set[str], max_chars: int = 360) -> str:
    lowered = text.lower()
    positions = [lowered.find(term.lower()) for term in query_terms if lowered.find(term.lower()) >= 0]
    start = max(0, min(positions) - 80) if positions else 0
    snippet = text[start : start + max_chars].replace("\n", " ").strip()
    return snippet


def _supporting_excerpt(text: str, required_terms: set[str], max_chars: int = 700) -> str:
    normalized_text = re.sub(r"\s+", " ", text).strip()
    lowered = normalized_text.lower()
    if not required_terms:
        return normalized_text[:max_chars].strip()
    window = max(100, max_chars // max(1, len(required_terms)) - 20)
    snippets: list[str] = []
    seen: set[str] = set()
    for term in sorted(required_terms):
        position = lowered.find(term.lower())
        if position < 0:
            continue
        start = max(0, position - 70)
        end = min(len(normalized_text), position + len(term) + window)
        snippet = normalized_text[start:end].strip()
        if snippet and snippet not in seen:
            snippets.append(snippet)
            seen.add(snippet)
    if not snippets:
        return normalized_text[:max_chars].strip()
    return " ... ".join(snippets)[:max_chars].strip()


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip()
    metadata: dict[str, Any] = {}
    list_key: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if list_key and stripped.startswith("- "):
            metadata[list_key].append(stripped[2:].strip().strip('"').strip("'"))
            continue
        list_key = None
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            metadata[key] = value.strip('"').strip("'")
            continue
        metadata[key] = []
        list_key = key
    return metadata, body


def _title_from_markdown(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return path.stem.replace("_", " ").replace("-", " ").title()


def retrieve_reference_context(
    query: str,
    *,
    root: Path | str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    root_path = Path(root or Path.cwd())
    persist_path = root_path / ".rag_index"
    pinned_hits = _pinned_launchability_hits(query, root_path)
    if (persist_path / "chunks.jsonl").exists():
        indexed = retrieve_from_local_rag_index(
            query,
            root=root_path,
            persist_dir=persist_path,
            filters=filters,
            limit=limit,
        )
        if indexed["results"]:
            if pinned_hits:
                seen_sources = {hit["source"] for hit in pinned_hits}
                indexed["results"] = (pinned_hits + [hit for hit in indexed["results"] if hit.get("source") not in seen_sources])[:limit]
            return indexed
    query_terms = _tokens(query)
    filters = filters or {}
    hits: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for pattern in DEFAULT_KNOWLEDGE_GLOBS:
        for path in root_path.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                raw_text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            metadata, body = _parse_frontmatter(raw_text)
            if any(str(metadata.get(key)) != str(value) for key, value in filters.items()):
                continue
            doc_terms = _tokens(body)
            score = len(query_terms & doc_terms)
            if score <= 0:
                continue
            try:
                source = str(path.relative_to(root_path))
            except ValueError:
                source = str(path)
            metadata.setdefault(
                "source_type",
                "skill_reference"
                if "docs/skills" in source.replace("\\", "/")
                else "rag_document"
                if "docs/rag" in source.replace("\\", "/")
                else "local_document",
            )
            hits.append(
                {
                    "source": source,
                    "title": _title_from_markdown(path, body),
                    "snippet": _excerpt(body, query_terms),
                    "score": float(score),
                    "metadata": metadata,
                }
            )
    if pinned_hits:
        seen_sources = {hit["source"] for hit in pinned_hits}
        hits = pinned_hits + [hit for hit in hits if hit.get("source") not in seen_sources]
    else:
        hits.sort(key=lambda item: (-item["score"], item["source"]))
    return {
        "query": query,
        "results": hits[:limit],
        "tool": "retrieve_reference_context",
        "mode": "local_file_search",
    }


def _pinned_launchability_hits(query: str, root_path: Path) -> list[dict[str, Any]]:
    if not _is_launchability_query(query):
        return []
    path = root_path / LAUNCHABILITY_MATRIX_SOURCE
    if not path.exists() or not path.is_file():
        return []
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    metadata, body = _parse_frontmatter(raw_text)
    metadata.setdefault("source_type", "rag_workflow")
    metadata.setdefault("workflow_type", "workflow_launchability_matrix")
    return [
        {
            "source": LAUNCHABILITY_MATRIX_SOURCE,
            "title": _title_from_markdown(path, body),
            "snippet": _excerpt(body, _tokens(query), max_chars=520),
            "score": 999.0,
            "metadata": metadata,
        }
    ]


def query_local_knowledge(query: str, root: Path | str | None = None, limit: int = 5) -> list[dict]:
    root_path = Path(root or Path.cwd())
    query_terms = _tokens(query)
    hits: list[dict] = []
    seen: set[Path] = set()
    for pattern in DEFAULT_KNOWLEDGE_GLOBS:
        for path in root_path.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            doc_terms = _tokens(text)
            score = len(query_terms & doc_terms)
            if score <= 0:
                continue
            hits.append(
                {
                    "path": str(path.relative_to(root_path)),
                    "score": score,
                    "excerpt": _excerpt(text, query_terms),
                }
            )
    return sorted(hits, key=lambda item: (-item["score"], item["path"]))[:limit]


def _citation_context(query: str, root: Path | str | None = None, limit: int = 5) -> dict[str, Any]:
    started = time.perf_counter()
    context = retrieve_reference_context(query, root=root, limit=limit)
    normalized = []
    for hit in context.get("results") or []:
        source = str(hit.get("source") or hit.get("path") or "")
        excerpt = str(hit.get("snippet") or hit.get("excerpt") or "")
        normalized.append(
            {
                **hit,
                "source": source,
                "path": source,
                "snippet": excerpt,
                "excerpt": excerpt,
            }
        )
    if normalized:
        normalized = _filter_policy_citations(query, normalized)
        normalized = _enrich_policy_citation_snippets(query, normalized, root=root)
        mode = str(context.get("mode") or "persistent_index")
        output = {
            "citations": normalized[:limit],
            "retrieval_mode": mode,
            "retrieval_source": "elasticsearch_hybrid" if mode == "elasticsearch_hybrid" else "persistent_index",
        }
        if mode == "elasticsearch_hybrid":
            evidence = _safe_elasticsearch_hybrid_query_evidence(context.get("elasticsearch_hybrid_query"))
            if evidence:
                output["elasticsearch_hybrid_query"] = evidence
        output["retrieval_latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        return output
    local_hits = [
        {**hit, "source": str(hit.get("path") or ""), "snippet": str(hit.get("excerpt") or "")}
        for hit in query_local_knowledge(query, root=root, limit=limit)
    ]
    local_hits = _filter_policy_citations(query, local_hits)
    local_hits = _enrich_policy_citation_snippets(query, local_hits, root=root)
    return {
        "citations": local_hits,
        "retrieval_mode": "local_scan",
        "retrieval_source": "local_scan",
        "retrieval_latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }


def _safe_elasticsearch_hybrid_query_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in (
        "index",
        "lexical_retriever",
        "vector_retriever",
        "dense_vector_field",
        "fusion",
        "rrf_unavailable_reason",
        "embedding_provider",
        "embedding_model",
        "embedding_transport",
    ):
        field = value.get(key)
        if isinstance(field, str) and field and len(field) <= 140 and all(char.isalnum() or char in "_.-" for char in field):
            safe[key] = field
    dense_vector_dims = value.get("dense_vector_dims")
    if isinstance(dense_vector_dims, int) and not isinstance(dense_vector_dims, bool) and dense_vector_dims > 0:
        safe["dense_vector_dims"] = dense_vector_dims
    for key in ("embedding_endpoint_configured", "embedding_production_ready"):
        if isinstance(value.get(key), bool):
            safe[key] = value[key]
    return safe


def _filter_policy_citations(query: str, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lowered = query.lower()
    preferred: tuple[str, ...] = ()
    if any(term in lowered for term in ("mriqc", "dpabi", "qsiprep")) and _is_launchability_query(query):
        preferred = (LAUNCHABILITY_MATRIX_SOURCE,)
    elif "elasticsearch" in lowered and "hybrid" in lowered:
        preferred = (
            "docs/rag/contracts/elasticsearch-hybrid-search.md",
            "docs/rag/vendor/elastic_official_hybrid_search.md",
        )
    elif "fixed workflow" in lowered and ("production task" in lowered or "create" in lowered):
        preferred = (
            "docs/skills/image-agent-workflow-runner/references/registry-and-preflight.md",
            LAUNCHABILITY_MATRIX_SOURCE,
        )
    elif "dwi" in lowered and any(term in lowered for term in ("produce", "output", "workflow", "dti", "fast gpu")):
        preferred = ("docs/rag/workflows/dwi_fast_gpu_dti.md",)
    elif any(term in lowered for term in ("upload", "sidecar", "bval", "bvec", "nifti", "dicom")):
        preferred = ("docs/rag/data-requirements/modalities-bids.md",)
    elif any(term in lowered for term in ("diagnose", "diagnosis", "dementia", "tumor", "stroke", "normal", "abnormal", "clinical interpretation")):
        preferred = ("docs/rag/safety/non-diagnostic.md",)
    if not preferred:
        return citations
    filtered = [
        hit
        for hit in citations
        if str(hit.get("source") or hit.get("path") or "").replace("\\", "/") in preferred
    ]
    return filtered or citations


def _policy_excerpt_terms(query: str) -> set[str]:
    lowered = query.lower()
    if any(term in lowered for term in ("mriqc", "dpabi", "qsiprep")) and _is_launchability_query(query):
        return {"incubation_reference", "unsupported_external", "workflow_eligibility", "production tasks"}
    if "elasticsearch" in lowered and "hybrid" in lowered:
        return {"elasticsearch", "bm25", "dense vector", "rrf"}
    if "fixed workflow" in lowered and ("production task" in lowered or "create" in lowered):
        return {"registry", "preflight", "human confirmation", "fingerprint", "task_service.create_series_task"}
    if "dwi" in lowered and any(term in lowered for term in ("produce", "output", "workflow", "dti", "fast gpu")):
        return {"fa/md/ad/rd", "atlas regional tsv tables", "qc/provenance", "not full qsiprep"}
    if any(term in lowered for term in ("upload", "sidecar", "bval", "bvec", "nifti", "dicom")):
        return {"dwi", "nifti", "bval", "bvec", "json"}
    if any(term in lowered for term in ("diagnose", "diagnosis", "dementia", "tumor", "stroke", "normal", "abnormal", "clinical interpretation")):
        return {"must not diagnose", "qualified radiologist", "not a diagnosis"}
    return set()


def _enrich_policy_citation_snippets(
    query: str,
    citations: list[dict[str, Any]],
    *,
    root: Path | str | None,
) -> list[dict[str, Any]]:
    terms = _policy_excerpt_terms(query)
    if not terms:
        return citations
    root_path = Path(root or Path.cwd())
    enriched = []
    for hit in citations:
        source = str(hit.get("source") or hit.get("path") or "").replace("\\", "/")
        path = root_path / source
        if path.exists() and path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            snippet = _supporting_excerpt(text, terms, max_chars=1200)
            hit = {**hit, "snippet": snippet, "excerpt": snippet}
        enriched.append(hit)
    return enriched


def _citation_hits(query: str, root: Path | str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    return _citation_context(query, root=root, limit=limit)["citations"]


def _raw_source_evidence_for_citations(citations: list[dict[str, Any]], root: Path | str | None = None) -> dict[str, Any]:
    root_path = Path(root or Path.cwd())
    cited_vendor_docs = []

    def add_vendor_path(value: Any) -> None:
        source = str(value or "").replace("\\", "/")
        prefix = "docs/rag/vendor/"
        if not source.startswith(prefix) or "/raw-sources/" in source or not source.endswith(".md"):
            return
        vendor_doc = source.removeprefix(prefix)
        if vendor_doc not in cited_vendor_docs:
            cited_vendor_docs.append(vendor_doc)

    for hit in citations:
        add_vendor_path(hit.get("source") or hit.get("path"))
        metadata = hit.get("metadata") or {}
        grounding = metadata.get("official_grounding") if isinstance(metadata, dict) else None
        if isinstance(grounding, list):
            for value in grounding:
                add_vendor_path(value)
        elif grounding:
            for value in str(grounding).split(","):
                add_vendor_path(value.strip())
    status = vendor_raw_source_status(root=root_path, indexed_sources=[])
    curated_by_doc = {
        str(item.get("vendor_doc") or ""): item
        for item in status.get("curated_sources") or []
        if isinstance(item, dict)
    }
    sources = []
    unmatched = []
    for vendor_doc in cited_vendor_docs:
        curated = curated_by_doc.get(vendor_doc)
        if not curated or not curated.get("complete"):
            unmatched.append(f"docs/rag/vendor/{vendor_doc}")
            continue
        sources.append(
            {
                "vendor_doc": vendor_doc,
                "curated_source": f"docs/rag/vendor/{vendor_doc}",
                "raw_source_ids": curated.get("raw_source_ids") or [],
                "source_urls": curated.get("source_urls") or [],
                "raw_files": curated.get("raw_files") or [],
                "source_types": curated.get("source_types") or [],
                "raw_snapshots": curated.get("raw_snapshots") or [],
                "complete": curated.get("complete") is True,
            }
        )
    return {
        "policy": "raw snapshots are traceability evidence and are not indexed wholesale",
        "manifest_exists": status.get("manifest_exists") is True,
        "manifest_schema_version": status.get("manifest_schema_version"),
        "generated_at": status.get("generated_at"),
        "raw_sources_indexed": status.get("raw_sources_indexed") is True,
        "curated_provenance_ok": status.get("curated_provenance_ok") is True,
        "sources": sources,
        "unmatched_citations": unmatched,
    }


def _metadata(output: dict[str, Any]) -> dict[str, Any]:
    metadata = output.get("metadata") or output.get("metadata_json") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return metadata if isinstance(metadata, dict) else {}


def _is_previewable_report(report: dict[str, Any]) -> bool:
    relative_path = str(report.get("relative_path") or report.get("path") or "").lower()
    content_type = str(report.get("content_type") or "").lower()
    return (
        content_type.startswith("image/")
        or relative_path.endswith(".svg")
        or relative_path.endswith(".png")
        or relative_path.endswith(".png")
        or relative_path.endswith(".jpg")
        or relative_path.endswith(".jpeg")
        or relative_path.endswith(".webp")
    )


def _backend_context_answer(backend_context: dict | None) -> str:
    if not backend_context:
        return ""
    parts = []
    project_id = backend_context.get("project_id")
    if project_id is not None:
        parts.append(f"Project {project_id} backend state is the primary source of truth.")
    tasks = backend_context.get("tasks") or []
    if tasks:
        task_bits = []
        for task in tasks[:5]:
            workflow_type = task.get("workflow_type", "unknown_workflow")
            runtime_workflow_type = task.get("runtime_workflow_type")
            runtime_note = (
                f" via runtime runner {runtime_workflow_type}"
                if runtime_workflow_type and runtime_workflow_type != workflow_type
                else ""
            )
            task_bits.append(
                "task {id}: {workflow_type}{runtime_note} is {status} ({progress}%){error}".format(
                    id=task.get("id", "unknown"),
                    workflow_type=workflow_type,
                    runtime_note=runtime_note,
                    status=task.get("status", "unknown"),
                    progress=task.get("progress", 0),
                    error=f", error={task.get('error_message')}" if task.get("error_message") else "",
                )
            )
        parts.append("Recent tasks: " + "; ".join(task_bits) + ".")
    outputs = backend_context.get("outputs") or []
    if outputs:
        output_bits = []
        for output in outputs[:5]:
            metadata = _metadata(output)
            output_bits.append(
                "task {task_id} {output_type} output {path}{kind}".format(
                    task_id=output.get("task_id", "unknown"),
                    output_type=output.get("output_type", "unknown"),
                    path=output.get("path", ""),
                    kind=f" ({metadata.get('kind')})" if metadata.get("kind") else "",
                )
            )
        parts.append("Registered outputs: " + "; ".join(output_bits) + ".")
    result_summaries = backend_context.get("result_summaries") or []
    if result_summaries:
        summary_bits = []
        for summary in result_summaries[:5]:
            workflow_type = summary.get("workflow_type", "unknown_workflow")
            workflow_metadata = summary.get("workflow_metadata") or {}
            metadata_workflow_type = workflow_metadata.get("workflow_type")
            display_name = workflow_metadata.get("display_name") or workflow_type
            report_only_note = ""
            if workflow_metadata.get("is_report_only") is False:
                report_only_note = " not report-only"
            elif workflow_metadata.get("is_report_only") is True:
                report_only_note = " report-only"
            metadata_note = (
                f"; public workflow metadata {metadata_workflow_type}{report_only_note}"
                if metadata_workflow_type and metadata_workflow_type != workflow_type
                else report_only_note
            )
            summary_bits.append(
                "task {task_id}: {display_name} for {modality} with stable workflow id {workflow_type}{metadata_note}".format(
                    task_id=summary.get("task_id", "unknown"),
                    display_name=display_name,
                    modality=summary.get("modality", "unknown modality"),
                    workflow_type=workflow_type,
                    metadata_note=metadata_note,
                )
            )
        parts.append("Result summaries: " + "; ".join(summary_bits) + ".")
    supported_workflows = backend_context.get("supported_workflows") or []
    if supported_workflows:
        workflow_bits = []
        for workflow in supported_workflows[:5]:
            workflow_type = workflow.get("workflow_type", "unknown_workflow")
            runtime_workflow_type = workflow.get("runtime_workflow_type")
            lane = workflow.get("lane", "unknown_lane")
            display_name = workflow.get("display_name", workflow_type)
            capability_summary = workflow.get("capability_summary", "")
            alias_note = (
                f" runtime runner {runtime_workflow_type}"
                if runtime_workflow_type and runtime_workflow_type != workflow_type
                else ""
            )
            report_only_note = ""
            if workflow.get("is_report_only") is False:
                report_only_note = " not report-only"
            elif workflow.get("is_report_only") is True:
                report_only_note = " report-only"
            confirmation_note = " requires human confirmation" if workflow.get("requires_confirmation") else ""
            capability_note = f" Capability: {capability_summary}" if capability_summary else ""
            workflow_bits.append(
                f"{workflow_type} is {lane}: {display_name}{alias_note}{report_only_note}{confirmation_note}.{capability_note}"
            )
        parts.append("Supported workflow capabilities: " + " ".join(workflow_bits) + ".")
    return " ".join(parts)


class RAGState(TypedDict, total=False):
    query: str
    root: str
    backend_context: dict
    citations: list[dict]
    answer: str
    dependencies: dict
    grounding_policy: dict
    mode: str
    retrieval_mode: str
    retrieval_source: str
    intent: str
    recommended_next_step: str
    tool_chain_hint: str
    tool_invocations: list[dict]


def _classify_intent(query: str) -> str:
    lowered = query.lower()
    if _is_launchability_query(query):
        return "launchability"
    if any(token in lowered for token in ("status", "progress", "task", "tasks", "state", "进度", "状态", "任务", "结果", "result-summary", "report", "报告")):
        return "status"
    if any(token in lowered for token in ("怎么", "如何", "next", "下一步", "tool", "调用", "工具", "理解")):
        return "next_step"
    if any(token in lowered for token in ("rag", "知识库", "文档", "planning", "skill")):
        return "knowledge"
    return "general"


def _tool_chain_hint(intent: str) -> str:
    if intent == "launchability":
        return "Use workflow_eligibility and the workflow launchability matrix; do not create production tasks from RAG answers."
    if intent == "status":
        return "Inspect backend tasks and outputs, then surface result-summary and scientific report artifacts."
    if intent == "next_step":
        return "Inspect current task state, registered outputs, and report coverage before recommending the next workflow gate."
    if intent == "knowledge":
        return "Use planning files, skills, and indexed docs as support, but keep backend state dominant."
    return "Answer from backend state first, then supplement with local knowledge if needed."


def _query_has_all(query: str, terms: tuple[str, ...]) -> bool:
    lowered = query.lower()
    return all(term in lowered for term in terms)


def _policy_answer(query: str, intent: str, citations: list[dict[str, Any]]) -> str:
    lowered = query.lower()
    if intent == "launchability" and any(term in lowered for term in ("mriqc", "dpabi", "qsiprep")):
        return (
            "Do not create production tasks from this matrix. "
            "workflow_eligibility remains authoritative for launchability on a specific uploaded series. "
            "MRIQC and QSIPrep-related lanes are incubation_reference unless the backend registry promotes them, "
            "and DPABI is unsupported_external in the current Image Agent product. "
            "Use backend registry, preflight, task records, result-summary, and artifact-manifest evidence before making success claims."
        )
    if "elasticsearch" in lowered and "hybrid" in lowered:
        return (
            "Elasticsearch hybrid RAG retrieves curated Image Agent context with BM25 lexical retrieval, "
            "dense vector kNN over the embedding field, and RRF fusion of ranked results. "
            "It cites safe repo-relative docs/rag or docs/skills Markdown sources only; raw official snapshots are provenance evidence and are not indexed wholesale."
        )
    if "fixed workflow" in lowered and ("production task" in lowered or "create" in lowered):
        return (
            "Before a fixed workflow creates a production task, Image Agent must pass the workflow registry, "
            "run preflight checks, obtain human confirmation, verify the confirmation fingerprint, call "
            "task_service.create_series_task(), and then execute through the pipeline runner."
        )
    if "dwi" in lowered and any(term in lowered for term in ("produce", "output", "workflow", "dti", "fast gpu")):
        return (
            "The dwi_fast_gpu_dti workflow produces FA/MD/AD/RD maps, MNI152 maps when registration succeeds, "
            "atlas regional TSV tables, QC/provenance files, result-summary JSON, and an HTML scientific report. "
            "It is not full QSIPrep and not full QSIRecon; fixed execution still requires registry, preflight, "
            "human confirmation, confirmation fingerprint, task_service.create_series_task(), and the pipeline runner."
        )
    if any(term in lowered for term in ("upload", "sidecar", "bval", "bvec", "nifti", "dicom")):
        return (
            "For a complete DWI sidecar set, upload the DWI NIfTI plus matching JSON sidecar, bval, and bvec files. "
            "Fast GPU DTI also needs phase-encoding/readout metadata in the JSON sidecar. T1 uses T1w NIfTI plus JSON, "
            "BOLD uses BOLD NIfTI plus task/timing JSON, and DICOM archives should be converted or staged before production launch."
        )
    if any(term in lowered for term in ("diagnose", "diagnosis", "dementia", "tumor", "stroke", "normal", "abnormal", "clinical interpretation")):
        return (
            "Image Agent must not diagnose from workflow outputs. It can explain preprocessing, derived features, QC, "
            "and registered artifacts, but clinical interpretation should come from a qualified radiologist or clinician."
        )
    if _query_has_all(lowered, ("registry", "preflight")):
        return (
            "The registry defines stable workflow_type capability and requirements, while preflight resolves series identity, inputs, sidecars, Docker or host tools, GPU capability, mounts, and output writeability before confirmation."
        )
    return ""


def _launchability_boundary_note(intent: str) -> str:
    if intent != "launchability":
        return ""
    return (
        "Do not create production tasks from this matrix. "
        "workflow_eligibility remains authoritative for launchability. "
        "/tasks/{task_id}/result-summary remains authoritative for completed outputs."
    )


def _should_prepend_launchability_boundary(query: str, intent: str) -> bool:
    if intent != "launchability":
        return False
    lowered = query.lower()
    if "fixed workflow" in lowered and ("production task" in lowered or "create" in lowered):
        return False
    return True


def _tool_invocation(name: str, status: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"tool": name, "status": status, "result": result}


def _inspect_task_status(backend_context: dict[str, Any]) -> dict[str, Any]:
    tasks = backend_context.get("tasks") or []
    by_status: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    latest = tasks[0] if tasks else None
    return {
        "task_count": len(tasks),
        "by_status": by_status,
        "latest_task": latest,
        "running_task_ids": [task.get("id") for task in tasks if task.get("status") == "running"],
        "failed_task_ids": [task.get("id") for task in tasks if task.get("status") == "failed"],
        "completed_task_ids": [task.get("id") for task in tasks if task.get("status") == "completed"],
    }


def _inspect_registered_outputs(backend_context: dict[str, Any]) -> dict[str, Any]:
    outputs = backend_context.get("outputs") or []
    by_kind: dict[str, int] = {}
    by_task: dict[str, int] = {}
    result_summary_tasks: list[Any] = []
    scientific_report_tasks: list[Any] = []
    for output in outputs:
        metadata = _metadata(output)
        kind = str(metadata.get("kind") or output.get("output_type") or "unknown")
        task_id = output.get("task_id")
        path = str(output.get("path") or "")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_task[str(task_id)] = by_task.get(str(task_id), 0) + 1
        if kind == "result_summary" or path.endswith("_result_summary.json"):
            result_summary_tasks.append(task_id)
        if kind == "scientific_report_summary" or path.endswith("_scientific_report_summary.json"):
            scientific_report_tasks.append(task_id)
    return {
        "output_count": len(outputs),
        "by_kind": by_kind,
        "outputs_by_task": by_task,
        "result_summary_tasks": list(dict.fromkeys(result_summary_tasks)),
        "scientific_report_tasks": list(dict.fromkeys(scientific_report_tasks)),
    }


def _inspect_scientific_reports(backend_context: dict[str, Any]) -> dict[str, Any]:
    outputs = backend_context.get("outputs") or []
    report_summaries = []
    missing_paths = []
    result_summary_reports = []
    for summary in backend_context.get("result_summaries") or []:
        reports = ((summary.get("outputs") or {}).get("reports") or [])
        if not isinstance(reports, list):
            reports = []
        report_count = len(reports)
        figure_count = sum(1 for report in reports if isinstance(report, dict) and _is_previewable_report(report))
        result_summary_reports.append(
            {
                "task_id": summary.get("task_id"),
                "modality": summary.get("modality"),
                "report_count": report_count,
                "figure_count": figure_count,
                "has_index_html": any((report.get("relative_path") or "").endswith("reports/index.html") for report in reports if isinstance(report, dict)),
                "has_manifest": any((report.get("relative_path") or "").endswith("reports/report_manifest.json") for report in reports if isinstance(report, dict)),
            }
        )
    for output in outputs:
        metadata = _metadata(output)
        path_value = output.get("path") or ""
        kind = metadata.get("kind")
        if kind != "scientific_report_summary" and not str(path_value).endswith("_scientific_report_summary.json"):
            continue
        item: dict[str, Any] = {"task_id": output.get("task_id"), "path": str(path_value)}
        path = Path(str(path_value)) if path_value else None
        if not path or not path.exists():
            item["exists"] = False
            missing_paths.append(str(path_value))
            report_summaries.append(item)
            continue
        item["exists"] = True
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            item["valid_json"] = False
            report_summaries.append(item)
            continue
        reports = ((payload.get("outputs") or {}).get("reports") or [])
        item["valid_json"] = True
        item["modality"] = payload.get("modality")
        item["report_count"] = len(reports) if isinstance(reports, list) else 0
        item["has_index_html"] = any((report.get("relative_path") or "").endswith("reports/index.html") for report in reports if isinstance(report, dict))
        item["has_manifest"] = any((report.get("relative_path") or "").endswith("reports/report_manifest.json") for report in reports if isinstance(report, dict))
        report_summaries.append(item)
    return {
        "scientific_report_summary_count": len(report_summaries),
        "report_summaries": report_summaries,
        "result_summary_reports": result_summary_reports,
        "missing_paths": missing_paths,
    }


def _recommend_next_action(intent: str, tool_results: list[dict[str, Any]]) -> dict[str, Any]:
    task_result = next((item["result"] for item in tool_results if item.get("tool") == "inspect_task_status"), {})
    output_result = next((item["result"] for item in tool_results if item.get("tool") == "inspect_registered_outputs"), {})
    report_result = next((item["result"] for item in tool_results if item.get("tool") == "inspect_scientific_reports"), {})
    if task_result.get("running_task_ids"):
        action = "Monitor running tasks and read logs before launching new work."
    elif task_result.get("failed_task_ids"):
        action = (
            "Open failed task logs, identify the first concrete runtime error, then draft a repair plan. "
            "Any retry requires a new registry preflight and human confirmation before task creation."
        )
    elif output_result.get("result_summary_tasks") and not report_result.get("scientific_report_summary_count") and not report_result.get("result_summary_reports"):
        action = (
            "Draft a report-registration repair plan for the completed result-summary task. "
            "Generating or rerunning report artifacts requires human confirmation before task creation."
        )
    elif report_result.get("missing_paths"):
        action = (
            "Draft a repair plan for missing scientific report registrations and verify artifact paths. "
            "Any report generation rerun requires a new preflight and human confirmation."
        )
    elif report_result.get("result_summary_reports"):
        action = "Review the result-summary report figures in the frontend and use the registered HTML/PNG artifacts for scientific interpretation."
    elif intent == "next_step":
        action = "Pick the most recent completed task, inspect its result-summary and report bundle, then suggest the next workflow gate."
    else:
        action = _tool_chain_hint(intent)
    return {"recommended_action": action, "policy": "read-only ObserveRepair agent tool chain; no retry, rerun, or long workflow is launched from chat"}


def run_agent_tool_chain(query: str, backend_context: dict | None = None) -> list[dict]:
    context = backend_context or {}
    intent = _classify_intent(query)
    invocations = [
        _tool_invocation("inspect_task_status", "ok", _inspect_task_status(context)),
        _tool_invocation("inspect_registered_outputs", "ok", _inspect_registered_outputs(context)),
    ]
    if intent in {"status", "next_step", "general"}:
        invocations.append(_tool_invocation("inspect_scientific_reports", "ok", _inspect_scientific_reports(context)))
        invocations.append(_tool_invocation("recommend_next_action", "ok", _recommend_next_action(intent, invocations)))
    return invocations


def _fallback_rag_response(query: str, root: Path | str | None = None, backend_context: dict | None = None, limit: int = 5) -> dict:
    citation_context = _citation_context(query, root=root, limit=limit)
    citations = citation_context["citations"]
    cited_text = " ".join(hit["excerpt"] for hit in citations[:3])
    backend_answer = _backend_context_answer(backend_context)
    intent = _classify_intent(query)
    launchability_note = _launchability_boundary_note(intent) if _should_prepend_launchability_boundary(query, intent) else ""
    policy_answer = _policy_answer(query, intent, citations)
    if backend_answer and cited_text:
        answer = f"{backend_answer} Relevant local docs: {cited_text}"
    elif backend_answer:
        answer = backend_answer
    elif policy_answer:
        answer = policy_answer
    else:
        answer = cited_text or "No backend records or local planning/skill documents matched the query."
    if launchability_note:
        answer = f"{launchability_note} {answer}"
    return {
        "answer": answer,
        "citations": citations,
        "retrieval_mode": citation_context["retrieval_mode"],
        "retrieval_source": citation_context["retrieval_source"],
        "retrieval_latency_ms": citation_context.get("retrieval_latency_ms", 0.0),
        **(
            {"elasticsearch_hybrid_query": citation_context["elasticsearch_hybrid_query"]}
            if citation_context.get("elasticsearch_hybrid_query")
            else {}
        ),
        "raw_source_evidence": _raw_source_evidence_for_citations(citations, root=root),
        "backend_context": backend_context or {},
        "grounding_policy": grounding_policy(),
        "dependencies": dependency_status(),
        "intent": intent,
        "recommended_next_step": _tool_chain_hint(intent),
        "tool_chain_hint": _tool_chain_hint(intent),
        "tool_invocations": run_agent_tool_chain(query, backend_context=backend_context),
        "mode": "fallback",
    }


def _langgraph_app():
    if not _package_available("langgraph"):
        return None
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    def route(state: RAGState) -> str:
        return _classify_intent(state.get("query", ""))

    def ingest_backend(state: RAGState) -> dict[str, Any]:
        intent = _classify_intent(state.get("query", ""))
        return {
            "answer": _backend_context_answer(state.get("backend_context")),
            "intent": intent,
            "tool_chain_hint": _tool_chain_hint(intent),
            "recommended_next_step": _tool_chain_hint(intent),
        }

    def invoke_tools(state: RAGState) -> dict[str, Any]:
        return {"tool_invocations": run_agent_tool_chain(state.get("query", ""), backend_context=state.get("backend_context"))}

    def retrieve_docs(state: RAGState) -> dict[str, Any]:
        citation_context = _citation_context(state.get("query", ""), root=state.get("root"), limit=5)
        return {
            "citations": citation_context["citations"],
            "retrieval_mode": citation_context["retrieval_mode"],
            "retrieval_source": citation_context["retrieval_source"],
            "retrieval_latency_ms": citation_context["retrieval_latency_ms"],
            **(
                {"elasticsearch_hybrid_query": citation_context["elasticsearch_hybrid_query"]}
                if citation_context.get("elasticsearch_hybrid_query")
                else {}
            ),
        }

    def synthesize(state: RAGState) -> dict[str, Any]:
        backend_answer = state.get("answer", "")
        citations = state.get("citations") or []
        cited_text = " ".join(hit["excerpt"] for hit in citations[:3])
        intent = _classify_intent(state.get("query", ""))
        launchability_note = (
            _launchability_boundary_note(intent)
            if _should_prepend_launchability_boundary(state.get("query", ""), intent)
            else ""
        )
        policy_answer = _policy_answer(state.get("query", ""), intent, citations)
        answer = backend_answer
        if backend_answer and cited_text:
            answer = f"{backend_answer} Relevant local docs: {cited_text}"
        elif policy_answer:
            answer = policy_answer
        elif cited_text and not backend_answer:
            answer = cited_text
        elif not answer:
            answer = "No backend records or local planning/skill documents matched the query."
        if launchability_note:
            answer = f"{launchability_note} {answer}"
        return {
            "answer": answer,
            "intent": intent,
            "retrieval_mode": state.get("retrieval_mode"),
            "retrieval_source": state.get("retrieval_source"),
            "retrieval_latency_ms": state.get("retrieval_latency_ms"),
            "elasticsearch_hybrid_query": state.get("elasticsearch_hybrid_query"),
            "recommended_next_step": _tool_chain_hint(intent),
            "tool_chain_hint": _tool_chain_hint(intent),
            "tool_invocations": state.get("tool_invocations") or [],
        }

    graph = StateGraph(RAGState)
    graph.add_node("backend", ingest_backend)
    graph.add_node("tools", invoke_tools)
    graph.add_node("retrieve", retrieve_docs)
    graph.add_node("synthesize", synthesize)
    graph.set_entry_point("backend")
    graph.add_edge("backend", "tools")
    graph.add_conditional_edges("tools", route, {"status": "retrieve", "next_step": "retrieve", "knowledge": "retrieve", "launchability": "retrieve", "general": "retrieve"})
    graph.add_edge("retrieve", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


def build_rag_response(query: str, root: Path | str | None = None, backend_context: dict | None = None, limit: int = 5) -> dict:
    app = _langgraph_app()
    base_state: RAGState = {
        "query": query,
        "root": str(root or Path.cwd()),
        "backend_context": backend_context or {},
        "dependencies": dependency_status(),
        "grounding_policy": grounding_policy(),
    }
    if app is not None:
        try:
            result = app.invoke(base_state)
            citation_context = _citation_context(query, root=root, limit=limit)
            result["dependencies"] = dependency_status()
            result["grounding_policy"] = grounding_policy()
            result["backend_context"] = backend_context or {}
            result["mode"] = "langgraph"
            result.setdefault("citations", citation_context["citations"])
            result.setdefault("retrieval_mode", citation_context["retrieval_mode"])
            result.setdefault("retrieval_source", citation_context["retrieval_source"])
            result.setdefault("retrieval_latency_ms", citation_context.get("retrieval_latency_ms", 0.0))
            if citation_context.get("elasticsearch_hybrid_query"):
                result.setdefault("elasticsearch_hybrid_query", citation_context["elasticsearch_hybrid_query"])
            safe_query_evidence = _safe_elasticsearch_hybrid_query_evidence(
                result.get("elasticsearch_hybrid_query")
            )
            if safe_query_evidence:
                result["elasticsearch_hybrid_query"] = safe_query_evidence
            else:
                result.pop("elasticsearch_hybrid_query", None)
            result["raw_source_evidence"] = _raw_source_evidence_for_citations(result.get("citations") or [], root=root)
            result.setdefault("tool_chain_hint", _tool_chain_hint(result.get("intent", _classify_intent(query))))
            result.setdefault("recommended_next_step", result.get("tool_chain_hint"))
            result.setdefault("tool_invocations", run_agent_tool_chain(query, backend_context=backend_context))
            return result
        except Exception:
            pass
    return _fallback_rag_response(query, root=root, backend_context=backend_context, limit=limit)
