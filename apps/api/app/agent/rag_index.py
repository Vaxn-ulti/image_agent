from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Callable

import httpx


INDEX_GLOBS = ("docs/rag/**/*.md", "docs/skills/**/SKILL.md", "docs/skills/**/references/*.md")
VENDOR_RAW_SOURCES_MANIFEST = "docs/rag/vendor/raw-sources/manifest.json"
VENDOR_RAW_SOURCES_PREFIX = "docs/rag/vendor/raw-sources/"
RAG_POINTER_GLOBS = ("docs/rag/workflows/**/*.md", "docs/rag/contracts/**/*.md")
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 160
ELASTICSEARCH_INDEX_NAME = "image_agent_rag"
ELASTICSEARCH_URL_ENV = "IMAGE_AGENT_ELASTICSEARCH_URL"
ELASTICSEARCH_API_KEY_ENV = "IMAGE_AGENT_ELASTICSEARCH_API_KEY"
ELASTICSEARCH_INDEX_ENV = "IMAGE_AGENT_ELASTICSEARCH_INDEX"
ELASTICSEARCH_DENSE_VECTOR_FIELD = "embedding"
ELASTICSEARCH_DENSE_VECTOR_DIMS = 64
ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER = "local_hashing"
ELASTICSEARCH_LOCAL_EMBEDDING_MODEL = "local-token-hash-v1"
RAG_EMBEDDING_PROVIDER_ENV = "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER"
RAG_EMBEDDING_MODEL_ENV = "IMAGE_AGENT_RAG_EMBEDDING_MODEL"
RAG_EMBEDDING_API_KEY_ENV = "IMAGE_AGENT_RAG_EMBEDDING_API_KEY"
RAG_EMBEDDING_BASE_URL_ENV = "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL"
RAG_EMBEDDING_TIMEOUT_ENV = "IMAGE_AGENT_RAG_EMBEDDING_TIMEOUT_SECONDS"
ELASTICSEARCH_OFFICIAL_SOURCES = [
    "https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html",
    "https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html",
    "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
]
EmbeddingVectorFn = Callable[[str], list[float]]


def _env_first(names: list[str], default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _privacy_safe_symbol(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 140 and all(
        char.isalnum() or char in "_.-" for char in value
    )


def _elasticsearch_index_name() -> str:
    configured = os.environ.get(ELASTICSEARCH_INDEX_ENV, "").strip()
    if _privacy_safe_symbol(configured):
        return configured
    return ELASTICSEARCH_INDEX_NAME


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


def _source_type_for(source: str, metadata: dict[str, Any]) -> str:
    if metadata.get("source_type"):
        return str(metadata["source_type"])
    normalized = source.replace("\\", "/")
    if normalized.startswith("docs/rag/vendor/") and not normalized.startswith(VENDOR_RAW_SOURCES_PREFIX):
        return "rag_vendor"
    if "/docs/skills/" in "/" + normalized:
        return "skill_reference"
    if "/docs/rag/" in "/" + normalized:
        return "rag_document"
    return "local_document"


def _normalize_source_path(source: str) -> str:
    return source.replace("\\", "/")


def _is_vendor_raw_source(source: str) -> bool:
    return _normalize_source_path(source).startswith(VENDOR_RAW_SOURCES_PREFIX)


def _is_safe_raw_source_file_name(file_name: str) -> bool:
    normalized = file_name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return bool(file_name) and "/" not in normalized and not (
        normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha())
        or ".." in parts
    )


def _is_safe_indexed_source(source: Any) -> bool:
    if not isinstance(source, str) or not source.strip():
        return False
    normalized = source.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if (
        normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha())
        or ".." in parts
    ):
        return False
    return (
        normalized.endswith(".md")
        and "/raw-sources/" not in f"/{normalized}"
        and (normalized.startswith("docs/rag/") or normalized.startswith("docs/skills/"))
    )


def _metadata_list(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _priority_for(source_type: str, metadata: dict[str, Any]) -> int:
    raw = str(metadata.get("priority", "")).lower()
    if raw == "policy" or source_type == "skill_reference":
        return 80
    if source_type.startswith("rag_"):
        return 50
    return 30


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\\-]+", text) if len(token) > 2]


def _chunk_text(text: str) -> list[str]:
    cleaned = text.strip()
    if len(cleaned) <= CHUNK_SIZE:
        return [cleaned] if cleaned else []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + CHUNK_SIZE)
        chunks.append(cleaned[start:end].strip())
        if end == len(cleaned):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return [chunk for chunk in chunks if chunk]


