import importlib.util
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

import pytest


def _load_smoke_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_remote_agent.py"
    spec = importlib.util.spec_from_file_location("smoke_remote_agent", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_verifier_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_remote_smoke_acceptance.py"
    spec = importlib.util.spec_from_file_location("verify_remote_smoke_acceptance", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _good_remote_smoke_response(url: str):
    if url.endswith("/health"):
        return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
    if url.endswith("/agent/model/status"):
        return {"configured": False, "provider": "OpenAI"}
    if url.endswith("/agent/rag/status"):
        return {"index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"}}
    if url.endswith("/agent/rag/rebuild"):
        return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
    return None


def test_smoke_remote_agent_runtime_toolchain_help_points_to_runtime_probe(capsys):
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit):
        smoke.main(["--help"])

    help_text = capsys.readouterr().out
    assert "--require-runtime-toolchain" in help_text
    assert "/runtime/probe" in help_text
    assert "/runtime/containers" not in help_text


def _elasticsearch_hybrid_search(**overrides):
    payload = {
        "engine": "elasticsearch",
        "configured": True,
        "persisted": True,
        "mode": "connected",
        "index": "image_agent_rag",
        "indexed_chunk_count": 260,
        "lexical_retriever": "standard",
        "vector_retriever": "knn",
        "dense_vector_field": "embedding",
        "dense_vector_dims": 1536,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_transport": "openai_compatible_http",
        "embedding_endpoint_configured": True,
        "embedding_production_ready": True,
        "fusion": "rrf",
        "official_sources": [
            "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
        ],
    }
    payload.update(overrides)
    return payload


def _ready_fast_launch_readiness(**hybrid_overrides):
    hybrid = _elasticsearch_hybrid_search(**hybrid_overrides)
    return {
        "blocking_reasons": [],
        "ready": True,
        "status": "ready",
        "checks": {
            "model_gateway_target": {"status": "passed"},
            "production_deployment": {
                "status": "passed",
                "required": True,
                "ready": True,
                "readiness_status": "ready",
                "blocking_reasons": [],
            },
            "agent_task_boundary": {"status": "passed"},
            "upload_workflow_result_contract": {"status": "passed"},
            "strict_remote_acceptance": {"status": "passed"},
            "rag_elasticsearch_hybrid": {
                "status": "passed",
                "engine": hybrid["engine"],
                "configured": hybrid["configured"],
                "persisted": hybrid["persisted"],
                "mode": hybrid["mode"],
                "index": hybrid["index"],
                "indexed_chunk_count": hybrid["indexed_chunk_count"],
                "dense_vector_dims": hybrid["dense_vector_dims"],
                "embedding_provider": hybrid["embedding_provider"],
                "embedding_model": hybrid["embedding_model"],
                "embedding_transport": hybrid["embedding_transport"],
                "embedding_endpoint_configured": hybrid["embedding_endpoint_configured"],
                "embedding_production_ready": hybrid["embedding_production_ready"],
                "fusion": hybrid["fusion"],
            },
        },
    }


def _pre_acceptance_fast_launch_readiness(**hybrid_overrides):
    readiness = _ready_fast_launch_readiness(**hybrid_overrides)
    readiness["ready"] = False
    readiness["status"] = "blocked"
    readiness["blocking_reasons"] = [
        "Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain."
    ]
    readiness["checks"]["strict_remote_acceptance"] = {"status": "missing"}
    return readiness


def _runtime_toolchain_response(**overrides):
    payload = {
        "docker_requires_sudo": True,
        "fs_license_path": "C:/Users/A/private/license.txt",
        "fs_license_exists": True,
        "qsirecon_profile": "dki",
        "qsirecon_recon_spec": "dipy_dki",
        "workflows": {
            "t1_deepprep": {
                "image": "pbfslab/deepprep:25.1.0",
                "available": True,
                "detail_tail": "docker inspect /var/run/docker.sock private detail",
            },
            "dwi_fast_gpu_dti": {
                "image": "pennlinc/qsiprep:26.0.0",
                "available": True,
                "detail_tail": "nvidia-smi ok with secret-ish host path C:/Users/A/private",
            },
        },
    }
    payload.update(overrides)
    return payload


def _good_workflow_eligibility(workflow_type="t1_deepprep_anat_report"):
    workflow_metadata = _workflow_metadata(workflow_type)
    return {
        "policy_version": "workflow_eligibility_v1",
        "production_task_created": False,
        "primary_recommendation": {
            "workflow_type": workflow_type,
            "workflow_metadata": workflow_metadata,
        },
        "runnable_workflows": [
            {
                "workflow_type": workflow_type,
                "workflow_metadata": workflow_metadata,
            }
        ],
        "blocked_workflows": [],
    }


def _complete_vendor_raw_sources(**overrides):
    payload = {
        "manifest_exists": True,
        "manifest_schema_version": 1,
        "source_count": 2,
        "vendor_doc_count": 2,
        "missing_files": [],
        "hash_mismatches": [],
        "raw_sources_indexed": False,
        "indexed_raw_sources": [],
        "curated_provenance_ok": True,
        "curated_provenance_issues": [],
        "curated_sources": [
            {
                "vendor_doc": "fmriprep_official_outputs.md",
                "raw_source_ids": ["fmriprep_outputs"],
                "source_urls": ["https://fmriprep.org/en/stable/outputs.html"],
                "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_outputs.html"],
                "source_types": ["official_docs"],
                "manifest_backed": True,
                "source_url_backed": True,
                "complete": True,
            },
            {
                "vendor_doc": "xcp_d_official_outputs.md",
                "raw_source_ids": ["xcp_d_outputs"],
                "source_urls": ["https://xcp-d.readthedocs.io/en/latest/outputs.html"],
                "raw_files": ["docs/rag/vendor/raw-sources/xcp_d_outputs.html"],
                "source_types": ["official_docs"],
                "manifest_backed": True,
                "source_url_backed": True,
                "complete": True,
            },
        ],
    }
    payload.update(overrides)
    return payload


def _complete_vendor_pointer_integrity(**overrides):
    payload = {
        "ok": True,
        "pointer_count": 35,
        "issue_count": 0,
        "issues": [],
        "referenced_vendor_docs": [
            "fmriprep_official_outputs.md",
            "xcp_d_official_outputs.md",
        ],
        "pointers_by_doc": {
            "docs/rag/workflows/bold_fmriprep_xcpd.md": [
                "docs/rag/vendor/fmriprep_official_outputs.md"
            ],
            "docs/rag/contracts/container-qc-artifacts.md": [
                "docs/rag/vendor/xcp_d_official_outputs.md"
            ],
        },
        "raw_source_manifest_exists": True,
        "curated_provenance_ok": True,
    }
    payload.update(overrides)
    return payload


def _complete_vendor_coverage_catalog(**overrides):
    payload = {
        "status": "complete",
        "policy": "curated summaries are indexed; raw snapshots are provenance evidence only",
        "manifest_exists": True,
        "manifest_schema_version": 1,
        "generated_at": "2026-06-06T00:00:00Z",
        "vendor_doc_count": 2,
        "complete_vendor_doc_count": 2,
        "incomplete_vendor_doc_count": 0,
        "raw_source_count": 2,
        "raw_sources_indexed": False,
        "curated_provenance_ok": True,
        "pointer_integrity_ok": True,
        "pointer_count": 35,
        "issue_count": 0,
        "vendors": [
            {
                "vendor_doc": "fmriprep_official_outputs.md",
                "vendor_path": "docs/rag/vendor/fmriprep_official_outputs.md",
                "complete": True,
                "manifest_backed": True,
                "source_url_backed": True,
                "raw_source_count": 1,
                "source_url_count": 1,
                "source_types": ["official_docs"],
                "referenced_by": ["docs/rag/workflows/bold_fmriprep_xcpd.md"],
                "raw_source_ids": ["fmriprep_outputs"],
            },
            {
                "vendor_doc": "xcp_d_official_outputs.md",
                "vendor_path": "docs/rag/vendor/xcp_d_official_outputs.md",
                "complete": True,
                "manifest_backed": True,
                "source_url_backed": True,
                "raw_source_count": 1,
                "source_url_count": 1,
                "source_types": ["official_docs"],
                "referenced_by": ["docs/rag/contracts/container-qc-artifacts.md"],
                "raw_source_ids": ["xcp_d_outputs"],
            },
        ],
    }
    payload.update(overrides)
    return payload


def _scientific_report_artifact(
    relative_path: str,
    *,
    preview_kind: str,
    content_type: str,
    size_bytes: int = 32,
    provenance_override: dict | None = None,
):
    artifact = {
        "relative_path": relative_path,
        "download_url": f"/tasks/114/artifacts/{quote(relative_path)}",
        "preview_kind": preview_kind,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "exists": True,
        "source_stage": "scientific_report",
        "artifact_role": "derived_presentation_asset",
        "artifact_origin": "generated_from_result_summary",
        "native_artifact": False,
        "provenance": {"generated_from": "result_summary", "replaces_native_qc": False},
    }
    if provenance_override:
        artifact.update(provenance_override)
    return artifact


def _scientific_report_manifest(*, artifacts=None, result_summary_available=True):
    if artifacts is None:
        artifacts = [
            _scientific_report_artifact("reports/index.html", preview_kind="html", content_type="text/html"),
            _scientific_report_artifact("reports/report_manifest.json", preview_kind="json", content_type="application/json"),
            _scientific_report_artifact("reports/t1_qc.png", preview_kind="image", content_type="image/png"),
        ]
    return {
        "contract_version": "artifact_manifest_v1",
        "task_id": 114,
        "result_summary": {"available": result_summary_available},
        "artifacts": artifacts,
        "omitted_artifacts": [],
    }


def _artifact_manifest_with_result_summary_output(
    relative_path="reports/index.html",
    *,
    preview_kind="html",
    content_type="text/html",
):
    return {
        "contract_version": "artifact_manifest_v1",
        "task_id": 114,
        "workflow_type": "dwi_fast_gpu_dti",
        "modality": "DWI",
        "result_summary": {"available": True, "contract_version": "1.0"},
        "artifacts": [
            {
                "relative_path": relative_path,
                "download_url": f"/tasks/114/artifacts/{quote(relative_path)}",
                "preview_kind": preview_kind,
                "content_type": content_type,
                "size_bytes": 12,
                "exists": True,
            }
        ],
        "omitted_artifacts": [],
    }


_DEFAULT_WORKFLOW_METADATA = object()


def _workflow_metadata(workflow_type="dwi_fast_gpu_dti", runtime_workflow_type=None):
    runtime = runtime_workflow_type or ("t1_deepprep" if workflow_type == "t1_deepprep_anat_report" else workflow_type)
    return {
        "workflow_type": workflow_type,
        "runtime_workflow_type": runtime,
        "display_name": f"{workflow_type} processing, QC, and report",
        "workflow_family": workflow_type.split("_", 1)[0],
        "workflow_role": "complete_processing",
        "capability_summary": "Runs the selected workflow, QC, and report outputs.",
        "pipeline_stages": [
            {"name": "Input preparation", "purpose": "Prepare supported imaging input."},
            {"name": "Pipeline execution", "purpose": "Generate derivatives and QC outputs."},
        ],
        "primary_outputs": ["pipeline derivatives", "result-summary.json"],
        "qc_outputs": ["container-native QC artifacts"],
        "report_outputs": ["HTML scientific report"],
        "limitations": ["Requires supported input and configured containers"],
        "agent_selectable": True,
        "is_report_only": False,
    }


def _task_result_summary(
    *,
    task_id=114,
    workflow_type="dwi_fast_gpu_dti",
    modality="DWI",
    output_path="reports/index.html",
    output_content_type="text/html",
    outputs=None,
    workflow_metadata=_DEFAULT_WORKFLOW_METADATA,
):
    summary = {
        "contract_version": "1.0",
        "task_id": task_id,
        "workflow_type": workflow_type,
        "modality": modality,
        "spaces": ["native"],
        "feature_groups": ["dti_metrics"],
        "outputs": outputs
        if outputs is not None
        else {
            "dti_metrics": [
                {
                    "relative_path": output_path,
                    "download_url": f"/tasks/114/artifacts/{quote(output_path)}",
                    "content_type": output_content_type,
                }
            ]
        },
        "provenance": {"generated_from": "workflow"},
    }
    if workflow_metadata is _DEFAULT_WORKFLOW_METADATA:
        summary["workflow_metadata"] = _workflow_metadata(workflow_type)
    elif workflow_metadata is not None:
        summary["workflow_metadata"] = workflow_metadata
    return summary


def test_smoke_remote_agent_skips_model_run_when_gateway_unconfigured(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {"index": {"document_count": 55, "chunk_count": 182, "engine": "llama_index"}}
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 55, "chunk_count": 182, "semantic_index": True}
        if url.endswith("/agent/runs"):
            raise AssertionError("agent run should be skipped when model gateway is unconfigured")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["agent_run_status"] == "skipped"
    assert payload["model_smoke_status"] == "skipped_missing_model_config"
    assert payload["model_status"]["configured"] is False
    assert all(not call[1].endswith("/agent/runs") for call in calls)


def test_smoke_remote_agent_can_skip_generic_agent_run_while_requiring_model_status(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "rawchat",
                "provider_profile": "rawchat",
                "wire_api": "responses",
                "trust_env_proxy": False,
                "capabilities": {"model_tool_loop": True},
                "deployment": {"model_gateway_access": "direct"},
            }
        if url.endswith("/agent/rag/status"):
            return {"index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"}}
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs"):
            raise AssertionError("generic agent run should be skipped")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-model",
            "--expected-model-wire-api",
            "responses",
            "--expected-model-provider-profile",
            "rawchat",
            "--require-model-tool-loop",
            "--skip-agent-run-smoke",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["model_status"]["configured"] is True
    assert payload["model_smoke_status"] == "skipped_by_option"
    assert payload["agent_run_status"] == "skipped"
    assert payload["agent_model_gateway_status"] == "skipped"
    assert payload["smoke_gate"]["skip_agent_run_smoke"] is True
    assert all(not call[1].endswith("/agent/runs") for call in calls)


def test_smoke_remote_agent_preserves_safe_gateway_diagnostics(monkeypatch, capsys):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {
                "configured": False,
                "provider": "OpenAI",
                "gateway_diagnostics": {
                    "sdk_method": "responses.create",
                    "request_shape": "responses_input",
                    "structured_output": "responses_text_format",
                    "model_tool_loop": "enabled",
                    "workflow_task_creation": "server_side_resume_confirmation_only",
                    "authorization": "Bearer secret-value",
                    "unsafe": "https://user:pass@example.test",
                },
            }
        if url.endswith("/agent/rag/status"):
            return {"index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"}}
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": {
                    "engine": "elasticsearch",
                    "persisted": True,
                    "mode": "connected",
                    "indexed_chunk_count": 260,
                    "lexical_retriever": "standard",
                    "vector_retriever": "knn",
                    "dense_vector_field": "embedding",
                    "fusion": "rrf",
                    "official_sources": [
                        "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                    ],
                },
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["model_status"]["gateway_diagnostics"] == {
        "sdk_method": "responses.create",
        "request_shape": "responses_input",
        "structured_output": "responses_text_format",
        "model_tool_loop": "enabled",
        "workflow_task_creation": "server_side_resume_confirmation_only",
    }
    assert "secret-value" not in json.dumps(payload)
    assert "authorization" not in json.dumps(payload)


def test_smoke_remote_agent_model_status_omits_runtime_capacity_fields():
    smoke = _load_smoke_module()

    safe = smoke._safe_model_status(
        {
            "configured": True,
            "provider_profile": "rawchat",
            "model": "gpt-5.5",
            "wire_api": "responses",
            "context_window": 1000000,
            "auto_compact_token_limit": 900000,
            "capabilities": {"model_tool_loop": True},
        }
    )

    assert safe["configured"] is True
    assert safe["provider_profile"] == "rawchat"
    assert "context_window" not in safe
    assert "auto_compact_token_limit" not in safe


def test_smoke_remote_agent_checks_health_identity_before_smoke(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "wrong_app"}
        raise AssertionError(f"unexpected request after bad health identity: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local"])

    assert "health identity check failed" in str(exc.value)


def test_smoke_remote_agent_require_model_fails_when_gateway_unconfigured(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": {
                    "manifest_exists": True,
                    "missing_files": [],
                    "hash_mismatches": [],
                    "raw_sources_indexed": False,
                    "curated_sources": [{"vendor_doc": "fmriprep_official_container_usage.md", "complete": True}],
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-model"])

    assert "model gateway is not configured" in str(exc.value)


def test_smoke_remote_agent_require_production_readiness_fails_when_blocked(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/deployment"):
            return {
                "production_readiness": {
                    "blocking_reasons": ["Agent model gateway is not configured."],
                    "ready": False,
                    "required": True,
                    "status": "blocked",
                }
            }
        raise AssertionError(f"unexpected request after blocked readiness: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-production-readiness"])

    assert "production readiness is blocked: Agent model gateway is not configured." in str(exc.value)


def test_smoke_remote_agent_require_production_readiness_fails_when_ready_with_blockers(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/deployment"):
            return {
                "production_readiness": {
                    "blocking_reasons": ["Remote runtime mode is not enabled."],
                    "ready": True,
                    "required": True,
                    "status": "ready",
                }
            }
        raise AssertionError(f"unexpected request after blocked readiness: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-production-readiness"])

    assert "production readiness is blocked: Remote runtime mode is not enabled." in str(exc.value)


def test_smoke_remote_agent_records_production_readiness_when_required(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/deployment"):
            return {
                "production_readiness": {
                    "blocking_reasons": [],
                    "ready": True,
                    "required": True,
                    "status": "ready",
                },
                "fast_launch_readiness": _pre_acceptance_fast_launch_readiness(),
            }
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {"index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"}}
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--require-production-readiness"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_production_readiness"] is True
    assert payload["production_readiness_status"] == "passed"
    assert payload["production_readiness"] == {
        "blocking_reasons": [],
        "ready": True,
        "required": True,
        "status": "ready",
    }
    assert payload["fast_launch_readiness_status"] == "pre_acceptance"
    assert payload["fast_launch_readiness"]["checks"]["production_deployment"] == {
        "status": "passed",
        "required": True,
        "ready": True,
        "readiness_status": "ready",
        "blocking_reasons": [],
    }
    assert payload["fast_launch_readiness"]["checks"]["strict_remote_acceptance"]["status"] == "missing"
    assert payload["fast_launch_readiness"]["checks"]["rag_elasticsearch_hybrid"] == {
        "status": "passed",
        "engine": "elasticsearch",
        "configured": True,
        "persisted": True,
        "mode": "connected",
        "index": "image_agent_rag",
        "indexed_chunk_count": 260,
        "dense_vector_dims": 1536,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_transport": "openai_compatible_http",
        "embedding_endpoint_configured": True,
        "embedding_production_ready": True,
        "fusion": "rrf",
    }


