from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


INDEX_GLOBS = ("docs/rag/**/*.md", "docs/skills/**/SKILL.md", "docs/skills/**/references/*.md")
VENDOR_RAW_SOURCES_MANIFEST = "docs/rag/vendor/raw-sources/manifest.json"
VENDOR_RAW_SOURCES_PREFIX = "docs/rag/vendor/raw-sources/"
RAG_POINTER_GLOBS = ("docs/rag/workflows/**/*.md", "docs/rag/contracts/**/*.md")
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 160


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


def build_local_rag_index(*, root: Path | str, persist_dir: Path | str | None = None) -> dict[str, Any]:
    root_path = Path(root)
    persist_path = Path(persist_dir or root_path / ".rag_index")
    persist_path.mkdir(parents=True, exist_ok=True)
    documents = _collect_documents(root_path)
    chunks = _build_chunks(root_path, documents)
    _persist_llama_index(chunks, persist_path)
    manifest = {
        "engine": "llama_index" if _llama_index_available() else "local_manifest",
        "semantic_index": True,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "documents": documents,
        "note": "Persistent local RAG index for docs/rag and docs/skills. Uses LlamaIndex when available and local chunk retrieval as deterministic fallback.",
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
) -> dict[str, Any]:
    root_path = Path(root)
    persist_path = Path(persist_dir or root_path / ".rag_index")
    chunks = _load_chunks(persist_path)
    if not chunks:
        return {"query": query, "results": [], "tool": "retrieve_reference_context", "mode": "local_persistent_index"}
    filters = filters or {}
    query_terms = _tokens(query)
    results = []
    for chunk in chunks:
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
    manifest_path = persist_path / "manifest.json"
    mode = "llama_index" if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")).get("engine") == "llama_index" else "local_persistent_index"
    return {"query": query, "results": results[:limit], "tool": "retrieve_reference_context", "mode": mode}