def _collect_documents(root: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for pattern in INDEX_GLOBS:
        for path in root.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            text = path.read_text(encoding="utf-8", errors="ignore")
            metadata, body = _parse_frontmatter(text)
            source = path.relative_to(root).as_posix()
            if _is_vendor_raw_source(source):
                continue
            sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            source_type = _source_type_for(source, metadata)
            documents.append(
                {
                    "source": source,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256,
                    "metadata": {
                        **metadata,
                        "source": source,
                        "source_type": source_type,
                        "sha256": sha256,
                        "priority_score": _priority_for(source_type, metadata),
                    },
                    "title": next((line.lstrip("#").strip() for line in body.splitlines() if line.strip().startswith("#")), path.stem),
                }
            )
    return documents


def _llama_index_available() -> bool:
    try:
        import llama_index  # noqa: F401
    except Exception:
        return False
    return True


def build_local_rag_index(
    *,
    root: Path | str,
    persist_dir: Path | str | None = None,
    elasticsearch_client: Any | None = None,
    embedding_vector_fn: EmbeddingVectorFn | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    persist_path = Path(persist_dir or root_path / ".rag_index")
    persist_path.mkdir(parents=True, exist_ok=True)
    documents = _collect_documents(root_path)
    chunks = _build_chunks(root_path, documents)
    if embedding_vector_fn is None:
        configured_embedding = _configured_embedding_provider()
        if configured_embedding is not None:
            embedding_vector_fn, embedding_provider, embedding_model = configured_embedding
    embedding_context = _embedding_context(
        embedding_vector_fn=embedding_vector_fn,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        chunks=chunks,
    )
    index_name = _elasticsearch_index_name()
    elasticsearch_status = _persist_elasticsearch_hybrid_contract(chunks, persist_path, embedding_context=embedding_context)
    elasticsearch_status.update(
        _persist_elasticsearch_hybrid_index(
            chunks,
            elasticsearch_client=elasticsearch_client,
            index_name=index_name,
            embedding_context=embedding_context,
        )
    )
    _persist_llama_index(chunks, persist_path)
    manifest = {
        "engine": "elasticsearch_hybrid",
        "semantic_index": True,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "documents": documents,
        "hybrid_search": _elasticsearch_hybrid_metadata(elasticsearch_status),
        "fallback_engine": "llama_index" if _llama_index_available() else "local_manifest",
        "note": "Persistent local RAG index for docs/rag and docs/skills. Writes an Elasticsearch hybrid BM25+dense-vector RRF contract and uses local chunk retrieval as deterministic fallback when Elasticsearch is not connected.",
    }
    (persist_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (persist_path / "chunks.jsonl").write_text(
        "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    return manifest


def local_rag_index_status(*, root: Path | str, persist_dir: Path | str | None = None) -> dict[str, Any]:
    root_path = Path(root)
    persist_path = Path(persist_dir or root_path / ".rag_index")
    manifest_path = persist_path / "manifest.json"
    chunks_path = persist_path / "chunks.jsonl"
    status: dict[str, Any] = {
        "persist_dir": str(persist_path),
        "exists": persist_path.exists(),
        "manifest_exists": manifest_path.exists(),
        "chunks_exists": chunks_path.exists(),
        "engine": None,
        "semantic_index": False,
        "document_count": 0,
        "chunk_count": 0,
        "indexed_sources": [],
        "missing_sources": [],
    }
    if not manifest_path.exists():
        return status
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        status["error"] = f"Could not read RAG manifest: {exc}"
        return status
    documents = manifest.get("documents") or []
    indexed_sources = [str(document.get("source")) for document in documents if document.get("source")]
    status.update(
        {
            "engine": manifest.get("engine"),
            "semantic_index": bool(manifest.get("semantic_index")),
            "hybrid_search": manifest.get("hybrid_search") or {},
            "document_count": int(manifest.get("document_count") or len(documents)),
            "chunk_count": int(manifest.get("chunk_count") or 0),
            "indexed_sources": indexed_sources,
            "missing_sources": [source for source in indexed_sources if not (root_path / source).exists()],
        }
    )
    if chunks_path.exists() and status["chunk_count"] == 0:
        status["chunk_count"] = sum(1 for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip())
    return status


def vendor_raw_source_status(*, root: Path | str, indexed_sources: list[str] | None = None) -> dict[str, Any]:
    root_path = Path(root)
    manifest_path = root_path / VENDOR_RAW_SOURCES_MANIFEST
    status: dict[str, Any] = {
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "source_count": 0,
        "vendor_doc_count": 0,
        "missing_files": [],
        "hash_mismatches": [],
        "indexed_raw_sources": [],
        "raw_sources_indexed": False,
        "curated_sources": [],
        "curated_provenance_issues": [],
        "curated_provenance_ok": False,
        "note": "Raw official source snapshots are traceability evidence and should not be indexed wholesale.",
    }
    if not manifest_path.exists():
        return status
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        status["error"] = f"Could not read vendor raw-source manifest: {exc}"
        return status
    sources = manifest.get("sources") or []
    raw_files = set()
    vendor_docs = {
        path.name
        for path in (root_path / "docs" / "rag" / "vendor").glob("*.md")
        if path.is_file()
    }
    sources_by_id: dict[str, dict[str, Any]] = {}
    source_file_integrity_issues: dict[str, dict[str, str]] = {}
    for source in sources:
        source_id = str(source.get("id") or "")
        if source_id:
            sources_by_id[source_id] = source
        file_name = str(source.get("file") or "")
        vendor_doc = str(source.get("vendor_doc") or "")
        if vendor_doc:
            vendor_docs.add(vendor_doc)
        if file_name:
            raw_files.add(f"docs/rag/vendor/raw-sources/{file_name}")
        if not _is_safe_raw_source_file_name(file_name):
            if file_name:
                status["missing_files"].append(file_name)
            if source_id:
                source_file_integrity_issues[source_id] = {
                    "issue": "raw_source_file_path_unsafe",
                    "file": file_name,
                }
            continue
        raw_file = manifest_path.parent / file_name if file_name else None
        if raw_file is None or not raw_file.exists():
            status["missing_files"].append(file_name)
            if source_id:
                source_file_integrity_issues[source_id] = {
                    "issue": "raw_source_file_missing",
                    "file": file_name,
                }
            continue
        raw_bytes = raw_file.read_bytes()
        if source.get("bytes") is not None and int(source.get("bytes") or 0) != len(raw_bytes):
            status["hash_mismatches"].append(file_name)
            if source_id:
                source_file_integrity_issues[source_id] = {
                    "issue": "raw_source_file_integrity_failed",
                    "file": file_name,
                }
            continue
        expected_hash = str(source.get("sha256") or "")
        if expected_hash and hashlib.sha256(raw_bytes).hexdigest() != expected_hash:
            status["hash_mismatches"].append(file_name)
            if source_id:
                source_file_integrity_issues[source_id] = {
                    "issue": "raw_source_file_integrity_failed",
                    "file": file_name,
                }
    for vendor_doc in sorted(vendor_docs):
        doc_path = root_path / "docs" / "rag" / "vendor" / vendor_doc
        curated_entry = {
            "vendor_doc": vendor_doc,
            "raw_source_ids": [],
            "source_urls": [],
            "raw_files": [],
            "source_types": [],
            "raw_snapshots": [],
            "manifest_backed": False,
            "source_url_backed": False,
            "complete": False,
        }
        if not doc_path.exists():
            status["curated_provenance_issues"].append(
                {
                    "vendor_doc": vendor_doc,
                    "issue": "missing_curated_vendor_doc",
                }
            )
            status["curated_sources"].append(curated_entry)
            continue
        metadata, _ = _parse_frontmatter(doc_path.read_text(encoding="utf-8", errors="ignore"))
        raw_source_ids = _metadata_list(metadata.get("raw_source_ids"))
        source_urls = _metadata_list(metadata.get("source_url"))
        curated_entry["raw_source_ids"] = raw_source_ids
        curated_entry["source_urls"] = source_urls
        if not raw_source_ids:
            status["curated_provenance_issues"].append(
                {
                    "vendor_doc": vendor_doc,
                    "issue": "missing_raw_source_ids",
                }
            )
            status["curated_sources"].append(curated_entry)
            continue
        valid_sources = []
        for raw_source_id in raw_source_ids:
            source = sources_by_id.get(raw_source_id)
            if source is None:
                status["curated_provenance_issues"].append(
                    {
                        "vendor_doc": vendor_doc,
                        "issue": "unknown_raw_source_id",
                        "raw_source_id": raw_source_id,
                    }
                )
                continue
            source_vendor_doc = str(source.get("vendor_doc") or "")
            if source_vendor_doc != vendor_doc:
                status["curated_provenance_issues"].append(
                    {
                        "vendor_doc": vendor_doc,
                        "issue": "raw_source_vendor_doc_mismatch",
                        "raw_source_id": raw_source_id,
                        "manifest_vendor_doc": source_vendor_doc,
                    }
                )
                continue
            if raw_source_id in source_file_integrity_issues:
                status["curated_provenance_issues"].append(
                    {
                        "vendor_doc": vendor_doc,
                        "issue": source_file_integrity_issues[raw_source_id]["issue"],
                        "raw_source_id": raw_source_id,
                        "file": source_file_integrity_issues[raw_source_id]["file"],
                    }
                )
                continue
            else:
                valid_sources.append(source)
        curated_entry["raw_files"] = [
            f"docs/rag/vendor/raw-sources/{source['file']}"
            for source in valid_sources
            if source.get("file")
        ]
        curated_entry["source_types"] = sorted(
            {str(source.get("source_type")) for source in valid_sources if source.get("source_type")}
        )
        curated_entry["raw_snapshots"] = [
            {
                "id": str(source.get("id") or ""),
                "file": f"docs/rag/vendor/raw-sources/{source['file']}",
                "url": str(source.get("url") or ""),
                "sha256": str(source.get("sha256") or ""),
                "bytes": int(source.get("bytes") or 0),
                "retrieved_at": str(source.get("retrieved_at") or ""),
                "source_type": str(source.get("source_type") or ""),
                "status": str(source.get("status") or ""),
            }
            for source in valid_sources
            if source.get("file")
        ]
        curated_entry["manifest_backed"] = len(valid_sources) == len(raw_source_ids)
        manifest_urls = {str(source.get("url") or "") for source in valid_sources if source.get("url")}
        curated_entry["source_url_backed"] = bool(source_urls) and all(source_url in manifest_urls for source_url in source_urls)
        for source_url in source_urls:
            if manifest_urls and source_url not in manifest_urls:
                status["curated_provenance_issues"].append(
                    {
                        "vendor_doc": vendor_doc,
                        "issue": "source_url_not_backed_by_raw_source_ids",
                        "source_url": source_url,
                        "raw_source_ids": raw_source_ids,
                    }
                )
        curated_entry["complete"] = bool(
            curated_entry["raw_source_ids"]
            and curated_entry["manifest_backed"]
            and curated_entry["source_url_backed"]
        )
        status["curated_sources"].append(curated_entry)
    indexed_set = {_normalize_source_path(source) for source in indexed_sources or []}
    indexed_raw = sorted(raw_files & indexed_set)
    status.update(
        {
            "source_count": len(sources),
            "vendor_doc_count": len(vendor_docs),
            "indexed_raw_sources": indexed_raw,
            "raw_sources_indexed": bool(indexed_raw),
            "curated_provenance_ok": not status["curated_provenance_issues"],
            "manifest_schema_version": manifest.get("schema_version"),
            "generated_at": manifest.get("generated_at"),
        }
    )
    return status


def rag_vendor_pointer_integrity(*, root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    raw_status = vendor_raw_source_status(root=root_path, indexed_sources=[])
    complete_vendor_docs = {
        str(item.get("vendor_doc") or "")
        for item in raw_status.get("curated_sources") or []
        if isinstance(item, dict) and item.get("complete") is True
    }
    pointers_by_doc: dict[str, list[str]] = {}
    issues: list[dict[str, str]] = []
    pointer_count = 0
    referenced_vendor_docs: set[str] = set()
    pattern = re.compile(r"docs/rag/vendor/(?!raw-sources/)([A-Za-z0-9_.-]+\.md)")
    seen_paths: set[Path] = set()
    for glob in RAG_POINTER_GLOBS:
        for path in root_path.glob(glob):
            if path in seen_paths or not path.is_file():
                continue
            seen_paths.add(path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            source_doc = path.relative_to(root_path).as_posix()
            vendor_paths = []
            for match in pattern.finditer(text):
                vendor_doc = match.group(1)
                vendor_path = f"docs/rag/vendor/{vendor_doc}"
                vendor_paths.append(vendor_path)
                referenced_vendor_docs.add(vendor_doc)
                pointer_count += 1
                if vendor_doc not in complete_vendor_docs:
                    issues.append(
                        {
                            "source_doc": source_doc,
                            "vendor_doc": vendor_doc,
                            "vendor_path": vendor_path,
                            "issue": "missing_or_incomplete_vendor_doc",
                        }
                    )
            if vendor_paths:
                pointers_by_doc[source_doc] = sorted(set(vendor_paths))
    return {
        "ok": not issues,
        "pointer_count": pointer_count,
        "issue_count": len(issues),
        "issues": issues,
        "referenced_vendor_docs": sorted(referenced_vendor_docs),
        "pointers_by_doc": dict(sorted(pointers_by_doc.items())),
        "raw_source_manifest_exists": raw_status.get("manifest_exists") is True,
        "curated_provenance_ok": raw_status.get("curated_provenance_ok") is True,
    }


def rag_vendor_coverage_catalog(
    *,
    root: Path | str,
    indexed_sources: list[str] | None = None,
) -> dict[str, Any]:
    raw_status = vendor_raw_source_status(root=root, indexed_sources=indexed_sources)
    pointer_status = rag_vendor_pointer_integrity(root=root)
    referenced_by_vendor: dict[str, list[str]] = {}
    pointers_by_doc = pointer_status.get("pointers_by_doc") if isinstance(pointer_status.get("pointers_by_doc"), dict) else {}
    for source_doc, vendor_paths in pointers_by_doc.items():
        if not isinstance(source_doc, str) or not isinstance(vendor_paths, list):
            continue
        for vendor_path in vendor_paths:
            if not isinstance(vendor_path, str):
                continue
            vendor_doc = Path(vendor_path.replace("\\", "/")).name
            referenced_by_vendor.setdefault(vendor_doc, []).append(source_doc)

    vendors = []
    curated_sources = raw_status.get("curated_sources") if isinstance(raw_status.get("curated_sources"), list) else []
    for item in curated_sources:
        if not isinstance(item, dict):
            continue
        vendor_doc = str(item.get("vendor_doc") or "")
        if not vendor_doc:
            continue
        raw_source_ids = [str(value) for value in item.get("raw_source_ids") or [] if value]
        source_urls = [str(value) for value in item.get("source_urls") or [] if value]
        source_types = sorted({str(value) for value in item.get("source_types") or [] if value})
        vendors.append(
            {
                "vendor_doc": vendor_doc,
                "vendor_path": f"docs/rag/vendor/{vendor_doc}",
                "complete": item.get("complete") is True,
                "manifest_backed": item.get("manifest_backed") is True,
                "source_url_backed": item.get("source_url_backed") is True,
                "raw_source_count": len(raw_source_ids),
                "source_url_count": len(source_urls),
                "source_types": source_types,
                "referenced_by": sorted(set(referenced_by_vendor.get(vendor_doc, []))),
                "raw_source_ids": raw_source_ids,
            }
        )
    vendors.sort(key=lambda item: item["vendor_doc"])
    complete_count = sum(1 for item in vendors if item["complete"])
    issue_count = len(raw_status.get("curated_provenance_issues") or []) + int(pointer_status.get("issue_count") or 0)
    if not raw_status.get("manifest_exists"):
        status = "missing_manifest"
    elif issue_count:
        status = "issues"
    else:
        status = "complete"
    return {
        "status": status,
        "policy": "curated summaries are indexed; raw snapshots are provenance evidence only",
        "manifest_exists": raw_status.get("manifest_exists") is True,
        "manifest_schema_version": raw_status.get("manifest_schema_version"),
        "generated_at": raw_status.get("generated_at"),
        "vendor_doc_count": len(vendors),
        "complete_vendor_doc_count": complete_count,
        "incomplete_vendor_doc_count": len(vendors) - complete_count,
        "raw_source_count": int(raw_status.get("source_count") or 0),
        "raw_sources_indexed": raw_status.get("raw_sources_indexed") is True,
        "curated_provenance_ok": raw_status.get("curated_provenance_ok") is True,
        "pointer_integrity_ok": pointer_status.get("ok") is True,
        "pointer_count": int(pointer_status.get("pointer_count") or 0),
        "issue_count": issue_count,
        "vendors": vendors,
    }


def _build_chunks(root: Path, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document in documents:
        path = root / document["source"]
        text = path.read_text(encoding="utf-8", errors="ignore")
        _, body = _parse_frontmatter(text)
        for index, chunk in enumerate(_chunk_text(body)):
            metadata = dict(document["metadata"])
            metadata["chunk_index"] = index
            chunks.append(
                {
                    "id": hashlib.sha256(f"{document['source']}:{index}:{document['sha256']}".encode("utf-8")).hexdigest()[:24],
                    "source": document["source"],
                    "title": document["title"],
                    "text": chunk,
                    "metadata": metadata,
                    "tokens": _tokens(chunk),
                }
            )
    return chunks


def _persist_llama_index(chunks: list[dict[str, Any]], persist_path: Path) -> None:
    if not _llama_index_available():
        return
    try:
        from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
        from llama_index.core.embeddings import MockEmbedding

        Settings.embed_model = MockEmbedding(embed_dim=384)
        Settings.llm = None
        docs = [
            Document(
                text=chunk["text"],
                metadata={key: value for key, value in chunk["metadata"].items() if isinstance(value, (str, int, float, bool))},
                doc_id=chunk["id"],
            )
            for chunk in chunks
        ]
        storage_context = StorageContext.from_defaults()
        index = VectorStoreIndex.from_documents(docs, storage_context=storage_context, show_progress=False)
        index.storage_context.persist(persist_dir=str(persist_path))
    except Exception:
        # The deterministic chunks.jsonl retrieval path remains authoritative in
        # constrained deployments where LlamaIndex persistence is unavailable.
        return


def _elasticsearch_path(persist_path: Path) -> Path:
    return persist_path / "elasticsearch"


def _coerce_embedding_vector(vector: list[float]) -> list[float]:
    values = [float(value) for value in vector]
    if not values:
        raise ValueError("embedding vector must not be empty")
    return values


def _embedding_context(
    *,
    embedding_vector_fn: EmbeddingVectorFn | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if embedding_vector_fn is None:
        return {
            "vector_fn": None,
            "provider": ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
            "model": ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
            "dims": ELASTICSEARCH_DENSE_VECTOR_DIMS,
            "production_ready": False,
        }
    provider = str(embedding_provider or "configured").strip()
    model = str(embedding_model or "configured").strip()
    sample_text = str((chunks or [{}])[0].get("text") or "embedding dimension probe")
    try:
        sample_vector = _coerce_embedding_vector(embedding_vector_fn(sample_text))
    except Exception as exc:
        return {
            "vector_fn": None,
            "provider": provider,
            "model": model,
            "dims": ELASTICSEARCH_DENSE_VECTOR_DIMS,
            "production_ready": False,
            "transport": getattr(embedding_vector_fn, "image_agent_embedding_transport", None),
            "endpoint_configured": getattr(embedding_vector_fn, "image_agent_embedding_endpoint_configured", None),
            "embedding_error": _redact_elasticsearch_status_error(f"{type(exc).__name__}: {exc}"),
        }
    local_provider = provider.lower() in {
        "",
        ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
        "deterministic_local_hashing",
        "mock",
        "mock_embedding",
    }
    return {
        "vector_fn": embedding_vector_fn,
        "provider": provider,
        "model": model,
        "dims": len(sample_vector),
        "production_ready": not local_provider,
        "transport": getattr(embedding_vector_fn, "image_agent_embedding_transport", None),
        "endpoint_configured": getattr(embedding_vector_fn, "image_agent_embedding_endpoint_configured", None),
    }


def _embedding_vector(text: str, embedding_context: dict[str, Any]) -> list[float]:
    vector_fn = embedding_context.get("vector_fn")
    if callable(vector_fn):
        return _coerce_embedding_vector(vector_fn(text))
    return _dense_vector(text)


def _embedding_response_vector(response: Any) -> list[float]:
    data = getattr(response, "data", None)
    if data is None and isinstance(response, dict):
        data = response.get("data")
    first = data[0] if data else None
    embedding = getattr(first, "embedding", None)
    if embedding is None and isinstance(first, dict):
        embedding = first.get("embedding")
    return _coerce_embedding_vector(list(embedding or []))


def _openai_compatible_embeddings_endpoint(base_url: str) -> str:
    normalized = (base_url or "https://api.openai.com/v1").strip().rstrip("/")
    if normalized.endswith("/embeddings"):
        return normalized
    return f"{normalized}/embeddings"


def _openai_compatible_http_embedding_provider(
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: int,
) -> EmbeddingVectorFn:
    endpoint = _openai_compatible_embeddings_endpoint(base_url)

    def embed(text: str) -> list[float]:
        payload = json.dumps({"model": model, "input": text}).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        return _embedding_response_vector(body)

    return embed


def _configured_embedding_provider() -> tuple[EmbeddingVectorFn, str, str] | None:
    provider = os.environ.get(RAG_EMBEDDING_PROVIDER_ENV, "").strip().lower()
    if provider not in {"openai", "openai_compatible", "external_model_gateway", "krill", "custom"}:
        return None
    api_key = _env_first([RAG_EMBEDDING_API_KEY_ENV, "IMAGE_AGENT_MODEL_API_KEY", "OPENAI_API_KEY", "external_model_gateway_API_KEY", "KRILL_API_KEY"])
    if not api_key:
        return None
    base_url = _env_first([RAG_EMBEDDING_BASE_URL_ENV, "IMAGE_AGENT_MODEL_BASE_URL", "OPENAI_BASE_URL", "external_model_gateway_BASE_URL", "KRILL_BASE_URL"])
    model = _env_first([RAG_EMBEDDING_MODEL_ENV, "OPENAI_EMBEDDING_MODEL"], "text-embedding-3-small")
    timeout = int(os.environ.get(RAG_EMBEDDING_TIMEOUT_ENV, os.environ.get("OPENAI_TIMEOUT_SECONDS", "120")))
    try:
        from openai import OpenAI
    except Exception:
        OpenAI = None

    normalized_provider = "openai" if provider in {"openai", "openai_compatible", "custom"} else provider
    endpoint_configured = bool(base_url)
    if OpenAI is None:
        embed = _openai_compatible_http_embedding_provider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
        setattr(embed, "image_agent_embedding_transport", "openai_compatible_http")
        setattr(embed, "image_agent_embedding_endpoint_configured", endpoint_configured)
        return embed, normalized_provider, model

    try:
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": timeout,
            "http_client": httpx.Client(trust_env=False, timeout=timeout),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
    except Exception:
        embed = _openai_compatible_http_embedding_provider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
        )
        setattr(embed, "image_agent_embedding_transport", "openai_compatible_http")
        setattr(embed, "image_agent_embedding_endpoint_configured", endpoint_configured)
        return embed, normalized_provider, model

    def embed(text: str) -> list[float]:
        response = client.embeddings.create(model=model, input=text)
        return _embedding_response_vector(response)

    setattr(embed, "image_agent_embedding_transport", "sdk")
    setattr(embed, "image_agent_embedding_endpoint_configured", endpoint_configured)
    return embed, normalized_provider, model


def _dense_vector(text: str) -> list[float]:
    vector = [0.0] * ELASTICSEARCH_DENSE_VECTOR_DIMS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % ELASTICSEARCH_DENSE_VECTOR_DIMS
        sign = -1.0 if digest[4] % 2 else 1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _elasticsearch_mapping(embedding_context: dict[str, Any] | None = None) -> dict[str, Any]:
    dims = int((embedding_context or {}).get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS)
    return {
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "title": {"type": "text"},
                "text": {"type": "text"},
                "source_type": {"type": "keyword"},
                "workflow_type": {"type": "keyword"},
                "skill": {"type": "keyword"},
                "priority_score": {"type": "float"},
                ELASTICSEARCH_DENSE_VECTOR_FIELD: {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
    }


def _elasticsearch_hybrid_query_template() -> dict[str, Any]:
    return {
        "retriever": {
            "rrf": {
                "retrievers": [
                    {
                        "standard": {
                            "query": {
                                "multi_match": {
                                    "query": "{{query}}",
                                    "fields": ["title^2", "text", "source"],
                                }
                            }
                        }
                    },
                    {
                        "knn": {
                            "field": ELASTICSEARCH_DENSE_VECTOR_FIELD,
                            "query_vector": "{{query_vector}}",
                            "k": "{{k}}",
                            "num_candidates": "{{num_candidates}}",
                        }
                    },
                ],
                "rank_window_size": "{{rank_window_size}}",
                "rank_constant": 60,
            }
        },
        "size": "{{size}}",
        "_source": ["chunk_id", "source", "title", "text", "source_type", "workflow_type", "skill", "priority_score"],
    }


def _elasticsearch_filter_clauses(filters: dict[str, Any]) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for key, value in filters.items():
        clauses.append({"term": {key: value}})
    return clauses


def _elasticsearch_hybrid_query(
    query: str,
    *,
    filters: dict[str, Any],
    limit: int,
    embedding_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = embedding_context or _embedding_context()
    filter_clauses = _elasticsearch_filter_clauses(filters)
    return {
        "retriever": {
            "rrf": {
                "retrievers": [
                    {
                        "standard": {
                            "query": {
                                "bool": {
                                    "must": [
                                        {
                                            "multi_match": {
                                                "query": query,
                                                "fields": ["title^2", "text", "source"],
                                            }
                                        }
                                    ],
                                    "filter": filter_clauses,
                                }
                            }
                        }
                    },
                    {
                        "knn": {
                            "field": ELASTICSEARCH_DENSE_VECTOR_FIELD,
                            "query_vector": _embedding_vector(query, context),
                            "k": max(limit, 1),
                            "num_candidates": max(limit * 8, 20),
                            "filter": filter_clauses,
                        }
                    },
                ],
                "rank_window_size": max(limit * 4, 10),
                "rank_constant": 60,
            }
        },
        "size": limit,
        "_source": ["chunk_id", "source", "title", "text", "source_type", "workflow_type", "skill", "priority_score", "metadata"],
    }


def _elasticsearch_query_plus_knn_query(
    query: str,
    *,
    filters: dict[str, Any],
    limit: int,
    embedding_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = embedding_context or _embedding_context()
    filter_clauses = _elasticsearch_filter_clauses(filters)
    lexical_query: dict[str, Any] = {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^2", "text", "source"],
                    }
                }
            ],
            "filter": filter_clauses,
        }
    }
    return {
        "query": lexical_query,
        "knn": {
            "field": ELASTICSEARCH_DENSE_VECTOR_FIELD,
            "query_vector": _embedding_vector(query, context),
            "k": max(limit, 1),
            "num_candidates": max(limit * 8, 20),
            **({"filter": filter_clauses} if filter_clauses else {}),
        },
        "size": limit,
        "_source": ["chunk_id", "source", "title", "text", "source_type", "workflow_type", "skill", "priority_score", "metadata"],
    }


def _is_rrf_license_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "reciprocal rank fusion" in text and ("license" in text or "non-compliant" in text)


def _persist_elasticsearch_hybrid_contract(
    chunks: list[dict[str, Any]],
    persist_path: Path,
    *,
    embedding_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = embedding_context or _embedding_context(chunks=chunks)
    es_path = _elasticsearch_path(persist_path)
    es_path.mkdir(parents=True, exist_ok=True)
    (es_path / "mapping.json").write_text(json.dumps(_elasticsearch_mapping(context), indent=2), encoding="utf-8")
    (es_path / "hybrid-query-template.json").write_text(
        json.dumps(_elasticsearch_hybrid_query_template(), indent=2),
        encoding="utf-8",
    )
    lines: list[str] = []
    for operation in _elasticsearch_bulk_operations(chunks, embedding_context=context):
        lines.append(json.dumps(operation, ensure_ascii=False))
    (es_path / "bulk.ndjson").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return {
        "contract_persisted": True,
        "contract_path": "elasticsearch",
        "document_count": len(chunks),
        "dense_vector_dims": int(context.get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
        "embedding_provider": context.get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
        "embedding_model": context.get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
        "embedding_production_ready": context.get("production_ready") is True,
        **({"embedding_transport": context["transport"]} if context.get("transport") else {}),
        **(
            {"embedding_endpoint_configured": context["endpoint_configured"]}
            if context.get("endpoint_configured") is not None
            else {}
        ),
        **({"embedding_error": context["embedding_error"]} if context.get("embedding_error") else {}),
    }


def _configured_elasticsearch_client() -> Any | None:
    url = os.environ.get(ELASTICSEARCH_URL_ENV, "").strip()
    if not url:
        return None
    try:
        from elasticsearch import Elasticsearch
    except Exception:
        return None
    api_key = os.environ.get(ELASTICSEARCH_API_KEY_ENV, "").strip()
    if api_key:
        return Elasticsearch(url, api_key=api_key)
    return Elasticsearch(url)


def _elasticsearch_document(chunk: dict[str, Any], *, embedding_context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = embedding_context or _embedding_context()
    metadata = chunk.get("metadata") or {}
    return {
        "chunk_id": chunk.get("id"),
        "source": chunk.get("source"),
        "title": chunk.get("title"),
        "text": chunk.get("text"),
        "source_type": metadata.get("source_type"),
        "workflow_type": metadata.get("workflow_type"),
        "skill": metadata.get("skill"),
        "priority_score": metadata.get("priority_score"),
        "metadata": metadata,
        ELASTICSEARCH_DENSE_VECTOR_FIELD: _embedding_vector(str(chunk.get("text") or ""), context),
    }


def _elasticsearch_bulk_operations(
    chunks: list[dict[str, Any]],
    *,
    index_name: str = ELASTICSEARCH_INDEX_NAME,
    embedding_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    context = embedding_context or _embedding_context(chunks=chunks)
    operations: list[dict[str, Any]] = []
    for chunk in chunks:
        operations.append({"index": {"_index": index_name, "_id": chunk.get("id")}})
        operations.append(_elasticsearch_document(chunk, embedding_context=context))
    return operations


def _elasticsearch_response_body(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    body = getattr(response, "body", None)
    if isinstance(body, dict):
        return body
    raw = getattr(response, "raw", None)
    if isinstance(raw, dict):
        return raw
    return {}


def _persist_elasticsearch_hybrid_index(
    chunks: list[dict[str, Any]],
    *,
    elasticsearch_client: Any | None = None,
    index_name: str = ELASTICSEARCH_INDEX_NAME,
    embedding_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = embedding_context or _embedding_context(chunks=chunks)
    configured = elasticsearch_client is not None or bool(os.environ.get(ELASTICSEARCH_URL_ENV, "").strip())
    if context.get("embedding_error"):
        return {
            "configured": configured,
            "persisted": False,
            "mode": "embedding_error",
            "indexed_chunk_count": 0,
            "error": context["embedding_error"],
            "dense_vector_dims": int(context.get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
            "embedding_provider": context.get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
            "embedding_model": context.get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
            "embedding_production_ready": False,
            "embedding_error": context["embedding_error"],
        }
    if configured and context.get("production_ready") is not True:
        return {
            "configured": configured,
            "persisted": False,
            "mode": "embedding_required",
            "indexed_chunk_count": 0,
            "dense_vector_dims": int(context.get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
            "embedding_provider": context.get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
            "embedding_model": context.get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
            "embedding_production_ready": False,
        }
    client = elasticsearch_client if elasticsearch_client is not None else _configured_elasticsearch_client()
    if client is None:
        return {
            "configured": configured,
            "persisted": False,
            "mode": "client_unavailable" if configured else "local_contract",
            "indexed_chunk_count": 0,
            "dense_vector_dims": int(context.get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
            "embedding_provider": context.get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
            "embedding_model": context.get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
            "embedding_production_ready": context.get("production_ready") is True,
        }
    try:
        exists = bool(client.indices.exists(index=index_name))
        if exists:
            client.indices.delete(index=index_name)
        mapping = _elasticsearch_mapping(context)
        try:
            client.indices.create(index=index_name, body=mapping)
        except TypeError:
            client.indices.create(index=index_name, mappings=mapping["mappings"])
        operations = _elasticsearch_bulk_operations(chunks, index_name=index_name, embedding_context=context)
        try:
            response = client.bulk(operations=operations, refresh="wait_for")
        except TypeError:
            response = client.bulk(body=operations, refresh="wait_for")
        response_body = _elasticsearch_response_body(response)
        persisted = response_body.get("errors") is not True
        return {
            "configured": True,
            "persisted": persisted,
            "mode": "connected" if persisted else "bulk_errors",
            "indexed_chunk_count": len(chunks) if persisted else 0,
            "index": index_name,
            "dense_vector_dims": int(context.get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
            "embedding_provider": context.get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
            "embedding_model": context.get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
            "embedding_transport": context.get("transport"),
            "embedding_endpoint_configured": context.get("endpoint_configured"),
            "embedding_production_ready": context.get("production_ready") is True,
        }
    except Exception as exc:
        return {
            "configured": True,
            "persisted": False,
            "mode": "connection_error",
            "indexed_chunk_count": 0,
            "error": _redact_elasticsearch_status_error(f"{type(exc).__name__}: {exc}"),
            "dense_vector_dims": int(context.get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
            "embedding_provider": context.get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
            "embedding_model": context.get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
            "embedding_transport": context.get("transport"),
            "embedding_endpoint_configured": context.get("endpoint_configured"),
            "embedding_production_ready": context.get("production_ready") is True,
        }


def _redact_elasticsearch_status_error(text: str) -> str:
    redacted = str(text or "")
    for name in (
        ELASTICSEARCH_URL_ENV,
        ELASTICSEARCH_API_KEY_ENV,
        RAG_EMBEDDING_API_KEY_ENV,
        RAG_EMBEDDING_BASE_URL_ENV,
        "IMAGE_AGENT_MODEL_API_KEY",
        "IMAGE_AGENT_MODEL_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "external_model_gateway_API_KEY",
        "external_model_gateway_BASE_URL",
        "KRILL_API_KEY",
        "KRILL_BASE_URL",
    ):
        value = os.environ.get(name, "")
        if value:
            redacted = redacted.replace(value, "[redacted-secret]")
    redacted = re.sub(r"https://[^/\s:@]+:[^@\s/]+@", "https://[redacted-secret]@", redacted)
    redacted = re.sub(r"(?i)\bAuthorization\s*:\s*(?:ApiKey|Bearer|Basic)\s+[^\s,\"']+", "[redacted-secret]", redacted)
    redacted = re.sub(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9._-]+", "[redacted-secret]", redacted)
    return redacted


def _elasticsearch_hybrid_metadata(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "engine": "elasticsearch",
        "index": str(status.get("index") or _elasticsearch_index_name()),
        "lexical_retriever": "standard",
        "vector_retriever": "knn",
        "dense_vector_field": ELASTICSEARCH_DENSE_VECTOR_FIELD,
        "dense_vector_dims": int(status.get("dense_vector_dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
        "embedding_provider": status.get("embedding_provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
        "embedding_model": status.get("embedding_model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
        "embedding_production_ready": status.get("embedding_production_ready") is True,
        **({"embedding_transport": status["embedding_transport"]} if status.get("embedding_transport") else {}),
        **(
            {"embedding_endpoint_configured": status["embedding_endpoint_configured"]}
            if status.get("embedding_endpoint_configured") is not None
            else {}
        ),
        "fusion": "rrf",
        "contract_persisted": status.get("contract_persisted") is True,
        "persisted": status.get("persisted") is True,
        "mode": status.get("mode") or "local_contract",
        "configured": status.get("configured") is True,
        "indexed_chunk_count": int(status.get("indexed_chunk_count") or 0),
        **({"error": status["error"]} if status.get("error") else {}),
        **({"embedding_error": status["embedding_error"]} if status.get("embedding_error") else {}),
        "official_sources": ELASTICSEARCH_OFFICIAL_SOURCES,
        "boundary": "Elasticsearch ranks curated local RAG chunks only; backend workflow registry, task rows, result-summary, and artifact manifests remain authoritative for current project state.",
    }


def _load_chunks(persist_path: Path) -> list[dict[str, Any]]:
    chunks_path = persist_path / "chunks.jsonl"
    if not chunks_path.exists():
        return []
    chunks = []
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        chunks.append(json.loads(line))
    return chunks


def _retrieve_from_elasticsearch_hybrid(
    query: str,
    *,
    filters: dict[str, Any],
    limit: int,
    elasticsearch_client: Any | None,
    embedding_context: dict[str, Any] | None = None,
    allowed_sources: set[str] | None = None,
    index_name: str = ELASTICSEARCH_INDEX_NAME,
) -> dict[str, Any] | None:
    client = elasticsearch_client if elasticsearch_client is not None else _configured_elasticsearch_client()
    if client is None:
        return None
    fusion = "rrf"
    rrf_unavailable_reason: str | None = None
    try:
        body = _elasticsearch_hybrid_query(query, filters=filters, limit=limit, embedding_context=embedding_context)
        response = client.search(index=index_name, body=body)
    except Exception as exc:
        if not _is_rrf_license_error(exc):
            return None
        fusion = "query_plus_knn"
        rrf_unavailable_reason = "license_non_compliant"
        try:
            body = _elasticsearch_query_plus_knn_query(
                query,
                filters=filters,
                limit=limit,
                embedding_context=embedding_context,
            )
            response = client.search(index=index_name, body=body)
        except Exception:
            return None
    response_body = _elasticsearch_response_body(response)
    hits = ((response_body or {}).get("hits") or {}).get("hits") or []
    results = []
    for hit in hits:
        source = hit.get("_source") or {}
        source_path = source.get("source")
        if not _is_safe_indexed_source(source_path):
            continue
        if allowed_sources is not None and source_path not in allowed_sources:
            continue
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        if not metadata:
            metadata = {
                key: source.get(key)
                for key in ("source_type", "workflow_type", "skill", "priority_score")
                if source.get(key) is not None
            }
        results.append(
            {
                "source": source_path,
                "title": source.get("title"),
                "snippet": str(source.get("text") or "")[:360].replace("\n", " ").strip(),
                "score": float(hit.get("_score") or 0.0),
                "metadata": metadata,
            }
        )
    if not results:
        return None
    query_evidence = {
        "index": index_name,
        "lexical_retriever": "standard",
        "vector_retriever": "knn",
        "dense_vector_field": ELASTICSEARCH_DENSE_VECTOR_FIELD,
        "fusion": fusion,
        **({"rrf_unavailable_reason": rrf_unavailable_reason} if rrf_unavailable_reason else {}),
        "dense_vector_dims": int((embedding_context or {}).get("dims") or ELASTICSEARCH_DENSE_VECTOR_DIMS),
        "embedding_provider": (embedding_context or {}).get("provider") or ELASTICSEARCH_LOCAL_EMBEDDING_PROVIDER,
        "embedding_model": (embedding_context or {}).get("model") or ELASTICSEARCH_LOCAL_EMBEDDING_MODEL,
        "embedding_transport": (embedding_context or {}).get("transport"),
        "embedding_endpoint_configured": (embedding_context or {}).get("endpoint_configured"),
        "embedding_production_ready": (embedding_context or {}).get("production_ready") is True,
    }
    return {
        "query": query,
        "results": results[:limit],
        "tool": "retrieve_reference_context",
        "mode": "elasticsearch_hybrid",
        "elasticsearch_hybrid_query": query_evidence,
    }


def _embedding_context_matches_manifest(context: dict[str, Any], hybrid_search: dict[str, Any]) -> bool:
    expected_provider = str(hybrid_search.get("embedding_provider") or "").strip()
    expected_model = str(hybrid_search.get("embedding_model") or "").strip()
    actual_provider = str(context.get("provider") or "").strip()
    actual_model = str(context.get("model") or "").strip()
    if expected_provider and actual_provider != expected_provider:
        return False
    if expected_model and actual_model != expected_model:
        return False
    try:
        expected_dims = int(hybrid_search.get("dense_vector_dims") or 0)
        actual_dims = int(context.get("dims") or 0)
    except (TypeError, ValueError):
        return False
    return expected_dims > 0 and actual_dims == expected_dims


def _passes_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        current = metadata.get(key)
        if isinstance(current, list):
            if str(value) not in {str(item) for item in current}:
                return False
            continue
        if str(current) != str(value):
            return False
    return True


def _score(query_terms: list[str], chunk: dict[str, Any]) -> float:
    if not query_terms:
        return 0.0
    doc_terms = chunk.get("tokens") or _tokens(chunk.get("text", ""))
    overlap = len(set(query_terms) & set(doc_terms))
    priority = float((chunk.get("metadata") or {}).get("priority_score") or 0) / 100.0
    length_penalty = math.log(max(len(doc_terms), 3), 10) / 10.0
    return overlap + priority - length_penalty


def retrieve_from_local_rag_index(
    query: str,
    *,
    root: Path | str,
    persist_dir: Path | str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int = 5,
    elasticsearch_client: Any | None = None,
    embedding_vector_fn: EmbeddingVectorFn | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    persist_path = Path(persist_dir or root_path / ".rag_index")
    chunks = _load_chunks(persist_path)
    if not chunks:
        return {"query": query, "results": [], "tool": "retrieve_reference_context", "mode": "local_persistent_index"}
    filters = filters or {}
    manifest_path = persist_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    hybrid_search = manifest.get("hybrid_search") if isinstance(manifest.get("hybrid_search"), dict) else {}
    manifest_sources = {
        chunk.get("source")
        for chunk in chunks
        if isinstance(chunk, dict) and _is_safe_indexed_source(chunk.get("source"))
    }
    if manifest.get("engine") == "elasticsearch_hybrid" and hybrid_search.get("persisted") is True:
        if embedding_vector_fn is None:
            configured_embedding = _configured_embedding_provider()
            if configured_embedding is not None:
                embedding_vector_fn, embedding_provider, embedding_model = configured_embedding
        embedding_context = _embedding_context(
            embedding_vector_fn=embedding_vector_fn,
            embedding_provider=embedding_provider or hybrid_search.get("embedding_provider"),
            embedding_model=embedding_model or hybrid_search.get("embedding_model"),
            chunks=[{"text": query}],
        )
        if embedding_context.get("production_ready") is True and not embedding_context.get("embedding_error"):
            if _embedding_context_matches_manifest(embedding_context, hybrid_search):
                elasticsearch_result = _retrieve_from_elasticsearch_hybrid(
                    query,
                    filters=filters,
                    limit=limit,
                    elasticsearch_client=elasticsearch_client,
                    embedding_context=embedding_context,
                    allowed_sources=manifest_sources or None,
                    index_name=str(hybrid_search.get("index") or ELASTICSEARCH_INDEX_NAME),
                )
                if elasticsearch_result is not None:
                    return elasticsearch_result
    query_terms = _tokens(query)
    results = []
    for chunk in chunks:
        if not _is_safe_indexed_source(chunk.get("source")):
            continue
        metadata = chunk.get("metadata") or {}
        if not _passes_filters(metadata, filters):
            continue
        score = _score(query_terms, chunk)
        if score <= 0:
            continue
        results.append(
            {
                "source": chunk["source"],
                "title": chunk["title"],
                "snippet": chunk["text"][:360].replace("\n", " ").strip(),
                "score": float(score),
                "metadata": metadata,
            }
        )
    results.sort(key=lambda item: (-item["score"], item["source"]))
    if manifest.get("engine") == "elasticsearch_hybrid":
        mode = "elasticsearch_hybrid_fallback"
    elif manifest.get("engine") == "llama_index":
        mode = "llama_index"
    else:
        mode = "local_persistent_index"
    return {"query": query, "results": results[:limit], "tool": "retrieve_reference_context", "mode": mode}

