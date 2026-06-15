from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.model_gateway import provider_status as model_provider_status
from app.agent.rag_index import (
    build_local_rag_index,
    local_rag_index_status,
    rag_vendor_coverage_catalog,
    rag_vendor_pointer_integrity,
    vendor_raw_source_status,
)
from app.agent.rag_orchestration import dependency_status, grounding_policy


def public_model_status() -> dict[str, Any]:
    status = model_provider_status()
    safe: dict[str, Any] = {
        key: value
        for key, value in status.items()
        if key
        in {
            "provider",
            "configured",
            "base_url",
            "model",
            "review_model",
            "wire_api",
            "reasoning_effort",
            "store",
            "metadata_enabled",
            "context_window",
            "auto_compact_token_limit",
        }
    }
    deployment = status.get("deployment") if isinstance(status.get("deployment"), dict) else {}
    safe_deployment = {
        key: deployment[key]
        for key in ("backend_runtime_mode", "model_gateway_access")
        if key in deployment
    }
    if safe_deployment:
        safe["deployment"] = safe_deployment
    return safe


def rag_status(root: Path) -> dict[str, Any]:
    index_status = local_rag_index_status(root=root, persist_dir=root / ".rag_index")
    indexed_sources = index_status.get("indexed_sources") or []
    return {
        "dependencies": dependency_status(),
        "grounding_policy": grounding_policy(),
        "index": index_status,
        "vendor_raw_sources": vendor_raw_source_status(
            root=root,
            indexed_sources=indexed_sources,
        ),
        "vendor_pointer_integrity": rag_vendor_pointer_integrity(root=root),
        "vendor_coverage_catalog": rag_vendor_coverage_catalog(
            root=root,
            indexed_sources=indexed_sources,
        ),
    }


def rebuild_rag_index(root: Path) -> dict[str, Any]:
    return build_local_rag_index(root=root, persist_dir=root / ".rag_index")