def test_smoke_remote_agent_requires_deployment_id_for_identity_gate():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-deployment-identity"])

    assert "--require-deployment-identity requires --deployment-id" in str(exc.value)


def test_smoke_remote_agent_rejects_path_like_deployment_id():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-deployment-identity",
                "--deployment-id",
                "/home/yyf/project/image_agent_releases/codex-f57a2ea",
            ]
        )

    assert "--deployment-id must be a privacy-safe release id or commit" in str(exc.value)


@pytest.mark.parametrize(
    ("health_version", "expected_message"),
    [
        ("", "deployment identity health version is missing"),
        ("/home/yyf/project/image_agent_releases/codex-f57a2ea/apps/api", "deployment identity health version must be privacy-safe"),
    ],
)
def test_smoke_remote_agent_rejects_bad_health_version_for_deployment_identity(
    monkeypatch,
    health_version,
    expected_message,
):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": health_version}
        raise AssertionError(f"unexpected request after bad deployment identity: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-deployment-identity",
                "--deployment-id",
                "codex-f57a2ea-20260611T023456",
            ]
        )

    assert expected_message in str(exc.value)


def test_smoke_remote_agent_rejects_unexpected_health_version_for_deployment_identity(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "old-release"}
        raise AssertionError(f"unexpected request after bad deployment identity: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-deployment-identity",
                "--deployment-id",
                "codex-new-release",
                "--expected-health-version",
                "new-release",
            ]
        )

    assert "deployment identity health version must match --expected-health-version" in str(exc.value)


def test_smoke_remote_agent_enforces_rag_thresholds_and_raw_source_policy(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 55, "chunk_count": 180, "engine": "llama_index"},
                "vendor_raw_sources": {
                    "manifest_exists": True,
                    "missing_files": ["missing.html"],
                    "hash_mismatches": [],
                    "raw_sources_indexed": True,
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 55, "chunk_count": 180, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--min-documents",
                "60",
                "--min-chunks",
                "200",
                "--require-raw-source-policy",
            ]
        )

    assert "RAG document_count 55 below minimum 60" in str(exc.value)


def test_smoke_remote_agent_raw_source_policy_rejects_curated_provenance_issues(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": {
                    "manifest_exists": True,
                    "manifest_schema_version": 1,
                    "source_count": 21,
                    "vendor_doc_count": 21,
                    "missing_files": [],
                    "hash_mismatches": [],
                    "raw_sources_indexed": False,
                    "indexed_raw_sources": [],
                    "curated_provenance_ok": False,
                    "curated_provenance_issues": [
                        {
                            "vendor_doc": "templateflow_official_cache_archive_client.md",
                            "issue": "source_url_not_backed_by_raw_source_ids",
                        }
                    ],
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-raw-source-policy"])

    assert "RAG raw-source policy failed: curated provenance issues" in str(exc.value)


def test_smoke_remote_agent_raw_source_policy_requires_curated_source_coverage(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(
                    curated_sources=[
                        {
                            "vendor_doc": "mriqc_official_container_usage_outputs.md",
                            "raw_source_ids": ["mriqc_usage"],
                            "source_urls": ["https://mriqc.readthedocs.io/en/latest/usage.html"],
                            "raw_files": ["docs/rag/vendor/raw-sources/mriqc_usage.html"],
                            "source_types": ["official_docs"],
                            "manifest_backed": True,
                            "source_url_backed": True,
                            "complete": False,
                        }
                    ]
                ),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-raw-source-policy"])

    assert "RAG raw-source policy failed: curated source coverage incomplete" in str(exc.value)


def test_smoke_remote_agent_raw_source_policy_requires_pointer_integrity_metadata(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": {
                    "manifest_exists": True,
                    "manifest_schema_version": 1,
                    "source_count": 21,
                    "vendor_doc_count": 21,
                    "missing_files": [],
                    "hash_mismatches": [],
                    "raw_sources_indexed": False,
                    "indexed_raw_sources": [],
                    "curated_provenance_ok": True,
                    "curated_provenance_issues": [],
                    "curated_sources": [
                        {
                            "vendor_doc": "mriqc_official_container_usage_outputs.md",
                            "raw_source_ids": ["mriqc_usage"],
                            "source_urls": ["https://mriqc.readthedocs.io/en/latest/usage.html"],
                            "raw_files": ["docs/rag/vendor/raw-sources/mriqc_usage.html"],
                            "source_types": ["official_docs"],
                            "complete": True,
                            "manifest_backed": False,
                            "source_url_backed": True,
                        }
                    ],
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-raw-source-policy"])

    assert "RAG raw-source policy failed: curated provenance pointer integrity incomplete" in str(exc.value)


def test_smoke_remote_agent_require_vendor_pointer_integrity_reports_status(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
                "vendor_coverage_catalog": _complete_vendor_coverage_catalog(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--require-vendor-pointer-integrity"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_vendor_pointer_integrity"] is True
    assert payload["rag_vendor_pointer_integrity_status"] == "passed"
    assert payload["rag_vendor_pointer_integrity_pointer_count"] == 35
    assert payload["rag_vendor_pointer_integrity_issue_count"] == 0
    assert payload["rag_vendor_pointer_integrity_referenced_vendor_docs"] == [
        "fmriprep_official_outputs.md",
        "xcp_d_official_outputs.md",
    ]
    assert payload["rag_vendor_coverage_catalog_status"] == "complete"
    assert payload["rag_vendor_coverage_catalog_vendor_doc_count"] == 2
    assert payload["rag_vendor_coverage_catalog_complete_vendor_doc_count"] == 2
    assert payload["rag_vendor_coverage_catalog_raw_source_count"] == 2
    assert payload["rag_vendor_coverage_catalog"]["vendors"][0]["vendor_doc"] == "fmriprep_official_outputs.md"


def test_smoke_remote_agent_require_vendor_pointer_integrity_rejects_issues(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(
                    ok=False,
                    issue_count=1,
                    issues=[
                        {
                            "source_doc": "docs/rag/workflows/bold_fmriprep_xcpd.md",
                            "vendor_doc": "docs/rag/vendor/fake.md",
                            "issue": "missing_or_incomplete_vendor_doc",
                        }
                    ],
                ),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-vendor-pointer-integrity"])

    assert "RAG vendor pointer integrity failed" in str(exc.value)


def test_smoke_remote_agent_configured_run_must_succeed(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "OpenAI",
                "base_url": "https://sk-test-secret@example.invalid/v1",
                "api_key": "sk-test-secret",
                "deployment": {
                    "backend_runtime_mode": "remote",
                    "model_gateway_access": "ssh_reverse_tunnel",
                    "reverse_tunnel_command": "ssh -N -R 18080:127.0.0.1:8080 user@remote",
                },
            }
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs"):
            return {"status": "blocked", "intent": "answer_question", "selected_skill": "image-agent-operator"}
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-model"])

    assert "agent run smoke failed" in str(exc.value)


def test_smoke_remote_agent_rejects_model_unconfigured_fallback_run(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_123",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "backend-status-fallback",
                "safe_metadata": {"fallback_reason": "model_gateway_unconfigured"},
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-model"])

    assert "agent run smoke failed: model gateway fallback was used" in str(exc.value)


def test_smoke_remote_agent_expected_model_wire_api_rejects_mismatch(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "krill", "model": "gpt-5.5", "wire_api": "responses"}
        raise AssertionError(f"unexpected request after model wire_api mismatch: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-model",
                "--expected-model-wire-api",
                "chat_completions",
            ]
        )

    assert "model wire_api responses did not match --expected-model-wire-api chat_completions" in str(exc.value)


def test_smoke_remote_agent_expected_model_provider_profile_rejects_mismatch(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "deepseek",
                "provider_profile": "deepseek",
                "model": "deepseek-chat",
                "wire_api": "chat_completions",
            }
        raise AssertionError(f"unexpected request after model provider_profile mismatch: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-model",
                "--expected-model-provider-profile",
                "rawchat",
            ]
        )

    assert "model provider_profile deepseek did not match --expected-model-provider-profile rawchat" in str(exc.value)


def test_smoke_remote_agent_strict_gate_reports_successful_run(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "rawchat",
                "provider_profile": "rawchat",
                "model": "gpt-5.5",
                "wire_api": "responses",
                "capabilities": {
                    "text": True,
                    "structured_json": True,
                    "model_tool_loop": True,
                },
                "base_url": "https://sk-test-secret@example.invalid/v1",
                "api_key": "sk-test-secret",
                "trust_env_proxy": False,
                "deployment": {
                    "backend_runtime_mode": "remote",
                    "model_gateway_access": "direct",
                    "reverse_tunnel_command": "ssh -N -R 18080:127.0.0.1:8080 user@remote",
                },
            }
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_123",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-model",
            "--expected-model-wire-api",
            "responses",
            "--expected-model-provider-profile",
            "rawchat",
            "--require-model-tool-loop",
            "--require-deployment-identity",
            "--deployment-id",
            "codex-f57a2ea-20260611T023456",
            "--min-documents",
            "60",
            "--min-chunks",
            "200",
            "--require-raw-source-policy",
            "--require-vendor-pointer-integrity",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["app"] == "image_agent"
    assert payload["model_smoke_status"] == "passed"
    assert payload["model_status"]["configured"] is True
    assert payload["model_status"]["provider"] == "rawchat"
    assert payload["model_status"]["provider_profile"] == "rawchat"
    assert payload["model_status"]["model"] == "gpt-5.5"
    assert payload["model_status"]["wire_api"] == "responses"
    assert payload["model_status"]["trust_env_proxy"] is False
    assert payload["model_status"]["capabilities"]["model_tool_loop"] is True
    assert payload["smoke_gate"]["expected_model_wire_api"] == "responses"
    assert payload["smoke_gate"]["expected_model_provider_profile"] == "rawchat"
    assert payload["smoke_gate"]["require_model_tool_loop"] is True
    assert "api_key" not in payload["model_status"]
    assert "sk-test-secret" not in json.dumps(payload["model_status"])
    assert payload["model_status"]["base_url"] == "https://example.invalid/v1"
    assert payload["model_status"]["deployment"] == {
        "backend_runtime_mode": "remote",
        "model_gateway_access": "direct",
    }
    assert "reverse_tunnel_command" not in json.dumps(payload["model_status"])
    assert payload["agent_run_id"] == "agent_run_123"
    assert payload["agent_run_status"] == "answered"
    assert payload["agent_model_gateway_status"] == "passed"
    assert payload["agent_model_gateway_access"] == "openai_sdk_gateway"
    assert payload["agent_model_transport_access"] == "direct"
    assert payload["agent_model_trust_env_proxy"] is False
    assert payload["intent"] == "answer_question"
    assert payload["agent_intent"] == "answer_question"
    assert payload["selected_skill"] == "image-agent-operator"
    assert payload["rag_vendor_pointer_integrity_status"] == "passed"
    assert calls[0][1].endswith("/health")


def test_smoke_remote_agent_rawchat_requires_direct_model_gateway(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "rawchat",
                "provider_profile": "rawchat",
                "model": "gpt-5.5",
                "wire_api": "responses",
                "trust_env_proxy": False,
                "capabilities": {
                    "text": True,
                    "structured_json": True,
                    "model_tool_loop": True,
                },
                "deployment": {
                    "backend_runtime_mode": "remote",
                    "model_gateway_access": "ssh_reverse_tunnel",
                },
            }
        raise AssertionError(f"unexpected request after rawchat direct mismatch: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-model",
                "--expected-model-wire-api",
                "responses",
                "--expected-model-provider-profile",
                "rawchat",
                "--require-model-tool-loop",
            ]
        )

    assert "rawchat model gateway access ssh_reverse_tunnel did not match direct" in str(exc.value)


def test_smoke_remote_agent_require_project_agent_context_requires_project_id(monkeypatch):
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-project-agent-context"])

    assert "--require-project-agent-context requires --project-id" in str(exc.value)


def test_smoke_remote_agent_require_project_agent_context_sends_project_id_and_records_scope(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs"):
            assert payload == {
                "project_id": 7,
                "message": "Summarize the current Image Agent runtime status.",
            }
            return {
                "agent_run_id": "agent_run_789",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--require-project-agent-context",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_project_agent_context"] is True
    assert payload["agent_project_context_status"] == "passed"
    assert payload["agent_run_project_id"] == 7
    assert any(call[1].endswith("/agent/runs") and call[2]["project_id"] == 7 for call in calls)


def test_smoke_remote_agent_requires_agent_workflow_confirmation(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs") and "Prepare a workflow confirmation" in payload["message"]:
            return {
                "agent_run_id": "agent_run_confirm",
                "thread_id": "agent_thread_confirm",
                "status": "confirmation_required",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "confirmation": {
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "t1_deepprep_anat_report",
                    "workflow_metadata": {
                        "workflow_type": "t1_deepprep_anat_report",
                        "runtime_workflow_type": "t1_deepprep",
                        "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                        "workflow_family": "t1",
                        "workflow_role": "anat_processing",
                        "capability_summary": "Runs anatomical T1 processing, QC, and report outputs.",
                        "pipeline_stages": [
                            {"name": "BIDS preparation", "purpose": "Prepare supported T1 input."},
                            {"name": "DeepPrep anatomical processing", "purpose": "Generate anatomical derivatives."},
                        ],
                        "primary_outputs": ["anatomical derivatives", "result-summary.json"],
                        "qc_outputs": ["DeepPrep QC artifacts"],
                        "report_outputs": ["HTML scientific report"],
                        "limitations": ["Requires supported T1 input"],
                        "agent_selectable": True,
                        "is_report_only": False,
                    },
                },
                "production_task_created": False,
            }
        if url.endswith("/agent/runs/agent_thread_confirm/resume"):
            if payload and payload.get("approved") is True and isinstance(payload.get("confirmation"), dict):
                if payload["confirmation"].get("series_id") != 1:
                    return {
                        "agent_run_id": "agent_run_fingerprint_negative",
                        "thread_id": "agent_thread_confirm",
                        "status": "blocked",
                        "production_task_created": False,
                        "safe_metadata": {
                            "confirmation_gate": "fingerprint_mismatch",
                            "production_task_created": False,
                            "task_created": False,
                        },
                    }
            return {
                "agent_run_id": "agent_run_resume",
                "thread_id": "agent_thread_confirm",
                "status": "task_created",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "production_task_created": True,
                "safe_metadata": {"confirmation_gate": "fingerprint_verified"},
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "t1_deepprep_anat_report",
                    "runtime_workflow_type": "t1_deepprep",
                    "status": "queued",
                },
            }
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_789",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-model",
            "--project-id",
            "7",
            "--require-project-agent-context",
            "--require-agent-workflow-confirmation",
            "--launch-series-id",
            "1",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_agent_workflow_confirmation"] is True
    assert payload["agent_workflow_confirmation_status"] == "passed"
    assert payload["agent_workflow_confirmation"] == {
        "agent_run_id": "agent_run_confirm",
        "status": "confirmation_required",
        "intent": "run_workflow",
        "project_id": 7,
        "series_id": 1,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "workflow_metadata": {
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
            "display_name": "T1 DeepPrep anatomical processing, QC, and report",
            "workflow_family": "t1",
            "workflow_role": "anat_processing",
            "capability_summary": "Runs anatomical T1 processing, QC, and report outputs.",
            "pipeline_stages": [
                {"name": "BIDS preparation", "purpose": "Prepare supported T1 input."},
                {"name": "DeepPrep anatomical processing", "purpose": "Generate anatomical derivatives."},
            ],
            "primary_outputs": ["anatomical derivatives", "result-summary.json"],
            "qc_outputs": ["DeepPrep QC artifacts"],
            "report_outputs": ["HTML scientific report"],
            "limitations": ["Requires supported T1 input"],
            "agent_selectable": True,
            "is_report_only": False,
        },
        "selected_skill": "image-agent-workflow-runner",
        "production_task_created": False,
    }
    workflow_calls = [
        call for call in calls if call[1].endswith("/agent/runs") and "Prepare a workflow confirmation" in call[2]["message"]
    ]
    assert workflow_calls == [
        (
            "POST",
            "http://api.local/agent/runs",
            {
                "project_id": 7,
                "message": (
                    "Prepare a workflow confirmation for series 1 using workflow "
                    "t1_deepprep_anat_report. Do not launch it."
                ),
            },
        )
    ]


@pytest.mark.parametrize("metadata_case", ["missing_metadata", "missing_agent_selectable", "false_agent_selectable"])
def test_smoke_remote_agent_rejects_agent_workflow_confirmation_without_agent_selectable_metadata(
    metadata_case,
    monkeypatch,
):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/agent/runs") and "Prepare a workflow confirmation" in payload["message"]:
            confirmation = {
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
            }
            if metadata_case != "missing_metadata":
                workflow_metadata = _workflow_metadata("t1_deepprep_anat_report")
                if metadata_case == "missing_agent_selectable":
                    workflow_metadata.pop("agent_selectable", None)
                elif metadata_case == "false_agent_selectable":
                    workflow_metadata["agent_selectable"] = False
                confirmation["workflow_metadata"] = workflow_metadata
            return {
                "agent_run_id": "agent_run_confirm",
                "thread_id": "agent_thread_confirm",
                "status": "confirmation_required",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "confirmation": confirmation,
                "production_task_created": False,
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--require-agent-workflow-confirmation",
                "--launch-series-id",
                "1",
                "--launch-workflow-type",
                "t1_deepprep_anat_report",
            ]
        )

    if metadata_case == "missing_metadata":
        assert "agent workflow confirmation failed: workflow_metadata missing" in str(exc.value)
    else:
        assert "agent workflow confirmation failed: workflow_metadata agent_selectable invalid" in str(exc.value)


def test_smoke_remote_agent_requires_agent_workflow_resume(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []
    confirmation_request_count = 0
    confirmation = {
        "project_id": 7,
        "series_id": 1,
        "workflow_type": "t1_deepprep_anat_report",
        "workflow_metadata": _workflow_metadata("t1_deepprep_anat_report"),
    }
    tampered_confirmation = {
        **confirmation,
        "series_id": 999,
    }

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs") and "Prepare a workflow confirmation" in payload["message"]:
            nonlocal confirmation_request_count
            confirmation_request_count += 1
            thread_id = "agent_thread_confirm" if confirmation_request_count == 1 else "agent_thread_negative"
            return {
                "agent_run_id": "agent_run_confirm",
                "thread_id": thread_id,
                "status": "confirmation_required",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "confirmation": confirmation,
                "production_task_created": False,
            }
        if url.endswith("/agent/runs/agent_thread_negative/resume"):
            return {
                "agent_run_id": "agent_run_tampered",
                "thread_id": "agent_thread_negative",
                "status": "blocked",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "production_task_created": False,
                "safe_metadata": {"confirmation_gate": "fingerprint_mismatch"},
                "events": [{"type": "agent.confirmation_mismatch", "message": "Payload did not match."}],
            }
        if url.endswith("/agent/runs/agent_thread_confirm/resume"):
            return {
                "agent_run_id": "agent_run_resume",
                "thread_id": "agent_thread_confirm",
                "status": "task_created",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "production_task_created": True,
                "safe_metadata": {"confirmation_gate": "fingerprint_verified"},
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "t1_deepprep_anat_report",
                    "runtime_workflow_type": "t1_deepprep",
                    "status": "queued",
                },
            }
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_789",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-model",
            "--project-id",
            "7",
            "--require-agent-workflow-confirmation",
            "--require-agent-workflow-resume",
            "--require-agent-workflow-fingerprint-negative",
            "--launch-series-id",
            "1",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_agent_workflow_resume"] is True
    assert payload["smoke_gate"]["require_agent_workflow_fingerprint_negative"] is True
    assert payload["agent_workflow_fingerprint_negative_status"] == "passed"
    assert payload["agent_workflow_fingerprint_negative"] == {
        "agent_run_id": "agent_run_tampered",
        "thread_id": "agent_thread_negative",
        "status": "blocked",
        "production_task_created": False,
        "confirmation_gate": "fingerprint_mismatch",
        "task_created": False,
    }
    assert payload["agent_workflow_resume_status"] == "passed"
    assert payload["agent_workflow_resume"] == {
        "agent_run_id": "agent_run_resume",
        "thread_id": "agent_thread_confirm",
        "status": "task_created",
        "project_id": 7,
        "series_id": 1,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "task_id": 114,
        "initial_status": "queued",
        "production_task_created": True,
        "confirmation_gate": "fingerprint_verified",
    }
    resume_calls = [
        call
        for call in calls
        if call[0] == "POST" and call[1].startswith("http://api.local/agent/runs/agent_thread_")
    ]
    assert resume_calls == [
        (
            "POST",
            "http://api.local/agent/runs/agent_thread_negative/resume",
            {"approved": True, "confirmation": tampered_confirmation},
        ),
        (
            "POST",
            "http://api.local/agent/runs/agent_thread_confirm/resume",
            {"approved": True, "confirmation": confirmation},
        ),
    ]


def test_smoke_remote_agent_requires_agent_workflow_resume_rejects_missing_runtime_workflow_type(monkeypatch):
    smoke = _load_smoke_module()
    confirmation = {
        "project_id": 7,
        "series_id": 1,
        "workflow_type": "t1_deepprep_anat_report",
        "workflow_metadata": _workflow_metadata("t1_deepprep_anat_report"),
    }

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs") and "Prepare a workflow confirmation" in payload["message"]:
            return {
                "agent_run_id": "agent_run_confirm",
                "thread_id": "agent_thread_confirm",
                "status": "confirmation_required",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "confirmation": confirmation,
                "production_task_created": False,
            }
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_789",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        if url.endswith("/agent/runs/agent_thread_confirm/resume"):
            return {
                "agent_run_id": "agent_run_resume",
                "thread_id": "agent_thread_confirm",
                "status": "task_created",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "production_task_created": True,
                "safe_metadata": {"confirmation_gate": "fingerprint_verified"},
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "t1_deepprep_anat_report",
                    "status": "queued",
                },
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-model",
                "--project-id",
                "7",
                "--require-agent-workflow-confirmation",
                "--require-agent-workflow-resume",
                "--launch-series-id",
                "1",
                "--launch-workflow-type",
                "t1_deepprep_anat_report",
            ]
        )

    assert "agent workflow resume failed: runtime_workflow_type missing" in str(exc.value)


def test_smoke_remote_agent_require_project_agent_context_rejects_unscoped_agent_run(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 70, "chunk_count": 250, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 70, "chunk_count": 250, "semantic_index": True}
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_789",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": None,
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--require-project-agent-context",
            ]
        )

    assert "agent run project context failed: project_id mismatch" in str(exc.value)


def test_smoke_remote_agent_require_real_evidence_ids_requires_all_ids(monkeypatch):
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-real-evidence-ids", "--project-id", "7"])

    assert "--require-real-evidence-ids requires --project-id, --upload-session-id, and --task-id" in str(exc.value)


def test_smoke_remote_agent_require_real_evidence_ids_reports_supplied_ids(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "modality": "BOLD",
                    "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
                }
            ]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 1,
                            "modality": "BOLD",
                            "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
                        }
                    ],
                },
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="bold_fmriprep_xcpd", modality="BOLD")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-real-evidence-ids",
            "--project-id",
            "7",
            "--upload-session-id",
            "22",
            "--task-id",
            "114",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["remote_evidence_ids_status"] == "passed"
    assert payload["remote_evidence_ids"] == {"project_id": 7, "upload_session_id": 22, "task_id": 114}


def test_smoke_remote_agent_require_completed_task_requires_task_id():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-completed-task"])

    assert "--require-completed-task requires --task-id" in str(exc.value)


def test_smoke_remote_agent_require_completed_task_rejects_running_task(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                }
            ]
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "running",
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114", "--require-completed-task"])

    assert "completed task check failed: status=running" in str(exc.value)


def test_smoke_remote_agent_require_completed_task_records_safe_task_status(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                }
            ]
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
                "log_path": "/home/yyf/project/image_agent/data/projects/7/logs/114.log",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(
                workflow_type="t1_deepprep_anat_report",
                modality="T1",
                output_path="reports/index.html",
                output_content_type="text/html",
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--task-id", "114", "--require-completed-task"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_completed_task"] is True
    assert payload["task_status_status"] == "passed"
    assert payload["task_status"] == {
        "project_id": 7,
        "series_id": 1,
        "status": "completed",
        "task_id": 114,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
    }
    assert "log_path" not in json.dumps(payload["task_status"])


def test_smoke_remote_agent_require_launched_task_requires_launch_inputs():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-launched-task", "--task-id", "114"])

    assert "--require-launched-task requires --launch-series-id and --launch-workflow-type" in str(exc.value)


def test_smoke_remote_agent_require_launched_task_rejects_mock_workflow():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-launched-task",
                "--launch-series-id",
                "5",
                "--launch-workflow-type",
                "t1_deepprep_mock",
            ]
        )

    assert "strict deployment acceptance cannot use debug-only workflow t1_deepprep_mock" in str(exc.value)


def test_smoke_remote_agent_production_readiness_requires_agent_resume_launch_source(monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/deployment"):
            return {
                "production_readiness": {"required": True, "ready": True, "status": "ready", "blocking_reasons": []},
                "fast_launch_readiness": _ready_fast_launch_readiness(),
            }
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "queued",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-production-readiness",
                "--require-launched-task",
                "--launch-series-id",
                "1",
                "--launch-workflow-type",
                "t1_deepprep_anat_report",
            ]
        )

    assert "--require-production-readiness with --require-launched-task requires --require-agent-workflow-resume" in str(
        exc.value
    )
    assert not any(call[1].endswith("/series/1/run") for call in calls)


def test_smoke_remote_agent_deployment_identity_requires_agent_resume_launch_source(monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "queued",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-deployment-identity",
                "--deployment-id",
                "codex-f57a2ea-20260611T023456",
                "--require-launched-task",
                "--launch-series-id",
                "1",
                "--launch-workflow-type",
                "t1_deepprep_anat_report",
            ]
        )

    assert "--require-deployment-identity with --require-launched-task requires --require-agent-workflow-resume" in str(
        exc.value
    )
    assert not any(call[1].endswith("/series/1/run") for call in calls)


def test_smoke_remote_agent_runtime_toolchain_requires_agent_resume_launch_source(monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/runtime/containers"):
            return _runtime_toolchain_response()
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "dwi_fast_gpu_dti",
                "runtime_workflow_type": "dwi_fast_gpu_dti",
                "status": "queued",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="dwi_fast_gpu_dti", modality="DWI")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-runtime-toolchain",
                "--require-launched-task",
                "--launch-series-id",
                "1",
                "--launch-workflow-type",
                "dwi_fast_gpu_dti",
            ]
        )

    assert "--require-runtime-toolchain with --require-launched-task requires --require-agent-workflow-resume" in str(
        exc.value
    )
    assert not any(call[1].endswith("/series/1/run") for call in calls)


def test_smoke_remote_agent_uploads_nifti_and_uses_uploaded_series_for_launch(tmp_path, capsys, monkeypatch):
    smoke = _load_smoke_module()
    upload_file = tmp_path / "sub-01_T1w.nii.gz"
    upload_file.write_bytes(b"nifti")
    calls = []

    def fake_upload_nifti(base, project_id, path):
        calls.append(("UPLOAD", base, project_id, path))
        return {
            "upload_session_id": 22,
            "series": {
                "id": 5,
                "project_id": 7,
                "modality": "T1",
                "sequence_label": "T1w",
                "workflow_eligibility": _good_workflow_eligibility(),
            }
        }

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and url.endswith("/series/5/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 5,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "queued",
            }
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 5,
                    "modality": "T1",
                    "workflow_eligibility": _good_workflow_eligibility(),
                }
            ]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 5,
                            "modality": "T1",
                            "workflow_eligibility": _good_workflow_eligibility(),
                        }
                    ],
                },
            }
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 5,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--require-uploaded-series",
            "--upload-nifti-file",
            str(upload_file),
            "--require-completed-upload",
            "--require-launched-task",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
            "--require-completed-task",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_uploaded_series"] is True
    assert payload["smoke_gate"]["require_completed_upload"] is True
    assert payload["smoke_gate"]["upload_session_id"] == 22
    assert payload["smoke_gate"]["uploaded_series_id"] == 5
    assert payload["smoke_gate"]["launch_series_id"] == 5
    assert payload["upload_inventory_completion_status"] == "passed"
    assert payload["uploaded_series_status"] == "passed"
    assert payload["uploaded_series"] == {
        "project_id": 7,
        "series_id": 5,
        "upload_session_id": 22,
        "modality": "T1",
        "sequence_label": "T1w",
    }
    assert ("UPLOAD", "http://api.local", 7, upload_file) in calls
    assert ("POST", "http://api.local/series/5/run", {"workflow_type": "t1_deepprep_anat_report"}) in calls


def test_smoke_remote_agent_can_validate_existing_uploaded_series(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fail_upload_nifti(base, project_id, path):
        raise AssertionError("existing uploaded-series evidence must not upload a file")

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 5,
                    "project_id": 7,
                    "upload_session_id": 22,
                    "modality": "T1",
                    "sequence_label": "T1w",
                    "workflow_eligibility": _good_workflow_eligibility(),
                }
            ]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 5,
                            "modality": "T1",
                            "workflow_eligibility": _good_workflow_eligibility(),
                        }
                    ],
                },
            }
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fail_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--require-uploaded-series",
            "--uploaded-series-id",
            "5",
            "--upload-session-id",
            "22",
            "--require-completed-upload",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["uploaded_series_status"] == "passed"
    assert payload["smoke_gate"]["uploaded_series_id"] == 5
    assert payload["smoke_gate"]["upload_session_id"] == 22
    assert payload["smoke_gate"]["launch_series_id"] == 5
    assert payload["upload_inventory_completion_status"] == "passed"
    assert payload["uploaded_series"] == {
        "project_id": 7,
        "series_id": 5,
        "upload_session_id": 22,
        "modality": "T1",
        "sequence_label": "T1w",
    }
    assert not any(call[0] == "UPLOAD" for call in calls)


def test_smoke_remote_agent_rejects_launch_series_id_that_differs_from_uploaded_series(tmp_path, monkeypatch):
    smoke = _load_smoke_module()
    upload_file = tmp_path / "sub-01_T1w.nii.gz"
    upload_file.write_bytes(b"nifti")

    def fake_upload_nifti(base, project_id, path):
        return {
            "series": {
                "id": 5,
                "project_id": 7,
                "modality": "T1",
                "workflow_eligibility": _good_workflow_eligibility(),
            }
        }

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and "/series/" in url:
            raise AssertionError("smoke must reject mismatched launch-series-id before launching")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)
    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--require-uploaded-series",
                "--upload-nifti-file",
                str(upload_file),
                "--launch-series-id",
                "99",
                "--require-launched-task",
                "--launch-workflow-type",
                "t1_deepprep_anat_report",
            ]
        )

    assert "--launch-series-id must match the series returned by --require-uploaded-series" in str(exc.value)


def test_smoke_remote_agent_require_uploaded_series_requires_project_and_file(tmp_path):
    smoke = _load_smoke_module()
    upload_file = tmp_path / "sub-01_T1w.nii.gz"
    upload_file.write_bytes(b"nifti")

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-uploaded-series",
                "--upload-nifti-file",
                str(upload_file),
            ]
        )

    assert "--require-uploaded-series requires --project-id and --upload-nifti-file" in str(exc.value)


def test_smoke_remote_agent_require_launched_task_records_deterministic_run_evidence(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "queued",
            }
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-launched-task",
            "--launch-series-id",
            "1",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
            "--task-id",
            "114",
            "--require-completed-task",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_launched_task"] is True
    assert payload["launched_task_status"] == "passed"
    assert payload["launched_task"] == {
        "task_id": 114,
        "project_id": 7,
        "series_id": 1,
        "workflow_type": "t1_deepprep_anat_report",
        "runtime_workflow_type": "t1_deepprep",
        "launch_source": "direct_series_run",
        "initial_status": "queued",
    }
    assert ("POST", "http://api.local/series/1/run", {"workflow_type": "t1_deepprep_anat_report"}) in calls


def test_smoke_remote_agent_require_launched_task_rejects_missing_runtime_workflow_type(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "queued",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-launched-task",
                "--launch-series-id",
                "1",
                "--launch-workflow-type",
                "t1_deepprep_anat_report",
                "--task-id",
                "114",
            ]
        )

    assert "launched task check failed: runtime_workflow_type missing" in str(exc.value)


def test_smoke_remote_agent_require_launched_task_uses_backend_task_id(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "queued",
            }
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-launched-task",
            "--launch-series-id",
            "1",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
            "--require-completed-task",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["task_id"] == 114
    assert payload["launched_task"]["task_id"] == 114
    assert payload["task_status"]["task_id"] == 114


def test_smoke_remote_agent_reuses_persisted_agent_launch_evidence(capsys, monkeypatch, tmp_path):
    smoke = _load_smoke_module()
    state_db = tmp_path / "app.db"
    conn = sqlite3.connect(state_db)
    conn.executescript(
        """
        create table agent_runs (
          agent_run_id text primary key,
          request_type text,
          thread_id text,
          project_id integer,
          series_id integer,
          task_id integer,
          workflow_type text,
          status text,
          intent text,
          action_lane text,
          selected_skill text,
          approved integer,
          model_gateway_access text,
          safe_metadata_json text,
          created_at text,
          finished_at text
        );
        create table agent_confirmations (
          thread_id text primary key,
          status text,
          project_id integer,
          series_id integer,
          workflow_type text,
          action_lane text,
          selected_skill text,
          confirmation_json text,
          consumed_at text,
          created_at text
        );
        """
    )
    workflow_metadata = _workflow_metadata("bold_fmriprep_xcpd_report")
    workflow_metadata["runtime_workflow_type"] = "bold_fmriprep_xcpd_report"
    confirmation_json = {
        "project_id": 24,
        "series_id": 45,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "runtime_workflow_type": "bold_fmriprep_xcpd_report",
        "workflow_metadata": workflow_metadata,
    }
    conn.execute(
        """
        insert into agent_runs values
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agent_run_prepare",
            "run",
            "agent_thread_valid",
            24,
            45,
            None,
            "bold_fmriprep_xcpd_report",
            "confirmation_required",
            "run_workflow",
            "fixed_workflow",
            "image-agent-workflow-runner",
            None,
            "direct",
            json.dumps({"production_task_created": False}),
            "2026-06-20T22:16:02+00:00",
            "2026-06-20T22:16:03+00:00",
        ),
    )
    conn.execute(
        """
        insert into agent_confirmations values
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agent_thread_valid",
            "task_created",
            24,
            45,
            "bold_fmriprep_xcpd_report",
            "fixed_workflow",
            "image-agent-workflow-runner",
            json.dumps(confirmation_json),
            "2026-06-20T22:17:17+00:00",
            "2026-06-20T22:16:02+00:00",
        ),
    )
    conn.execute(
        """
        insert into agent_runs values
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agent_run_resume",
            "resume",
            "agent_thread_valid",
            24,
            45,
            135,
            "bold_fmriprep_xcpd_report",
            "task_created",
            None,
            None,
            None,
            1,
            "direct",
            json.dumps({"production_task_created": True, "confirmation_gate": "fingerprint_verified"}),
            "2026-06-20T22:17:17+00:00",
            "2026-06-20T22:17:18+00:00",
        ),
    )
    conn.execute(
        """
        insert into agent_runs values
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agent_run_negative",
            "resume",
            "agent_thread_negative",
            24,
            1043,
            None,
            "bold_fmriprep_xcpd_report",
            "blocked",
            None,
            None,
            None,
            1,
            "direct",
            json.dumps({"production_task_created": False, "confirmation_gate": "fingerprint_mismatch"}),
            "2026-06-20T22:17:17+00:00",
            "2026-06-20T22:17:18+00:00",
        ),
    )
    conn.commit()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/135"):
            return {
                "id": 135,
                "project_id": 24,
                "series_id": 45,
                "workflow_type": "bold_fmriprep_xcpd_report",
                "runtime_workflow_type": "bold_fmriprep_xcpd_report",
                "status": "completed",
            }
        if url.endswith("/projects/24/series"):
            return [
                {
                    "id": 45,
                    "modality": "BOLD",
                    "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd_report"),
                }
            ]
        if url.endswith("/tasks/135/artifact-manifest"):
            manifest = _artifact_manifest_with_result_summary_output("reports/index.html")
            manifest["task_id"] = 135
            manifest["workflow_type"] = "bold_fmriprep_xcpd_report"
            manifest["modality"] = "BOLD"
            manifest["artifacts"][0]["download_url"] = "/tasks/135/artifacts/reports/index.html"
            return manifest
        if url.endswith("/tasks/135/result-summary"):
            return _task_result_summary(
                task_id=135,
                workflow_type="bold_fmriprep_xcpd_report",
                modality="BOLD",
                outputs={
                    "bold_reports": [
                        {
                            "relative_path": "reports/index.html",
                            "download_url": "/tasks/135/artifacts/reports/index.html",
                            "content_type": "text/html",
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--skip-agent-run-smoke",
            "--project-id",
            "24",
            "--launch-series-id",
            "45",
            "--launch-workflow-type",
            "bold_fmriprep_xcpd_report",
            "--task-id",
            "135",
            "--require-agent-workflow-confirmation",
            "--require-agent-workflow-resume",
            "--require-agent-workflow-fingerprint-negative",
            "--require-launched-task",
            "--require-completed-task",
            "--reuse-persisted-agent-launch-evidence",
            "--agent-state-db",
            str(state_db),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["agent_workflow_confirmation_status"] == "passed"
    assert payload["agent_workflow_resume_status"] == "passed"
    assert payload["agent_workflow_fingerprint_negative_status"] == "passed"
    assert payload["launched_task"] == {
        "task_id": 135,
        "project_id": 24,
        "series_id": 45,
        "workflow_type": "bold_fmriprep_xcpd_report",
        "runtime_workflow_type": "bold_fmriprep_xcpd_report",
        "launch_source": "agent_workflow_resume",
        "initial_status": "completed",
    }
    assert not any(method == "POST" and "/agent/runs" in url for method, url, _ in calls)
    assert not any(method == "POST" and url.endswith("/series/45/run") for method, url, _ in calls)


def test_smoke_remote_agent_waits_for_launched_task_completion(capsys, monkeypatch):
    smoke = _load_smoke_module()
    task_statuses = iter(["running", "completed"])
    sleeps = []

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if method == "POST" and url.endswith("/series/1/run"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "queued",
            }
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": next(task_statuses),
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(smoke.time, "sleep", lambda seconds: sleeps.append(seconds))

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-launched-task",
            "--launch-series-id",
            "1",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
            "--require-completed-task",
            "--wait-task-completion-timeout-seconds",
            "60",
            "--wait-task-completion-poll-seconds",
            "5",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["task_status"]["status"] == "completed"
    assert sleeps == [5]


def test_smoke_remote_agent_require_completed_task_rejects_missing_runtime_workflow_type(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "status": "completed",
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--task-id",
                "114",
                "--require-completed-task",
            ]
        )

    assert "completed task check failed: runtime_workflow_type missing" in str(exc.value)


def test_smoke_remote_agent_require_completed_task_records_workflow_selection(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "modality": "T1",
                    "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                }
            ]
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(
                workflow_type="t1_deepprep_anat_report",
                modality="T1",
                output_path="reports/index.html",
                output_content_type="text/html",
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--task-id",
            "114",
            "--require-completed-task",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["task_workflow_selection_status"] == "passed"
    assert payload["task_workflow_selection"] == {
        "series_id": 1,
        "workflow_type": "t1_deepprep_anat_report",
        "matched_runnable_workflow": True,
    }


def test_smoke_remote_agent_require_completed_task_rejects_task_not_in_runnable_workflows(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "modality": "T1",
                    "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                }
            ]
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "bold_fmriprep_xcpd",
                "runtime_workflow_type": "bold_fmriprep_xcpd",
                "status": "completed",
            }
        if url.endswith("/tasks/114/events"):
            return {
                "status": "ok",
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "bold_fmriprep_xcpd",
                    "status": "completed",
                    "progress": 100,
                },
                "main_log": {"tail": "pipeline runner completed"},
                "remote_logs": [
                    {
                        "name": "fmriprep.log",
                        "source_stage": "fmriprep",
                        "size_bytes": 48,
                        "tail": "fMRIPrep completed",
                    }
                ],
                "events": [
                    {"type": "task.status", "status": "completed", "progress": 100},
                    {"type": "task.remote_log", "name": "fmriprep.log", "source_stage": "fmriprep", "size_bytes": 48},
                ],
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(
                workflow_type="t1_deepprep_anat_report",
                modality="T1",
                output_path="xcpd/sub-01/figures/carpetplot.png",
                output_content_type="image/png",
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--task-id",
                "114",
                "--require-completed-task",
            ]
        )

    assert "task workflow selection check failed: workflow_type not runnable for completed task series" in str(exc.value)


def test_smoke_remote_agent_require_completed_upload_requires_upload_session_id():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-completed-upload", "--project-id", "7"])

    assert "--require-completed-upload requires --project-id and --upload-session-id" in str(exc.value)


def test_smoke_remote_agent_require_completed_upload_rejects_running_inventory(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "running",
                "inventory": {
                    "inventory_status": "running",
                    "series": [{"series_id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}],
                },
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--upload-session-id",
                "22",
                "--require-completed-upload",
            ]
        )

    assert "upload inventory completion check failed: status=running" in str(exc.value)


def test_smoke_remote_agent_require_completed_upload_records_completion(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "modality": "BOLD",
                    "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
                }
            ]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 1,
                            "modality": "BOLD",
                            "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
                        }
                    ],
                },
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--upload-session-id",
            "22",
            "--require-completed-upload",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_completed_upload"] is True
    assert payload["upload_inventory_completion_status"] == "passed"
    assert payload["upload_inventory_status"] == "completed"


def test_smoke_remote_agent_require_container_native_qc_requires_task_id():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-container-native-qc"])

    assert "--require-container-native-qc requires --task-id" in str(exc.value)


def test_smoke_remote_agent_require_scientific_report_artifacts_requires_task_id():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-scientific-report-artifacts"])

    assert "--require-scientific-report-artifacts requires --task-id" in str(exc.value)


def test_smoke_remote_agent_require_scientific_report_artifacts_reports_derived_evidence(capsys, monkeypatch):
    smoke = _load_smoke_module()
    byte_requests = []

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return _scientific_report_manifest()
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(
        smoke,
        "_request_bytes",
        lambda url: (
            byte_requests.append(url)
            or (
                (b"<html>report</html>", "text/html")
                if url.endswith("/reports/index.html")
                else (b'{"figures":[]}', "application/json")
                if url.endswith("/reports/report_manifest.json")
                else (b"\x89PNG\r\n\x1a\n", "image/png")
            )
        ),
    )

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--task-id",
            "114",
            "--require-scientific-report-artifacts",
            "--min-scientific-report-images",
            "1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_scientific_report_artifacts"] is True
    assert payload["smoke_gate"]["min_scientific_report_images"] == 1
    assert payload["scientific_report_artifacts_status"] == "passed"
    assert payload["scientific_report_artifact_count"] == 3
    assert payload["scientific_report_html_count"] == 1
    assert payload["scientific_report_image_count"] == 1
    assert payload["scientific_report_json_count"] == 1
    assert payload["scientific_report_preview_kinds"] == ["html", "image", "json"]
    assert payload["scientific_report_relative_paths"] == [
        "reports/index.html",
        "reports/report_manifest.json",
        "reports/t1_qc.png",
    ]
    assert payload["scientific_report_served_urls"] == [
        "/tasks/114/artifacts/reports/index.html",
        "/tasks/114/artifacts/reports/report_manifest.json",
        "/tasks/114/artifacts/reports/t1_qc.png",
    ]
    assert byte_requests == [
        "http://api.local/tasks/114/artifacts/reports/index.html",
        "http://api.local/tasks/114/artifacts/reports/report_manifest.json",
        "http://api.local/tasks/114/artifacts/reports/t1_qc.png",
    ]
    assert payload["scientific_report_artifacts"] == [
        {
            "relative_path": "reports/index.html",
            "download_url": "/tasks/114/artifacts/reports/index.html",
            "content_type": "text/html",
            "preview_kind": "html",
            "source_stage": "scientific_report",
            "artifact_role": "derived_presentation_asset",
            "artifact_origin": "generated_from_result_summary",
            "native_artifact": False,
            "provenance": {"generated_from": "result_summary", "replaces_native_qc": False},
        },
        {
            "relative_path": "reports/report_manifest.json",
            "download_url": "/tasks/114/artifacts/reports/report_manifest.json",
            "content_type": "application/json",
            "preview_kind": "json",
            "source_stage": "scientific_report",
            "artifact_role": "derived_presentation_asset",
            "artifact_origin": "generated_from_result_summary",
            "native_artifact": False,
            "provenance": {"generated_from": "result_summary", "replaces_native_qc": False},
        },
        {
            "relative_path": "reports/t1_qc.png",
            "download_url": "/tasks/114/artifacts/reports/t1_qc.png",
            "content_type": "image/png",
            "preview_kind": "image",
            "source_stage": "scientific_report",
            "artifact_role": "derived_presentation_asset",
            "artifact_origin": "generated_from_result_summary",
            "native_artifact": False,
            "provenance": {"generated_from": "result_summary", "replaces_native_qc": False},
        },
    ]


def test_smoke_remote_agent_scientific_report_gate_ignores_non_report_assets(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            manifest = _scientific_report_manifest()
            manifest["artifacts"].append(
                _scientific_report_artifact(
                    "metadata/report-debug.json",
                    preview_kind="download",
                    content_type="application/json",
                )
            )
            return manifest
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(
        smoke,
        "_request_bytes",
        lambda url: (
            (b"<html>report</html>", "text/html")
            if url.endswith("/reports/index.html")
            else (b'{"figures":[]}', "application/json")
            if url.endswith("/reports/report_manifest.json")
            else (b"\x89PNG\r\n\x1a\n", "image/png")
        ),
    )

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--task-id",
            "114",
            "--require-scientific-report-artifacts",
            "--min-scientific-report-images",
            "1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scientific_report_artifact_count"] == 3
    assert payload["scientific_report_preview_kinds"] == ["html", "image", "json"]
    assert payload["scientific_report_relative_paths"] == [
        "reports/index.html",
        "reports/report_manifest.json",
        "reports/t1_qc.png",
    ]


@pytest.mark.parametrize(
    ("body", "served_content_type", "expected_message"),
    [
        (b"", "text/html", "scientific report artifact route returned empty bytes"),
        (b"<html>report</html>", "application/json", "scientific report artifact content_type mismatch"),
    ],
)
def test_smoke_remote_agent_require_scientific_report_artifacts_rejects_bad_served_route(
    monkeypatch,
    body,
    served_content_type,
    expected_message,
):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return _scientific_report_manifest()
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(smoke, "_request_bytes", lambda url: (body, served_content_type))

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--task-id",
                "114",
                "--require-scientific-report-artifacts",
            ]
        )

    assert expected_message in str(exc.value)


@pytest.mark.parametrize(
    ("manifest", "expected_message"),
    [
        (
            _scientific_report_manifest(result_summary_available=False),
            "task artifact manifest scientific report result_summary unavailable",
        ),
        (
            _scientific_report_manifest(
                artifacts=[
                    _scientific_report_artifact("reports/report_manifest.json", preview_kind="json", content_type="application/json"),
                    _scientific_report_artifact("reports/t1_qc.png", preview_kind="image", content_type="image/png"),
                ]
            ),
            "task artifact manifest scientific report index.html missing",
        ),
        (
            _scientific_report_manifest(
                artifacts=[
                    _scientific_report_artifact("reports/index.html", preview_kind="html", content_type="text/html"),
                    _scientific_report_artifact("reports/t1_qc.png", preview_kind="image", content_type="image/png"),
                ]
            ),
            "task artifact manifest scientific report report_manifest.json missing",
        ),
        (
            _scientific_report_manifest(
                artifacts=[
                    _scientific_report_artifact("reports/index.html", preview_kind="html", content_type="text/html"),
                    _scientific_report_artifact("reports/report_manifest.json", preview_kind="json", content_type="application/json"),
                ]
            ),
            "task artifact manifest scientific report image count 0 below minimum 1",
        ),
        (
            _scientific_report_manifest(
                artifacts=[
                    _scientific_report_artifact(
                        "reports/index.html",
                        preview_kind="html",
                        content_type="text/html",
                        provenance_override={"native_artifact": True},
                    ),
                    _scientific_report_artifact("reports/report_manifest.json", preview_kind="json", content_type="application/json"),
                    _scientific_report_artifact("reports/t1_qc.png", preview_kind="image", content_type="image/png"),
                ]
            ),
            "scientific report artifact native_artifact must be false",
        ),
    ],
)
def test_smoke_remote_agent_require_scientific_report_artifacts_rejects_invalid_manifest(manifest, expected_message):
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke._validate_task_artifact_manifest(
            manifest,
            114,
            require_scientific_report_artifacts=True,
            min_scientific_report_images=1,
        )

    assert expected_message in str(exc.value)


def test_smoke_remote_agent_require_container_native_qc_reports_served_evidence(capsys, monkeypatch):
    smoke = _load_smoke_module()
    byte_requests = []

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                        "artifact_role": "derived_presentation_asset",
                        "artifact_origin": "generated_from_result_summary",
                        "native_artifact": False,
                        "provenance": {"generated_from": "result_summary", "replaces_native_qc": False},
                    },
                    {
                        "relative_path": "fmriprep/sub-01.html",
                        "download_url": "/tasks/114/artifacts/fmriprep/sub-01.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 48,
                        "exists": True,
                        "source_stage": "fmriprep",
                        "artifact_role": "container_native_html_report",
                        "artifact_origin": "container_output",
                        "native_artifact": True,
                        "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                        "official_source_scope": "curated_vendor_docs",
                        "provenance": {
                            "generated_from": "container_native_qc",
                            "replaces_native_qc": False,
                            "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                        },
                    },
                    {
                        "relative_path": "xcpd/sub-01/figures/carpetplot.png",
                        "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
                        "preview_kind": "image",
                        "content_type": "image/png",
                        "size_bytes": 68,
                        "exists": True,
                        "source_stage": "xcpd",
                        "artifact_role": "container_native_qc_figure",
                        "artifact_origin": "container_output",
                        "native_artifact": True,
                        "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                        "official_source_scope": "curated_vendor_docs",
                        "provenance": {
                            "generated_from": "container_native_qc",
                            "replaces_native_qc": False,
                            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                        },
                    },
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {url}")

    def fake_request_bytes(url):
        byte_requests.append(url)
        if url.endswith("/fmriprep/sub-01.html"):
            return b"<html>native report</html>", "text/html; charset=utf-8"
        if url.endswith("/xcpd/sub-01/figures/carpetplot.png"):
            return b"\x89PNG\r\n\x1a\nnative-qc", "image/png"
        raise AssertionError(f"unexpected artifact byte request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(smoke, "_request_bytes", fake_request_bytes)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--task-id",
            "114",
            "--require-container-native-qc",
            "--min-native-qc-images",
            "1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["task_artifact_manifest_status"] == "passed"
    assert payload["container_native_qc_status"] == "passed"
    assert payload["container_native_qc_artifact_count"] == 2
    assert payload["container_native_qc_image_count"] == 1
    assert payload["container_native_qc_html_count"] == 1
    assert payload["container_native_qc_preview_kinds"] == ["html", "image"]
    assert payload["container_native_qc_relative_paths"] == [
        "fmriprep/sub-01.html",
        "xcpd/sub-01/figures/carpetplot.png",
    ]
    assert payload["container_native_qc_served_urls"] == [
        "/tasks/114/artifacts/fmriprep/sub-01.html",
        "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
    ]
    assert payload["container_native_qc_artifacts"] == [
        {
            "relative_path": "fmriprep/sub-01.html",
            "download_url": "/tasks/114/artifacts/fmriprep/sub-01.html",
            "content_type": "text/html",
            "preview_kind": "html",
            "artifact_origin": "container_output",
            "native_artifact": True,
            "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
            "provenance": {
                "generated_from": "container_native_qc",
                "replaces_native_qc": False,
                "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
            },
        },
        {
            "relative_path": "xcpd/sub-01/figures/carpetplot.png",
            "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
            "content_type": "image/png",
            "preview_kind": "image",
            "artifact_origin": "container_output",
            "native_artifact": True,
            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
            "provenance": {
                "generated_from": "container_native_qc",
                "replaces_native_qc": False,
                "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
            },
        },
    ]
    assert payload["container_native_qc_official_source_ids"] == [
        "docs/rag/vendor/fmriprep_official_outputs.md",
        "docs/rag/vendor/xcp_d_official_outputs.md",
    ]
    assert byte_requests == [
        "http://api.local/tasks/114/artifacts/fmriprep/sub-01.html",
        "http://api.local/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
    ]


def test_smoke_remote_agent_require_container_native_qc_rejects_derived_only_manifest(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                        "artifact_role": "derived_presentation_asset",
                        "artifact_origin": "generated_from_result_summary",
                        "native_artifact": False,
                        "provenance": {"generated_from": "result_summary", "replaces_native_qc": False},
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--task-id",
                "114",
                "--require-container-native-qc",
            ]
        )

    assert "task artifact manifest native container QC evidence missing" in str(exc.value)


def test_smoke_remote_agent_require_container_native_qc_rejects_reports_path_native_impersonation():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke._validate_task_artifact_manifest(
            {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/fake_native.png",
                        "download_url": "/tasks/114/artifacts/reports/fake_native.png",
                        "preview_kind": "image",
                        "content_type": "image/png",
                        "size_bytes": 68,
                        "exists": True,
                        "source_stage": "fmriprep",
                        "artifact_role": "container_native_qc_figure",
                        "artifact_origin": "container_output",
                        "native_artifact": True,
                        "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                        "provenance": {
                            "generated_from": "container_native_qc",
                            "replaces_native_qc": False,
                            "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                        },
                    }
                ],
                "omitted_artifacts": [],
            },
            114,
            require_native_qc_artifact=True,
            min_native_qc_images=1,
        )

    assert "task artifact manifest native container QC evidence missing" in str(exc.value)


def test_smoke_remote_agent_require_container_native_qc_rejects_missing_official_source_ids():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke._validate_task_artifact_manifest(
            {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "xcpd/sub-01.html",
                        "download_url": "/tasks/114/artifacts/xcpd/sub-01.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                        "source_stage": "xcpd",
                        "artifact_role": "container_native_html_report",
                        "artifact_origin": "container_output",
                        "native_artifact": True,
                        "official_source_ids": [],
                        "provenance": {"generated_from": "container_native_qc", "replaces_native_qc": False},
                    }
                ],
                "omitted_artifacts": [],
            },
            114,
            require_native_qc_artifact=True,
        )

    assert "native container QC artifact official_source_ids missing" in str(exc.value)


@pytest.mark.parametrize(
    ("artifact_override", "expected_message"),
    [
        (
            {
                "official_source_ids": ["docs/rag/vendor/fake.md"],
                "provenance": {
                    "generated_from": "container_native_qc",
                    "replaces_native_qc": False,
                    "official_source_ids": ["docs/rag/vendor/fake.md"],
                },
            },
            "native container QC artifact official_source_ids invalid",
        ),
        (
            {
                "official_source_ids": [r"docs\rag\vendor\xcp_d_official_outputs.md"],
                "provenance": {
                    "generated_from": "container_native_qc",
                    "replaces_native_qc": False,
                    "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                },
            },
            "native container QC artifact official_source_ids invalid",
        ),
        (
            {
                "official_source_ids": [],
                "provenance": {
                    "generated_from": "container_native_qc",
                    "replaces_native_qc": False,
                    "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                },
            },
            "native container QC artifact official_source_ids missing",
        ),
        (
            {
                "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                "provenance": {
                    "generated_from": "container_native_qc",
                    "replaces_native_qc": False,
                    "official_source_ids": [],
                },
            },
            "native container QC artifact provenance.official_source_ids missing",
        ),
        (
            {
                "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                "provenance": {
                    "generated_from": "container_native_qc",
                    "replaces_native_qc": False,
                    "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                },
            },
            "native container QC artifact official_source_ids mismatch",
        ),
    ],
)
def test_smoke_remote_agent_require_container_native_qc_rejects_untrusted_official_source_ids(
    artifact_override,
    expected_message,
):
    smoke = _load_smoke_module()
    artifact = {
        "relative_path": "xcpd/sub-01/figures/carpetplot.png",
        "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
        "preview_kind": "image",
        "content_type": "image/png",
        "size_bytes": 68,
        "exists": True,
        "source_stage": "xcpd",
        "artifact_role": "container_native_qc_figure",
        "artifact_origin": "container_output",
        "native_artifact": True,
        "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
        "provenance": {
            "generated_from": "container_native_qc",
            "replaces_native_qc": False,
            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
        },
    }
    artifact.update(artifact_override)

    with pytest.raises(SystemExit) as exc:
        smoke._validate_task_artifact_manifest(
            {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [artifact],
                "omitted_artifacts": [],
            },
            114,
            require_native_qc_artifact=True,
        )

    assert expected_message in str(exc.value)


@pytest.mark.parametrize(
    ("artifact_override", "expected_message"),
    [
        ({"artifact_role": "derived_presentation_asset"}, "native container QC artifact_role invalid"),
        ({"source_stage": ""}, "native container QC artifact source_stage missing"),
        (
            {"provenance": {"generated_from": "container_native_qc", "replaces_native_qc": True}},
            "native container QC artifact provenance.replaces_native_qc must be false",
        ),
    ],
)
def test_smoke_remote_agent_require_container_native_qc_rejects_incomplete_native_provenance(
    artifact_override,
    expected_message,
):
    smoke = _load_smoke_module()
    artifact = {
        "relative_path": "xcpd/sub-01/figures/carpetplot.png",
        "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
        "preview_kind": "image",
        "content_type": "image/png",
        "size_bytes": 68,
        "exists": True,
        "source_stage": "xcpd",
        "artifact_role": "container_native_qc_figure",
        "artifact_origin": "container_output",
        "native_artifact": True,
        "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
        "provenance": {
            "generated_from": "container_native_qc",
            "replaces_native_qc": False,
            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
        },
    }
    artifact.update(artifact_override)

    with pytest.raises(SystemExit) as exc:
        smoke._validate_task_artifact_manifest(
            {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [artifact],
                "omitted_artifacts": [],
            },
            114,
            require_native_qc_artifact=True,
        )

    assert expected_message in str(exc.value)


def test_smoke_remote_agent_require_container_native_qc_rejects_artifact_route_empty_bytes(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "xcpd/sub-01/figures/carpetplot.png",
                        "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
                        "preview_kind": "image",
                        "content_type": "image/png",
                        "size_bytes": 68,
                        "exists": True,
                        "source_stage": "xcpd",
                        "artifact_role": "container_native_qc_figure",
                        "artifact_origin": "container_output",
                        "native_artifact": True,
                        "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                        "provenance": {
                            "generated_from": "container_native_qc",
                            "replaces_native_qc": False,
                            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                        },
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(
                workflow_type="t1_deepprep_anat_report",
                modality="T1",
                output_path="xcpd/sub-01/figures/carpetplot.png",
                output_content_type="image/png",
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(smoke, "_request_bytes", lambda url: (b"", "image/png"))

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114", "--require-container-native-qc"])

    assert "native container QC artifact route returned empty bytes" in str(exc.value)


def test_smoke_remote_agent_require_container_native_qc_rejects_served_content_type_mismatch(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "xcpd/sub-01/figures/carpetplot.png",
                        "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
                        "preview_kind": "image",
                        "content_type": "image/png",
                        "size_bytes": 68,
                        "exists": True,
                        "source_stage": "xcpd",
                        "artifact_role": "container_native_qc_figure",
                        "artifact_origin": "container_output",
                        "native_artifact": True,
                        "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                        "provenance": {
                            "generated_from": "container_native_qc",
                            "replaces_native_qc": False,
                            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
                        },
                    }
                ],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(
                workflow_type="t1_deepprep_anat_report",
                modality="T1",
                output_path="xcpd/sub-01/figures/carpetplot.png",
                output_content_type="image/png",
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(smoke, "_request_bytes", lambda url: (b"\x89PNG\r\n\x1a\n", "text/html"))

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114", "--require-container-native-qc"])

    assert "native container QC artifact content_type mismatch" in str(exc.value)


def test_smoke_remote_agent_require_launchability_matrix_reports_source(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/agent/rag/status"):
                return {
                    "index": {
                        "document_count": 72,
                        "chunk_count": 260,
                        "engine": "elasticsearch_hybrid",
                        "hybrid_search": {
                            "engine": "elasticsearch",
                            "persisted": True,
                            "mode": "connected",
                            "indexed_chunk_count": 260,
                            "lexical_retriever": "standard",
                            "vector_retriever": "knn",
                            "dense_vector_field": "embedding",
                            "fusion": "rrf",
                            "official_sources": [
                                "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                            ],
                        },
                        "indexed_sources": ["docs/rag/workflows/workflow_launchability_matrix.md"],
                    },
            }
        if url.endswith("/agent/rag/query"):
            if payload and "Elasticsearch hybrid" in payload.get("query", ""):
                return {
                    "retrieval_mode": "elasticsearch_hybrid",
                    "retrieval_source": "elasticsearch_hybrid",
                    "citations": [{"path": "docs/rag/contracts/elasticsearch-hybrid-search.md", "score": 12.5}],
                    "elasticsearch_hybrid_query": {
                        "index": "image_agent_rag",
                        "dense_vector_dims": 1536,
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-small",
                        "embedding_transport": "openai_compatible_http",
                        "embedding_endpoint_configured": True,
                        "embedding_production_ready": True,
                    },
                }
            return {
                "intent": "launchability",
                "answer": "workflow_eligibility remains authoritative for launchability.",
                "citations": [
                    {
                        "path": "docs/rag/workflows/workflow_launchability_matrix.md",
                        "title": "Workflow Launchability Matrix",
                    }
                ],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--require-launchability-matrix"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["rag_launchability_matrix_status"] == "passed"
    assert payload["rag_launchability_matrix_source"] == "docs/rag/workflows/workflow_launchability_matrix.md"
    assert payload["rag_launchability_query_status"] == "passed"
    assert payload["rag_launchability_query_intent"] == "launchability"
    assert payload["rag_launchability_query_source"] == "docs/rag/workflows/workflow_launchability_matrix.md"
    query_calls = [call for call in calls if call[1].endswith("/agent/rag/query")]
    assert query_calls == [
        (
            "POST",
            "http://api.local/agent/rag/query",
            {"query": smoke.LAUNCHABILITY_SMOKE_QUERY},
        )
    ]


def test_smoke_remote_agent_require_launchability_matrix_rejects_missing_source(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-launchability-matrix"])

    assert "RAG launchability matrix evidence missing" in str(exc.value)


def test_smoke_remote_agent_require_launchability_matrix_rejects_missing_query_citation(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "hybrid_search": {
                        "engine": "elasticsearch",
                        "configured": True,
                        "persisted": True,
                        "mode": "connected",
                        "index": "image_agent_rag",
                        "indexed_chunk_count": 260,
                        "lexical_retriever": "standard",
                        "vector_retriever": "knn",
                        "dense_vector_field": "embedding",
                        "dense_vector_dims": 1536,
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-small",
                        "embedding_transport": "openai_compatible_http",
                        "embedding_endpoint_configured": True,
                        "embedding_production_ready": True,
                        "fusion": "rrf",
                        "official_sources": [
                            "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                        ],
                    },
                    "indexed_sources": ["docs/rag/workflows/workflow_launchability_matrix.md"],
                },
            }
        if url.endswith("/agent/rag/query"):
            return {
                "intent": "launchability",
                "answer": "Missing matrix citation.",
                "citations": [{"path": "docs/rag/vendor/mriqc_official_container_usage_outputs.md"}],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-launchability-matrix"])

    assert "RAG launchability matrix query citation missing" in str(exc.value)


def test_smoke_remote_agent_require_launchability_matrix_rejects_answer_text_source_only(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "llama_index",
                    "indexed_sources": ["docs/rag/workflows/workflow_launchability_matrix.md"],
                },
            }
        if url.endswith("/agent/rag/query"):
            return {
                "intent": "launchability",
                "answer": "Answer text has no citation but ends with docs/rag/workflows/workflow_launchability_matrix.md",
                "citations": [],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-launchability-matrix"])

    assert "RAG launchability matrix query citation missing" in str(exc.value)


def test_smoke_remote_agent_require_launchability_matrix_rejects_wrong_query_intent(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "llama_index",
                    "indexed_sources": ["docs/rag/workflows/workflow_launchability_matrix.md"],
                },
            }
        if url.endswith("/agent/rag/query"):
            return {
                "intent": "general",
                "answer": "Wrong intent.",
                "citations": [{"path": "docs/rag/workflows/workflow_launchability_matrix.md"}],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-launchability-matrix"])

    assert "RAG launchability query intent failed" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_non_elasticsearch_index(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "llama_index",
                    "semantic_index": True,
                    "hybrid_search": {"engine": "elasticsearch", "persisted": False, "fusion": "rrf"},
                },
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "RAG Elasticsearch hybrid search is not active" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_records_acceptance_evidence(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []
    official_sources = [
        "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
        "https://internal.example.local/private-rag-notes",
        "C:/srv/image_agent/private-source.md",
    ]

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(official_sources=official_sources),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(),
            }
        if url.endswith("/agent/rag/query"):
            return {
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "elasticsearch_hybrid_query": {
                    "index": "image_agent_rag",
                    "lexical_retriever": "standard",
                    "vector_retriever": "knn",
                    "dense_vector_field": "embedding",
                    "fusion": "rrf",
                    "dense_vector_dims": 1536,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_transport": "openai_compatible_http",
                    "embedding_endpoint_configured": True,
                    "embedding_production_ready": True,
                },
                "citations": [
                    {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "snippet": "Elasticsearch hybrid search uses BM25, dense vector kNN, and RRF.",
                        "score": 12.5,
                    }
                ],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_elasticsearch_hybrid_rag"] is True
    assert payload["rag_elasticsearch_hybrid_status"] == "passed"
    assert payload["rag_elasticsearch_hybrid"]["engine"] == "elasticsearch"
    assert payload["rag_elasticsearch_hybrid"]["configured"] is True
    assert payload["rag_elasticsearch_hybrid"]["index"] == "image_agent_rag"
    assert payload["rag_elasticsearch_hybrid"]["fusion"] == "rrf"
    assert payload["rag_elasticsearch_hybrid"]["dense_vector_dims"] == 1536
    assert payload["rag_elasticsearch_hybrid"]["embedding_provider"] == "openai"
    assert payload["rag_elasticsearch_hybrid"]["embedding_model"] == "text-embedding-3-small"
    assert payload["rag_elasticsearch_hybrid"]["embedding_transport"] == "openai_compatible_http"
    assert payload["rag_elasticsearch_hybrid"]["embedding_endpoint_configured"] is True
    assert payload["rag_elasticsearch_hybrid"]["embedding_production_ready"] is True
    assert payload["rag_elasticsearch_hybrid"]["official_rrf_source_present"] is True
    assert "official_sources" not in payload["rag_elasticsearch_hybrid"]
    serialized_payload = json.dumps(payload)
    assert "internal.example.local" not in serialized_payload
    assert "C:/srv/image_agent/private-source.md" not in serialized_payload
    assert payload["rag_rebuild_elasticsearch_hybrid"]["mode"] == "connected"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["configured"] is True
    assert payload["rag_rebuild_elasticsearch_hybrid"]["index"] == "image_agent_rag"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["indexed_chunk_count"] == 260
    assert payload["rag_rebuild_elasticsearch_hybrid"]["lexical_retriever"] == "standard"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["vector_retriever"] == "knn"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["dense_vector_field"] == "embedding"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["dense_vector_dims"] == 1536
    assert payload["rag_rebuild_elasticsearch_hybrid"]["embedding_model"] == "text-embedding-3-small"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["embedding_transport"] == "openai_compatible_http"
    assert payload["rag_rebuild_elasticsearch_hybrid"]["embedding_endpoint_configured"] is True
    assert payload["rag_rebuild_elasticsearch_hybrid"]["fusion"] == "rrf"
    assert payload["rag_elasticsearch_hybrid_query_status"] == "passed"
    assert payload["rag_elasticsearch_hybrid_query_mode"] == "elasticsearch_hybrid"
    assert payload["rag_elasticsearch_hybrid_query_retrieval_source"] == "elasticsearch_hybrid"
    assert payload["rag_elasticsearch_hybrid_query_source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"
    assert payload["rag_elasticsearch_hybrid_query_citation_count"] == 1
    assert payload["rag_elasticsearch_hybrid_query_top_score"] == 12.5
    assert payload["rag_elasticsearch_hybrid_query_index"] == "image_agent_rag"
    assert payload["rag_elasticsearch_hybrid_query_lexical_retriever"] == "standard"
    assert payload["rag_elasticsearch_hybrid_query_vector_retriever"] == "knn"
    assert payload["rag_elasticsearch_hybrid_query_dense_vector_field"] == "embedding"
    assert payload["rag_elasticsearch_hybrid_query_fusion"] == "rrf"
    assert payload["rag_elasticsearch_hybrid_query_dense_vector_dims"] == 1536
    assert payload["rag_elasticsearch_hybrid_query_embedding_provider"] == "openai"
    assert payload["rag_elasticsearch_hybrid_query_embedding_model"] == "text-embedding-3-small"
    assert payload["rag_elasticsearch_hybrid_query_embedding_transport"] == "openai_compatible_http"
    assert payload["rag_elasticsearch_hybrid_query_embedding_endpoint_configured"] is True
    assert payload["rag_elasticsearch_hybrid_query_embedding_production_ready"] is True
    assert any(call[1].endswith("/agent/rag/query") for call in calls)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_query_embedding_drift(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(),
            }
        if url.endswith("/agent/rag/query"):
            return {
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "elasticsearch_hybrid_query": {
                    "index": "image_agent_rag",
                    "lexical_retriever": "standard",
                    "vector_retriever": "knn",
                    "dense_vector_field": "embedding",
                    "fusion": "rrf",
                    "dense_vector_dims": 1536,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-large",
                    "embedding_transport": "openai_compatible_http",
                    "embedding_endpoint_configured": True,
                    "embedding_production_ready": True,
                },
                "citations": [
                    {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "score": 12.5,
                    }
                ],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "RAG Elasticsearch hybrid query evidence mismatch: embedding_model must match status" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_query_without_hybrid_components(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(),
            }
        if url.endswith("/agent/rag/query"):
            return {
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "elasticsearch_hybrid_query": {
                    "index": "image_agent_rag",
                    "dense_vector_dims": 1536,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_transport": "openai_compatible_http",
                    "embedding_endpoint_configured": True,
                    "embedding_production_ready": True,
                },
                "citations": [
                    {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "score": 12.5,
                    }
                ],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "RAG Elasticsearch hybrid query evidence missing: lexical_retriever must be standard" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_unscored_query_evidence(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(),
            }
        if url.endswith("/agent/rag/query"):
            return {
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "citations": [{"source": "docs/rag/contracts/elasticsearch-hybrid-search.md"}],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "RAG Elasticsearch hybrid query evidence missing positive score" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_local_hash_embeddings(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(
                        dense_vector_dims=64,
                        embedding_provider="local_hashing",
                        embedding_model="local-token-hash-v1",
                        embedding_production_ready=False,
                    ),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(
                    dense_vector_dims=64,
                    embedding_provider="local_hashing",
                    embedding_model="local-token-hash-v1",
                    embedding_production_ready=False,
                ),
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "embedding_provider must be production configured" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_local_token_hash_embeddings(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(
                        embedding_provider="local-token-hash-v1",
                        embedding_model="local-token-hash-v1",
                    ),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(
                    embedding_provider="local-token-hash-v1",
                    embedding_model="local-token-hash-v1",
                ),
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "embedding_provider must be production configured" in str(exc.value)


@pytest.mark.parametrize("endpoint_value", [None, False, "true"])
def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_unverified_embedding_endpoint(
    monkeypatch,
    endpoint_value,
):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            hybrid = _elasticsearch_hybrid_search()
            if endpoint_value is None:
                hybrid.pop("embedding_endpoint_configured")
            else:
                hybrid["embedding_endpoint_configured"] = endpoint_value
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": hybrid,
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            hybrid = _elasticsearch_hybrid_search()
            if endpoint_value is None:
                hybrid.pop("embedding_endpoint_configured")
            else:
                hybrid["embedding_endpoint_configured"] = endpoint_value
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": hybrid,
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "embedding_endpoint_configured must be true" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_embedding_error(monkeypatch):
    smoke = _load_smoke_module()

    def hybrid_payload():
        return _elasticsearch_hybrid_search(
            embedding_error="[redacted-secret]",
        )

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": hybrid_payload(),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": hybrid_payload(),
            }
        if url.endswith("/agent/rag/query"):
            return {
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "citations": [{"source": "docs/rag/contracts/elasticsearch-hybrid-search.md"}],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "embedding_error must be absent" in str(exc.value)


def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_fallback_query(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(),
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": _elasticsearch_hybrid_search(),
            }
        if url.endswith("/agent/rag/query"):
            return {"retrieval_mode": "elasticsearch_hybrid_fallback", "citations": []}
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert "RAG Elasticsearch hybrid query did not use Elasticsearch retrieval" in str(exc.value)


@pytest.mark.parametrize(
    ("hybrid_override", "expected_message"),
    [
        ({"mode": "local_contract"}, "hybrid_search.mode must be connected"),
        ({"indexed_chunk_count": 0}, "indexed_chunk_count must be greater than zero"),
        ({"dense_vector_dims": 0}, "dense_vector_dims must be greater than zero"),
        ({"embedding_model": ""}, "embedding_model must be present"),
        ({"embedding_transport": ""}, "embedding_transport must be present"),
        ({"embedding_transport": "local"}, "embedding_transport must be production-safe"),
        ({"error": "[redacted-secret] connection refused"}, "hybrid_search.error must be absent"),
    ],
)
def test_smoke_remote_agent_require_elasticsearch_hybrid_rag_rejects_weak_connected_evidence(
    monkeypatch,
    hybrid_override,
    expected_message,
):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "semantic_index": True,
                    "hybrid_search": _elasticsearch_hybrid_search(**hybrid_override),
                },
            }
        if url.endswith("/agent/rag/query"):
            return {
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "citations": [{"source": "docs/rag/contracts/elasticsearch-hybrid-search.md"}],
            }
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--require-elasticsearch-hybrid-rag"])

    assert expected_message in str(exc.value)


def test_smoke_remote_agent_require_runtime_toolchain_records_safe_deployment_local_evidence(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append(url)
        if url.endswith("/runtime/containers"):
            return _runtime_toolchain_response()
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-runtime-toolchain",
            "--launch-workflow-type",
            "dwi_fast_gpu_dti",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert any(url.endswith("/runtime/containers") for url in calls)
    assert payload["smoke_gate"]["require_runtime_toolchain"] is True
    assert payload["runtime_toolchain_status"] == "passed"
    assert payload["runtime_toolchain"] == {
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "docker_requires_sudo": True,
        "fs_license_exists": True,
        "workflow_count": 2,
        "available_workflow_count": 2,
        "required_workflow_type": "dwi_fast_gpu_dti",
        "required_workflow_available": True,
        "unavailable_workflows": [],
        "workflow_types": ["dwi_fast_gpu_dti", "t1_deepprep"],
    }
    serialized = json.dumps(payload, sort_keys=True)
    assert "C:/Users/A/private" not in serialized
    assert "detail_tail" not in serialized
    assert "fs_license_path" not in serialized


def test_smoke_remote_agent_runtime_toolchain_resolves_stable_workflow_to_runtime_workflow(capsys, monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/runtime/containers"):
            return _runtime_toolchain_response(workflows={"t1_deepprep": {"available": True}})
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-runtime-toolchain",
            "--launch-workflow-type",
            "t1_deepprep_anat_report",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime_toolchain_status"] == "passed"
    assert payload["runtime_toolchain"]["required_workflow_type"] == "t1_deepprep_anat_report"
    assert payload["runtime_toolchain"]["required_runtime_workflow_type"] == "t1_deepprep"
    assert payload["runtime_toolchain"]["required_workflow_available"] is True
    assert payload["runtime_toolchain"]["workflow_types"] == ["t1_deepprep"]


def test_smoke_remote_agent_prefers_runtime_probe_for_toolchain_evidence(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append(url)
        if url.endswith("/runtime/probe"):
            return {
                "schema_version": 1,
                "status": "blocked",
                "workflow_tool_execution": "deployment_server_local",
                "docker_runtime_host": "api_server",
                "docker": {"requires_sudo": True},
                "resources": {"fs_license_exists": True},
                "workflow_count": 2,
                "available_workflow_count": 2,
                "workflows": {
                    "bold_fmriprep_xcpd_report": {"available": True},
                    "t1_deepprep_anat_report": {"available": True},
                },
            }
        if url.endswith("/runtime/containers"):
            raise AssertionError("runtime/containers should be fallback-only when runtime/probe is available")
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-runtime-toolchain",
            "--launch-workflow-type",
            "bold_fmriprep_xcpd_report",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert any(url.endswith("/runtime/probe") for url in calls)
    assert payload["runtime_toolchain_status"] == "passed"
    assert payload["runtime_toolchain"]["workflow_tool_execution"] == "deployment_server_local"
    assert payload["runtime_toolchain"]["docker_runtime_host"] == "api_server"
    assert payload["runtime_toolchain"]["docker_requires_sudo"] is True
    assert payload["runtime_toolchain"]["required_workflow_available"] is True


def test_smoke_remote_agent_require_runtime_toolchain_rejects_missing_launch_workflow(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/runtime/containers"):
            return _runtime_toolchain_response(workflows={"t1_deepprep": {"available": True}})
        return _good_remote_smoke_response(url)

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-runtime-toolchain",
                "--launch-workflow-type",
                "dwi_fast_gpu_dti",
            ]
        )

    assert "runtime toolchain missing required workflow dwi_fast_gpu_dti" in str(exc.value)


def test_smoke_remote_agent_writes_acceptance_json_artifact(capsys, monkeypatch, tmp_path):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
                "vendor_coverage_catalog": _complete_vendor_coverage_catalog(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        if url.endswith("/agent/runs"):
            return {
                "agent_run_id": "agent_run_456",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        raise AssertionError(f"unexpected request: {url}")

    output_path = tmp_path / "acceptance" / "strict-smoke.json"
    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--require-model",
            "--require-deployment-identity",
            "--deployment-id",
            "codex-f57a2ea-20260611T023456",
            "--min-documents",
            "60",
            "--min-chunks",
            "200",
            "--require-raw-source-policy",
            "--require-vendor-pointer-integrity",
            "--output-json",
            str(output_path),
        ]
    )

    stdout_payload = json.loads(capsys.readouterr().out)
    artifact_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact_payload == stdout_payload
    assert artifact_payload["smoke_gate"] == {
        "api_base": "http://api.local",
        "require_model": True,
        "skip_agent_run_smoke": False,
        "require_project_agent_context": False,
        "require_agent_workflow_confirmation": False,
        "require_agent_workflow_resume": False,
        "require_agent_workflow_fingerprint_negative": False,
        "require_unknown_workflow_incubation": False,
        "require_deployment_identity": True,
        "require_production_readiness": False,
        "require_runtime_toolchain": False,
        "deployment_id": "codex-f57a2ea-20260611T023456",
        "min_documents": 60,
        "min_chunks": 200,
        "require_raw_source_policy": True,
        "require_vendor_pointer_integrity": True,
        "require_elasticsearch_hybrid_rag": False,
        "require_real_evidence_ids": False,
        "require_completed_upload": False,
        "require_uploaded_series": False,
        "require_completed_task": False,
        "require_task_events": False,
        "require_observe_repair": False,
        "require_launched_task": False,
        "require_launchability_matrix": False,
        "require_container_native_qc": False,
        "min_native_qc_images": 0,
        "require_scientific_report_artifacts": False,
        "min_scientific_report_images": 0,
        "project_id": None,
        "task_id": None,
        "upload_session_id": None,
        "uploaded_series_id": None,
        "launch_series_id": None,
    }
    assert artifact_payload["deployment_identity_status"] == "passed"
    assert artifact_payload["deployment_identity"] == {
        "deployment_id": "codex-f57a2ea-20260611T023456",
        "health_app": "image_agent",
        "health_version": "0.2.0",
    }
    assert artifact_payload["production_readiness_status"] == "skipped"
    assert artifact_payload["production_readiness"] is None
    assert artifact_payload["upload_inventory_completion_status"] == "skipped"
    assert artifact_payload["rag_vendor_pointer_integrity_status"] == "passed"
    assert artifact_payload["rag_vendor_pointer_integrity_referenced_vendor_docs"] == [
        "fmriprep_official_outputs.md",
        "xcp_d_official_outputs.md",
    ]
    assert artifact_payload["rag_vendor_coverage_catalog_status"] == "complete"
    assert artifact_payload["rag_vendor_coverage_catalog_vendor_doc_count"] == 2
    assert artifact_payload["rag_vendor_coverage_catalog_complete_vendor_doc_count"] == 2
    assert "manifest_path" not in json.dumps(artifact_payload["rag_vendor_coverage_catalog"])
    assert "raw_snapshots" not in json.dumps(artifact_payload["rag_vendor_coverage_catalog"])
    assert artifact_payload["generated_at_utc"].endswith("Z")


def test_smoke_remote_agent_rejects_vendor_coverage_catalog_curated_source_drift(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": True, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"},
                "vendor_raw_sources": _complete_vendor_raw_sources(
                    curated_sources=[
                        {
                            "vendor_doc": "fmriprep_official_outputs.md",
                            "complete": True,
                            "raw_source_ids": ["fmriprep_outputs"],
                            "source_urls": ["https://fmriprep.org/en/stable/outputs.html"],
                            "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_outputs.html"],
                            "source_types": ["official_docs"],
                            "manifest_backed": True,
                            "source_url_backed": True,
                        }
                    ],
                    vendor_doc_count=1,
                    source_count=1,
                ),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
                "vendor_coverage_catalog": _complete_vendor_coverage_catalog(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        if url.endswith("/agent/runs") and "Prepare a workflow confirmation" in payload["message"]:
            return {
                "agent_run_id": "agent_run_confirm",
                "thread_id": "agent_thread_confirm",
                "status": "confirmation_required",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "confirmation": {
                    "project_id": 7,
                    "series_id": 1,
                        "workflow_type": "bold_fmriprep_xcpd",
                        "workflow_metadata": {
                            "workflow_type": "bold_fmriprep_xcpd",
                            "runtime_workflow_type": "bold_fmriprep_xcpd",
                            "display_name": "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report",
                        "workflow_family": "bold",
                        "workflow_role": "complete_processing",
                        "capability_summary": "Runs BOLD preprocessing, XCP-D metrics, QC, and report outputs.",
                        "pipeline_stages": [
                            {"name": "BIDS preparation", "purpose": "Prepare supported BOLD input."},
                            {"name": "fMRIPrep preprocessing", "purpose": "Generate preprocessed BOLD derivatives."},
                            {"name": "XCP-D postprocessing", "purpose": "Generate metrics and QC outputs."},
                        ],
                        "primary_outputs": ["preprocessed BOLD derivatives", "ALFF/fALFF/ReHo metrics"],
                        "qc_outputs": ["container-native fMRIPrep and XCP-D QC artifacts"],
                        "report_outputs": ["HTML scientific report"],
                        "limitations": ["Requires BOLD-compatible input and configured containers"],
                        "agent_selectable": True,
                        "is_report_only": False,
                    },
                },
                "production_task_created": False,
            }
        if url.endswith("/agent/runs/agent_thread_confirm/resume"):
            if payload and payload.get("approved") is True and isinstance(payload.get("confirmation"), dict):
                if payload["confirmation"].get("series_id") != 1:
                    return {
                        "agent_run_id": "agent_run_fingerprint_negative",
                        "thread_id": "agent_thread_confirm",
                        "status": "blocked",
                        "production_task_created": False,
                        "safe_metadata": {
                            "confirmation_gate": "fingerprint_mismatch",
                            "production_task_created": False,
                            "task_created": False,
                        },
                    }
            return {
                "agent_run_id": "agent_run_resume",
                "thread_id": "agent_thread_confirm",
                "status": "task_created",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "production_task_created": True,
                "safe_metadata": {"confirmation_gate": "fingerprint_verified"},
                    "task": {
                        "id": 114,
                        "project_id": 7,
                        "series_id": 1,
                        "workflow_type": "bold_fmriprep_xcpd",
                        "runtime_workflow_type": "bold_fmriprep_xcpd",
                        "status": "queued",
                    },
                }
        if url.endswith("/agent/runs"):
            message = payload.get("message", "") if isinstance(payload, dict) else ""
            if "codex_unknown_workflow_smoke" in message:
                return {
                    "agent_run_id": "agent_run_unknown",
                    "thread_id": "agent_thread_unknown",
                    "status": "toolchain_proposed",
                    "intent": "toolchain_incubation",
                    "selected_skill": "image-agent-toolchain-incubator",
                    "action_lane": "toolchain_incubation",
                    "workflow_type": "codex_unknown_workflow_smoke",
                    "proposed_toolchain": {
                        "proposal_id": "inc_codex_unknown",
                        "workflow_type": "codex_unknown_workflow_smoke",
                        "action_lane": "toolchain_incubation",
                        "production_task_created": False,
                    },
                    "production_task_created": False,
                    "task_created": False,
                    "confirmation_created": False,
                    "task_creation_allowed": False,
                    "forbidden_actions": [
                        "confirmation_creation",
                        "production_task_creation",
                        "pipeline_runner_launch",
                    ],
                }
            return {
                "agent_run_id": "agent_run_456",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--require-model",
                "--require-raw-source-policy",
                "--require-vendor-pointer-integrity",
            ]
        )

    assert "RAG vendor coverage catalog failed: vendors must match curated_sources" in str(exc.value)


def test_smoke_remote_agent_strict_output_passes_offline_acceptance_verifier(capsys, monkeypatch, tmp_path):
    smoke = _load_smoke_module()
    verifier = _load_verifier_module()
    upload_file = tmp_path / "sub-01_bold.nii.gz"
    upload_file.write_bytes(b"bold")

    native_artifacts = [
        {
            "relative_path": "fmriprep/sub-01.html",
            "download_url": "/tasks/114/artifacts/fmriprep/sub-01.html",
            "preview_kind": "html",
            "content_type": "text/html",
            "size_bytes": 48,
            "exists": True,
            "source_stage": "fmriprep",
            "artifact_role": "container_native_html_report",
            "artifact_origin": "container_output",
            "native_artifact": True,
            "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
            "provenance": {
                "generated_from": "container_native_qc",
                "replaces_native_qc": False,
                "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
            },
        },
        {
            "relative_path": "xcpd/sub-01/figures/carpetplot.png",
            "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
            "preview_kind": "image",
            "content_type": "image/png",
            "size_bytes": 68,
            "exists": True,
            "source_stage": "xcpd",
            "artifact_role": "container_native_qc_figure",
            "artifact_origin": "container_output",
            "native_artifact": True,
            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
            "provenance": {
                "generated_from": "container_native_qc",
                "replaces_native_qc": False,
                "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
            },
        },
    ]
    report_manifest = _scientific_report_manifest()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/deployment"):
            return {
                "production_readiness": {
                    "required": True,
                    "ready": True,
                    "status": "ready",
                    "blocking_reasons": [],
                },
                    "fast_launch_readiness": _pre_acceptance_fast_launch_readiness(),
            }
        if url.endswith("/runtime/containers"):
            return _runtime_toolchain_response(
                workflows={
                    "bold_fmriprep_xcpd": {"available": True},
                    "t1_deepprep_anat_report": {"available": True},
                }
            )
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "rawchat",
                "provider_profile": "rawchat",
                "model": "gpt-5.5",
                "wire_api": "responses",
                "trust_env_proxy": False,
                "capabilities": {
                    "text": True,
                    "structured_json": True,
                    "model_tool_loop": True,
                },
                "deployment": {
                    "backend_runtime_mode": "remote",
                    "model_gateway_access": "direct",
                },
            }
        if url.endswith("/agent/rag/status"):
            return {
                "index": {
                    "document_count": 72,
                    "chunk_count": 260,
                    "engine": "elasticsearch_hybrid",
                    "hybrid_search": {
                        "engine": "elasticsearch",
                        "configured": True,
                        "persisted": True,
                        "mode": "connected",
                        "index": "image_agent_rag",
                        "indexed_chunk_count": 260,
                        "lexical_retriever": "standard",
                        "vector_retriever": "knn",
                        "dense_vector_field": "embedding",
                        "dense_vector_dims": 1536,
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-small",
                        "embedding_transport": "openai_compatible_http",
                        "embedding_endpoint_configured": True,
                        "embedding_production_ready": True,
                        "fusion": "rrf",
                        "official_sources": [
                            "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                        ],
                    },
                    "indexed_sources": ["docs/rag/workflows/workflow_launchability_matrix.md"],
                },
                "vendor_raw_sources": _complete_vendor_raw_sources(),
                "vendor_pointer_integrity": _complete_vendor_pointer_integrity(),
                "vendor_coverage_catalog": _complete_vendor_coverage_catalog(),
            }
        if url.endswith("/agent/rag/rebuild"):
            return {
                "document_count": 72,
                "chunk_count": 260,
                "semantic_index": True,
                "hybrid_search": {
                    "engine": "elasticsearch",
                    "configured": True,
                    "persisted": True,
                    "mode": "connected",
                    "index": "image_agent_rag",
                    "indexed_chunk_count": 260,
                    "lexical_retriever": "standard",
                    "vector_retriever": "knn",
                    "dense_vector_field": "embedding",
                    "dense_vector_dims": 1536,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_transport": "openai_compatible_http",
                    "embedding_endpoint_configured": True,
                    "embedding_production_ready": True,
                    "fusion": "rrf",
                    "official_sources": [
                        "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                    ],
                },
            }
        if url.endswith("/agent/rag/query"):
            if payload and "Elasticsearch hybrid" in payload.get("query", ""):
                return {
                    "retrieval_mode": "elasticsearch_hybrid",
                    "retrieval_source": "elasticsearch_hybrid",
                    "citations": [{"path": "docs/rag/contracts/elasticsearch-hybrid-search.md", "score": 12.5}],
                    "elasticsearch_hybrid_query": {
                        "index": "image_agent_rag",
                        "lexical_retriever": "standard",
                        "vector_retriever": "knn",
                        "dense_vector_field": "embedding",
                        "fusion": "rrf",
                        "dense_vector_dims": 1536,
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-small",
                        "embedding_transport": "openai_compatible_http",
                        "embedding_endpoint_configured": True,
                        "embedding_production_ready": True,
                    },
                }
            return {
                "intent": "launchability",
                "answer": "workflow_eligibility remains authoritative for launchability.",
                "citations": [{"path": "docs/rag/workflows/workflow_launchability_matrix.md"}],
            }
        if url.endswith("/agent/runs") and "Prepare a workflow confirmation" in payload["message"]:
            return {
                "agent_run_id": "agent_run_confirm",
                "thread_id": "agent_thread_confirm",
                "status": "confirmation_required",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "confirmation": {
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "bold_fmriprep_xcpd",
                    "workflow_metadata": {
                        "workflow_type": "bold_fmriprep_xcpd",
                        "runtime_workflow_type": "bold_fmriprep_xcpd",
                        "display_name": "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report",
                        "workflow_family": "bold",
                        "workflow_role": "complete_processing",
                        "capability_summary": "Runs BOLD preprocessing, XCP-D metrics, QC, and report outputs.",
                        "pipeline_stages": [
                            {"name": "BIDS preparation", "purpose": "Prepare supported BOLD input."},
                            {"name": "fMRIPrep preprocessing", "purpose": "Generate preprocessed BOLD derivatives."},
                            {"name": "XCP-D postprocessing", "purpose": "Generate metrics and QC outputs."},
                        ],
                        "primary_outputs": ["preprocessed BOLD derivatives", "ALFF/fALFF/ReHo metrics"],
                        "qc_outputs": ["container-native fMRIPrep and XCP-D QC artifacts"],
                        "report_outputs": ["HTML scientific report"],
                        "limitations": ["Requires BOLD-compatible input and configured containers"],
                        "agent_selectable": True,
                        "is_report_only": False,
                    },
                },
                "production_task_created": False,
            }
        if url.endswith("/agent/runs/agent_thread_confirm/resume"):
            if payload and payload.get("approved") is True and isinstance(payload.get("confirmation"), dict):
                if payload["confirmation"].get("series_id") != 1:
                    return {
                        "agent_run_id": "agent_run_fingerprint_negative",
                        "thread_id": "agent_thread_confirm",
                        "status": "blocked",
                        "production_task_created": False,
                        "safe_metadata": {
                            "confirmation_gate": "fingerprint_mismatch",
                            "production_task_created": False,
                            "task_created": False,
                        },
                    }
            return {
                "agent_run_id": "agent_run_resume",
                "thread_id": "agent_thread_confirm",
                "status": "task_created",
                "intent": "run_workflow",
                "selected_skill": "image-agent-workflow-runner",
                "project_id": 7,
                "production_task_created": True,
                "safe_metadata": {"confirmation_gate": "fingerprint_verified"},
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "bold_fmriprep_xcpd",
                    "runtime_workflow_type": "bold_fmriprep_xcpd",
                    "status": "queued",
                },
            }
        if url.endswith("/agent/runs"):
            message = payload.get("message", "") if isinstance(payload, dict) else ""
            if "codex_unknown_workflow_smoke" in message:
                return {
                    "agent_run_id": "agent_run_unknown",
                    "thread_id": "agent_thread_unknown",
                    "status": "toolchain_proposed",
                    "intent": "toolchain_incubation",
                    "selected_skill": "image-agent-toolchain-incubator",
                    "action_lane": "toolchain_incubation",
                    "workflow_type": "codex_unknown_workflow_smoke",
                    "proposed_toolchain": {
                        "proposal_id": "inc_codex_unknown",
                        "workflow_type": "codex_unknown_workflow_smoke",
                        "action_lane": "toolchain_incubation",
                        "production_task_created": False,
                    },
                    "production_task_created": False,
                    "task_created": False,
                    "confirmation_created": False,
                    "task_creation_allowed": False,
                    "forbidden_actions": [
                        "confirmation_creation",
                        "production_task_creation",
                        "pipeline_runner_launch",
                    ],
                }
            return {
                "agent_run_id": "agent_run_456",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "safe_metadata": {},
                "project_id": 7,
            }
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "modality": "BOLD",
                    "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
                }
            ]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 1,
                            "modality": "BOLD",
                            "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
                        }
                    ],
                },
            }
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "bold_fmriprep_xcpd",
                "runtime_workflow_type": "bold_fmriprep_xcpd",
                "status": "completed",
            }
        if url.endswith("/tasks/114/events"):
            return {
                "status": "ok",
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "bold_fmriprep_xcpd",
                    "status": "completed",
                    "progress": 100,
                },
                "main_log": {"tail": "pipeline runner completed"},
                "remote_logs": [
                    {
                        "name": "fmriprep.log",
                        "source_stage": "fmriprep",
                        "size_bytes": 48,
                        "tail": "fMRIPrep completed",
                    }
                ],
                "events": [
                    {"type": "task.status", "status": "completed", "progress": 100},
                    {"type": "task.remote_log", "name": "fmriprep.log", "source_stage": "fmriprep", "size_bytes": 48},
                ],
            }
        if url.endswith("/tasks/114/observe-repair"):
                return {
                    "status": "ok",
                    "task_id": 114,
                    "policy": "read_only_observe_repair",
                    "auto_rerun_allowed": False,
                    "task_creation_allowed": False,
                    "production_task_created": False,
                    "forbidden_actions": ["auto_retry", "auto_rerun", "task_creation"],
                    "requires_preflight_before_retry": True,
                    "requires_human_confirmation_before_retry": True,
                "remote_logs": [
                    {"name": "fmriprep.log", "source_stage": "fmriprep", "size_bytes": 48},
                ],
                "repair_suggestions": [{"action": "review_remote_logs"}],
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [*native_artifacts, *report_manifest["artifacts"]],
                "omitted_artifacts": [],
            }
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="bold_fmriprep_xcpd", modality="BOLD")
        raise AssertionError(f"unexpected request: {url}")

    def fake_upload_nifti(base, project_id, path):
        assert base == "http://api.local"
        assert project_id == 7
        assert path == upload_file
        return {
            "series": {
                "id": 1,
                "project_id": 7,
                "modality": "BOLD",
                "sequence_label": "BOLD",
                "workflow_eligibility": _good_workflow_eligibility("bold_fmriprep_xcpd"),
            }
        }

    def fake_request_bytes(url):
        if url.endswith("/fmriprep/sub-01.html") or url.endswith("/reports/index.html"):
            return b"<html>report</html>", "text/html"
        if url.endswith("/xcpd/sub-01/figures/carpetplot.png") or url.endswith("/reports/t1_qc.png"):
            return b"\x89PNG\r\n\x1a\n", "image/png"
        if url.endswith("/reports/report_manifest.json"):
            return b'{"figures":[]}', "application/json"
        raise AssertionError(f"unexpected artifact byte request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)
    monkeypatch.setattr(smoke, "_request_bytes", fake_request_bytes)
    monkeypatch.setattr(smoke, "_upload_nifti", fake_upload_nifti)

    smoke.main(
                [
                    "--api-base",
                    "http://api.local",
                    "--require-model",
                    "--expected-model-wire-api",
                    "responses",
                    "--expected-model-provider-profile",
                    "rawchat",
                    "--require-model-tool-loop",
                    "--require-project-agent-context",
            "--require-agent-workflow-confirmation",
            "--require-agent-workflow-resume",
            "--require-agent-workflow-fingerprint-negative",
            "--require-unknown-workflow-incubation",
            "--require-deployment-identity",
            "--require-production-readiness",
            "--require-runtime-toolchain",
            "--deployment-id",
            "codex-f57a2ea-20260611T023456",
            "--min-documents",
            "60",
            "--min-chunks",
            "200",
                "--require-raw-source-policy",
                "--require-vendor-pointer-integrity",
                "--require-elasticsearch-hybrid-rag",
                "--require-real-evidence-ids",
            "--require-completed-upload",
            "--require-uploaded-series",
            "--upload-nifti-file",
            str(upload_file),
            "--require-completed-task",
            "--require-launched-task",
            "--require-task-events",
            "--require-observe-repair",
            "--launch-series-id",
            "1",
            "--launch-workflow-type",
            "bold_fmriprep_xcpd",
            "--require-launchability-matrix",
            "--require-container-native-qc",
            "--min-native-qc-images",
            "1",
            "--require-scientific-report-artifacts",
            "--min-scientific-report-images",
            "1",
            "--project-id",
            "7",
            "--upload-session-id",
            "22",
            "--task-id",
            "114",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["task_events_status"] == "passed"
    assert payload["task_events_event_types"] == ["task.remote_log", "task.status"]
    assert payload["task_events_remote_log_count"] == 1
    assert payload["task_events_remote_log_source_stages"] == ["fmriprep"]
    report = verifier.verify_acceptance_payload(payload)

    assert report["status"] == "passed"
    assert report["checked"]["launched_task_status"] == "passed"
    assert report["checked"]["task_events_status"] == "passed"
    assert report["checked"]["agent_workflow_confirmation_status"] == "passed"
    assert report["checked"]["agent_workflow_resume_status"] == "passed"
    assert report["checked"]["container_native_qc_status"] == "passed"
    assert report["checked"]["scientific_report_artifacts_status"] == "passed"


def test_smoke_remote_agent_require_task_events_rejects_unredacted_log_tail(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 1,
                    "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                }
            ]
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
            }
        if url.endswith("/tasks/114/events"):
            return {
                "status": "ok",
                "task": {
                    "id": 114,
                    "project_id": 7,
                    "series_id": 1,
                    "workflow_type": "t1_deepprep_anat_report",
                    "status": "completed",
                    "progress": 100,
                },
                "main_log": {"tail": r"completed under C:\srv\image_agent\projects\7"},
                "remote_logs": [
                    {"name": "deepprep.log", "source_stage": "deepprep", "size_bytes": 48, "tail": "completed"},
                ],
                "events": [
                    {"type": "task.status", "status": "completed", "progress": 100},
                    {"type": "task.remote_log", "name": "deepprep.log", "source_stage": "deepprep", "size_bytes": 48},
                ],
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(
            [
                "--api-base",
                "http://api.local",
                "--project-id",
                "7",
                "--task-id",
                "114",
                "--require-completed-task",
                "--require-task-events",
            ]
        )

    assert "task events main_log.tail leaked unsafe text" in str(exc.value)


def test_smoke_remote_agent_requires_observe_repair_read_only_evidence(monkeypatch, capsys):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114"):
            return {
                "id": 114,
                "project_id": 7,
                "series_id": 1,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
                "progress": 100,
            }
        if url.endswith("/tasks/114/observe-repair"):
            return {
                "status": "ok",
                "policy": "read_only_observe_repair",
                "task_id": 114,
                "task": {"id": 114, "status": "completed", "workflow_type": "t1_deepprep_anat_report"},
                "events": [{"type": "task.status", "status": "completed"}],
                "remote_logs": [{"name": "deepprep.log", "source_stage": "deepprep", "size_bytes": 48}],
                "main_log": {"tail": "redacted failure"},
                "result_summary_status": "ok",
                "repair_suggestions": [{"kind": "observe", "message": "Continue read-only observation."}],
                "auto_rerun_allowed": False,
                "task_creation_allowed": False,
                "forbidden_actions": ["auto_retry", "auto_rerun", "task_creation"],
                "production_task_created": False,
                "requires_preflight_before_retry": True,
                "requires_human_confirmation_before_retry": True,
            }
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_type="t1_deepprep_anat_report", modality="T1")
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--min-documents",
            "60",
            "--min-chunks",
            "200",
            "--require-completed-task",
            "--require-observe-repair",
            "--task-id",
            "114",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_observe_repair"] is True
    assert payload["observe_repair_status"] == "passed"
    assert payload["observe_repair_task_id"] == 114
    assert payload["observe_repair_policy"] == "read_only_observe_repair"
    assert payload["observe_repair_auto_rerun_allowed"] is False
    assert payload["observe_repair_task_creation_allowed"] is False
    assert payload["observe_repair_forbidden_actions"] == ["auto_retry", "auto_rerun", "task_creation"]
    assert payload["observe_repair_production_task_created"] is False
    assert payload["observe_repair_requires_preflight_before_retry"] is True
    assert payload["observe_repair_requires_human_confirmation_before_retry"] is True
    assert payload["observe_repair_repair_suggestion_count"] == 1


def test_smoke_remote_agent_requires_unknown_workflow_incubation_evidence(monkeypatch, capsys):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if url.endswith("/agent/model/status"):
            return {
                "configured": True,
                "provider": "rawchat",
                "provider_profile": "rawchat",
                "model": "gpt-5.5",
                "wire_api": "responses",
                "trust_env_proxy": False,
                "capabilities": {"model_tool_loop": True},
                "deployment": {"model_gateway_access": "direct"},
            }
        if base_response is not None:
            return base_response
        if url.endswith("/agent/runs"):
            message = payload.get("message") if isinstance(payload, dict) else ""
            if "codex_unknown_workflow_smoke" in message:
                return {
                    "agent_run_id": "agent_run_unknown",
                    "thread_id": None,
                    "status": "toolchain_proposed",
                    "action_lane": "toolchain_incubation",
                    "task_creation_allowed": False,
                    "forbidden_actions": ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"],
                    "production_task_created": False,
                    "proposed_toolchain": {
                        "proposal_id": "inc_codex_unknown",
                        "contract_version": "toolchain_proposal.v1",
                        "status": "draft",
                        "promotion_status": "blocked_by_gaps",
                        "task_creation_allowed": False,
                        "forbidden_actions": ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"],
                        "production_task_created": False,
                    },
                }
            return {
                "agent_run_id": "agent_run_123",
                "status": "answered",
                "intent": "answer_question",
                "selected_skill": "image-agent-operator",
                "model_gateway_access": "openai_sdk_gateway",
                "project_id": 7,
            }
        if url.endswith("/projects/7/series"):
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--require-model",
            "--require-project-agent-context",
            "--require-unknown-workflow-incubation",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["smoke_gate"]["require_unknown_workflow_incubation"] is True
    assert payload["unknown_workflow_incubation_status"] == "passed"
    assert payload["unknown_workflow_incubation"]["status"] == "toolchain_proposed"
    assert payload["unknown_workflow_incubation"]["action_lane"] == "toolchain_incubation"
    assert payload["unknown_workflow_incubation"]["proposal_id"] == "inc_codex_unknown"
    assert payload["unknown_workflow_incubation"]["thread_id"] is None
    assert payload["unknown_workflow_incubation"]["task_created"] is False
    assert payload["unknown_workflow_incubation"]["confirmation_created"] is False
    assert payload["unknown_workflow_incubation"]["task_creation_allowed"] is False
    assert payload["unknown_workflow_incubation"]["forbidden_actions"] == [
        "confirmation_creation",
        "production_task_creation",
        "pipeline_runner_launch",
    ]
    assert payload["unknown_workflow_incubation"]["production_task_created"] is False
    assert payload["unknown_workflow_incubation"]["proposal_production_task_created"] is False


def test_smoke_remote_agent_validates_project_series_and_task_artifact_contracts(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {
                "index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"},
                "vendor_raw_sources": {
                    "manifest_exists": True,
                    "missing_files": [],
                    "hash_mismatches": [],
                    "raw_sources_indexed": False,
                    "indexed_raw_sources": [],
                },
            }
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 3,
                    "modality": "DWI",
                    "workflow_eligibility": _good_workflow_eligibility("dwi_fast_gpu_dti"),
                }
            ]
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output(
                "reports/dti_metrics.json",
                preview_kind="json",
                content_type="application/json",
            )
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(
                output_path="reports/dti_metrics.json",
                output_content_type="application/json",
            )
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--task-id",
            "114",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["project_contract_status"] == "passed"
    assert payload["task_artifact_manifest_status"] == "passed"
    assert payload["task_result_summary_status"] == "passed"
    assert payload["task_result_summary"] == {
        "contract_version": "1.0",
        "task_id": 114,
        "workflow_type": "dwi_fast_gpu_dti",
        "workflow_metadata": _workflow_metadata("dwi_fast_gpu_dti"),
        "modality": "DWI",
        "feature_groups": ["dti_metrics"],
        "output_group_count": 1,
        "output_item_count": 1,
        "downloadable_output_count": 1,
        "downloadable_output_paths": ["reports/dti_metrics.json"],
        "downloadable_output_urls": ["/tasks/114/artifacts/reports/dti_metrics.json"],
        "provenance_keys": ["generated_from"],
    }
    assert payload["series_with_workflow_eligibility"] == 1
    assert payload["artifact_manifest_preview_kinds"] == ["json"]
    assert any(call[1].endswith("/projects/7/series") for call in calls)
    assert any(call[1].endswith("/tasks/114/artifact-manifest") for call in calls)
    assert any(call[1].endswith("/tasks/114/result-summary") for call in calls)


def test_smoke_remote_agent_rejects_result_summary_output_missing_from_artifact_manifest(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/other.json")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary()
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert "task result summary output missing from artifact manifest" in str(exc.value)


def test_smoke_remote_agent_rejects_result_summary_missing_workflow_metadata(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            return _task_result_summary(workflow_metadata=None)
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert "task result summary workflow_metadata missing" in str(exc.value)


def test_smoke_remote_agent_rejects_result_summary_non_agent_selectable_workflow_metadata(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return _artifact_manifest_with_result_summary_output("reports/index.html")
        if url.endswith("/tasks/114/result-summary"):
            metadata = _workflow_metadata()
            metadata["agent_selectable"] = False
            return _task_result_summary(workflow_metadata=metadata)
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert "task result summary workflow_metadata agent_selectable invalid" in str(exc.value)


def test_smoke_remote_agent_rejects_empty_task_artifact_manifest(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {"index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"}}
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": False},
                "artifacts": [],
                "omitted_artifacts": [],
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert "task artifact manifest has no artifacts" in str(exc.value)


def test_smoke_remote_agent_validates_dataset_inventory_workflow_eligibility(capsys, monkeypatch):
    smoke = _load_smoke_module()
    calls = []

    def fake_request(method, url, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/health"):
            return {"status": "ok", "app": "image_agent", "version": "0.2.0"}
        if url.endswith("/agent/model/status"):
            return {"configured": False, "provider": "OpenAI"}
        if url.endswith("/agent/rag/status"):
            return {"index": {"document_count": 72, "chunk_count": 260, "engine": "llama_index"}}
        if url.endswith("/agent/rag/rebuild"):
            return {"document_count": 72, "chunk_count": 260, "semantic_index": True}
        if url.endswith("/projects/7/series"):
            return [
                {
                    "id": 5,
                    "modality": "T1",
                    "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                }
            ]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "progress": 100,
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 5,
                            "modality": "T1",
                            "workflow_eligibility": _good_workflow_eligibility("t1_deepprep_anat_report"),
                        }
                    ],
                },
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    smoke.main(
        [
            "--api-base",
            "http://api.local",
            "--project-id",
            "7",
            "--upload-session-id",
            "22",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["upload_inventory_contract_status"] == "passed"
    assert payload["upload_inventory_status"] == "completed"
    assert payload["upload_inventory_series_with_workflow_eligibility"] == 1
    assert payload["upload_inventory_series_ids"] == [5]
    assert payload["upload_inventory_modalities"] == ["T1"]
    required_fields = [
        "display_name",
        "capability_summary",
        "workflow_family",
        "workflow_role",
        "pipeline_stages",
        "primary_outputs",
        "qc_outputs",
        "report_outputs",
        "limitations",
        "agent_selectable",
        "is_report_only",
    ]
    assert payload["project_workflow_eligibility_metadata_status"] == "passed"
    assert payload["project_workflow_eligibility_metadata_workflow_types"] == ["t1_deepprep_anat_report"]
    assert payload["project_workflow_eligibility_metadata_required_fields"] == required_fields
    assert payload["project_workflow_eligibility_metadata_item_count"] == 2
    assert payload["upload_inventory_workflow_eligibility_metadata_status"] == "passed"
    assert payload["upload_inventory_workflow_eligibility_metadata_workflow_types"] == ["t1_deepprep_anat_report"]
    assert payload["upload_inventory_workflow_eligibility_metadata_required_fields"] == required_fields
    assert payload["upload_inventory_workflow_eligibility_metadata_item_count"] == 2
    assert any(call[1].endswith("/projects/7/datasets/22/inventory") for call in calls)


def test_smoke_remote_agent_requires_project_id_for_upload_session(monkeypatch):
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--upload-session-id", "22"])

    assert "--upload-session-id requires --project-id" in str(exc.value)


def test_smoke_remote_agent_rejects_malformed_workflow_eligibility():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke._validate_project_series_contract(
            [
                {
                    "id": 3,
                    "modality": "DWI",
                    "workflow_eligibility": {
                        "production_task_created": False,
                        "runnable_workflows": [],
                        "blocked_workflows": [],
                    },
                }
            ]
        )

    assert "workflow_eligibility policy_version failed" in str(exc.value)


@pytest.mark.parametrize(
    ("workflow_entry", "expected_message"),
    [
        (
            {"workflow_type": "t1_deepprep_anat_report"},
            "runnable_workflows[0] workflow_metadata missing",
        ),
        (
            {
                "workflow_type": "t1_deepprep_anat_report",
                "workflow_metadata": _workflow_metadata("bold_fmriprep_xcpd_report"),
            },
            "runnable_workflows[0] workflow_metadata missing",
        ),
    ],
)
def test_smoke_remote_agent_rejects_workflow_eligibility_item_without_matching_metadata(
    workflow_entry,
    expected_message,
):
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke._validate_project_series_contract(
            [
                {
                    "id": 3,
                    "modality": "T1",
                    "workflow_eligibility": {
                        "policy_version": "workflow_eligibility_v1",
                        "production_task_created": False,
                        "runnable_workflows": [workflow_entry],
                        "blocked_workflows": [],
                    },
                }
            ]
        )

    assert expected_message in str(exc.value)


@pytest.mark.parametrize(
    ("metadata_override", "expected_message"),
    [
        ({"display_name": None}, "runnable_workflows[0] workflow_metadata display_name missing"),
        ({"capability_summary": None}, "runnable_workflows[0] workflow_metadata capability_summary missing"),
        ({"pipeline_stages": []}, "runnable_workflows[0] workflow_metadata pipeline_stages missing"),
        ({"primary_outputs": []}, "runnable_workflows[0] workflow_metadata primary_outputs missing"),
        ({"qc_outputs": []}, "runnable_workflows[0] workflow_metadata qc_outputs missing"),
        ({"report_outputs": []}, "runnable_workflows[0] workflow_metadata report_outputs missing"),
        ({"limitations": []}, "runnable_workflows[0] workflow_metadata limitations missing"),
        ({"is_report_only": True}, "runnable_workflows[0] workflow_metadata is_report_only invalid"),
        ({"agent_selectable": False}, "runnable_workflows[0] workflow_metadata agent_selectable invalid"),
    ],
)
def test_smoke_remote_agent_rejects_weak_workflow_eligibility_metadata(metadata_override, expected_message):
    smoke = _load_smoke_module()
    metadata = _workflow_metadata("t1_deepprep_anat_report")
    metadata.update(metadata_override)

    with pytest.raises(SystemExit) as exc:
        smoke._validate_project_series_contract(
            [
                {
                    "id": 3,
                    "modality": "T1",
                    "workflow_eligibility": {
                        "policy_version": "workflow_eligibility_v1",
                        "production_task_created": False,
                        "runnable_workflows": [
                            {
                                "workflow_type": "t1_deepprep_anat_report",
                                "workflow_metadata": metadata,
                            }
                        ],
                        "blocked_workflows": [],
                    },
                }
            ]
        )

    assert expected_message in str(exc.value)


def test_smoke_remote_agent_rejects_windows_style_unsafe_artifact_paths():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit) as exc:
        smoke._validate_task_artifact_manifest(
            {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": r"..\secret.txt",
                        "download_url": r"/tasks/114/artifacts/..\secret.txt",
                        "preview_kind": "download",
                        "content_type": "text/plain",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
            },
            114,
        )

    assert "relative_path is unsafe" in str(exc.value)


@pytest.mark.parametrize(
    ("argv", "series_payload", "inventory_payload", "expected_message"),
    [
        (
            ["--api-base", "http://api.local", "--project-id", "7"],
            [
                {"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()},
                {"id": 2, "modality": "DWI", "workflow_eligibility": None},
            ],
            None,
            "project series contract failed: workflow_eligibility missing",
        ),
        (
            ["--api-base", "http://api.local", "--project-id", "7", "--upload-session-id", "22"],
            [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}],
            {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [
                        {
                            "series_id": 3,
                            "modality": "DWI",
                            "workflow_eligibility": {
                                **_good_workflow_eligibility(),
                                "policy_version": "workflow_eligibility_v0",
                            },
                        }
                    ],
                },
            },
            "upload inventory contract failed: workflow_eligibility policy_version failed",
        ),
    ],
)
def test_smoke_remote_agent_rejects_bad_workflow_eligibility_via_remote_gates(
    monkeypatch,
    argv,
    series_payload,
    inventory_payload,
    expected_message,
):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/projects/7/series"):
            return series_payload
        if url.endswith("/projects/7/datasets/22/inventory"):
            return inventory_payload
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(argv)

    assert expected_message in str(exc.value)


@pytest.mark.parametrize(
    ("artifact_override", "expected_message"),
    [
        ({"relative_path": r"..\secret.txt", "download_url": r"/tasks/114/artifacts/..\secret.txt"}, "relative_path is unsafe"),
        ({"relative_path": "reports/../secret.txt", "download_url": "/tasks/114/artifacts/reports/../secret.txt"}, "relative_path is unsafe"),
        ({"relative_path": "C:/secret.txt", "download_url": "/tasks/114/artifacts/C:/secret.txt"}, "relative_path is unsafe"),
        ({"exists": False}, "artifact exists=false"),
        ({"exists": None}, "artifact exists=true missing"),
        ({"download_url": "/wrong/114/reports/index.html"}, "download_url mismatch"),
        ({"content_type": ""}, "content_type missing"),
        ({"size_bytes": 0}, "size_bytes missing"),
        ({"preview_kind": "svg"}, "preview_kind invalid"),
        ({"path": "/srv/image_agent/secret.txt"}, "leaked backend absolute path"),
        ({"absolute_path": "/srv/image_agent/secret.txt"}, "leaked backend absolute path"),
        ({"backend_path": r"C:\image_agent\secret.txt"}, "leaked backend absolute path"),
        ({"filesystem_path": "../secret.txt"}, "leaked backend absolute path"),
        ({"provenance": {"backend_path": "/srv/image_agent/secret.txt"}}, "leaked backend absolute path"),
        ({"provenance": {"script_path": "/srv/image_agent/scripts/run_qc.py"}}, "leaked backend absolute path"),
    ],
)
def test_smoke_remote_agent_rejects_bad_artifact_manifest_fields_via_task_gate(
    monkeypatch,
    artifact_override,
    expected_message,
):
    smoke = _load_smoke_module()
    artifact = {
        "relative_path": "reports/index.html",
        "download_url": "/tasks/114/artifacts/reports/index.html",
        "preview_kind": "html",
        "content_type": "text/html",
        "size_bytes": 12,
        "exists": True,
    }
    artifact.update(artifact_override)

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [artifact],
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert expected_message in str(exc.value)


def test_smoke_remote_agent_rejects_omitted_artifact_path_leakage_via_task_gate(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
                "omitted_artifacts": [{"reason": "unsupported", "backend_path": "/srv/image_agent/secret.txt"}],
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert "task artifact manifest omitted_artifacts leaked backend absolute path" in str(exc.value)


def test_smoke_remote_agent_rejects_omitted_artifact_relative_path_leakage_via_task_gate(monkeypatch):
    smoke = _load_smoke_module()

    def fake_request(method, url, payload=None):
        base_response = _good_remote_smoke_response(url)
        if base_response is not None:
            return base_response
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "result_summary": {"available": True},
                "artifacts": [
                    {
                        "relative_path": "reports/index.html",
                        "download_url": "/tasks/114/artifacts/reports/index.html",
                        "preview_kind": "html",
                        "content_type": "text/html",
                        "size_bytes": 12,
                        "exists": True,
                    }
                ],
                "omitted_artifacts": [{"reason": "outside", "relative_path": "/srv/image_agent/private/report.html"}],
            }
        raise AssertionError(f"unexpected request: {url}")

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(SystemExit) as exc:
        smoke.main(["--api-base", "http://api.local", "--task-id", "114"])

    assert "task artifact manifest omitted_artifacts leaked backend absolute path" in str(exc.value)


def test_smoke_remote_agent_accepts_quoted_artifact_download_url():
    smoke = _load_smoke_module()

    summary = smoke._validate_task_artifact_manifest(
        {
            "contract_version": "artifact_manifest_v1",
            "task_id": 114,
            "result_summary": {"available": True},
            "artifacts": [
                {
                    "relative_path": "reports/qc figure.html",
                    "download_url": "/tasks/114/artifacts/reports/qc%20figure.html",
                    "preview_kind": "html",
                    "content_type": "text/html",
                    "size_bytes": 12,
                    "exists": True,
                }
            ],
            "omitted_artifacts": [],
        },
        114,
    )

    assert summary["artifact_count"] == 1


def test_smoke_remote_agent_unsafe_text_check_does_not_flag_bids_task_or_mask_tokens():
    smoke = _load_smoke_module()

    assert smoke._contains_unredacted_unsafe_text("sub-01_task-rest_desc-summary_bold.html") is False
    assert smoke._contains_unredacted_unsafe_text("sub-01_desc-brain_mask.nii.gz") is False
    assert smoke._contains_unredacted_unsafe_text("Authorization: Bearer sk-real-secret-token") is True
