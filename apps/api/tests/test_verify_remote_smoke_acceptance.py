import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _strict_workflow_metadata(**overrides):
    metadata = {
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
    }
    metadata.update(overrides)
    return metadata


def _strict_workflow_metadata_without(*keys):
    metadata = _strict_workflow_metadata()
    for key in keys:
        metadata.pop(key, None)
    return metadata


WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS = [
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


def _load_verifier_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_remote_smoke_acceptance.py"
    spec = importlib.util.spec_from_file_location("verify_remote_smoke_acceptance", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _strict_smoke_payload():
    return {
        "generated_at_utc": "2026-06-08T12:00:00Z",
        "smoke_gate": {
            "api_base": "http://127.0.0.1:8000",
            "require_model": True,
            "require_deployment_identity": True,
            "deployment_id": "codex-f57a2ea-20260611T023456",
            "min_documents": 60,
            "min_chunks": 200,
            "require_production_readiness": True,
            "require_completed_task": True,
            "require_project_agent_context": True,
            "require_agent_workflow_confirmation": True,
            "require_agent_workflow_resume": True,
            "require_agent_workflow_fingerprint_negative": True,
            "require_unknown_workflow_incubation": True,
            "require_raw_source_policy": True,
            "require_vendor_pointer_integrity": True,
            "require_elasticsearch_hybrid_rag": True,
            "require_real_evidence_ids": True,
            "require_completed_upload": True,
            "require_uploaded_series": True,
            "require_launchability_matrix": True,
            "require_task_events": True,
            "require_observe_repair": True,
            "require_launched_task": True,
            "require_runtime_toolchain": True,
            "require_container_native_qc": True,
            "min_native_qc_images": 1,
            "require_scientific_report_artifacts": True,
            "min_scientific_report_images": 1,
            "expected_model_wire_api": "responses",
            "expected_model_provider_profile": "rawchat",
            "require_model_tool_loop": True,
            "project_id": 7,
            "upload_session_id": 22,
            "uploaded_series_id": 1,
            "task_id": 114,
        },
        "health": {"status": "ok", "app": "image_agent"},
        "deployment_identity_status": "passed",
        "deployment_identity": {
            "deployment_id": "codex-f57a2ea-20260611T023456",
            "health_app": "image_agent",
            "health_version": "0.2.0",
        },
        "model_status": {
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
        },
        "model_smoke_status": "passed",
        "production_readiness_status": "passed",
        "production_readiness": {
            "blocking_reasons": [],
            "ready": True,
            "required": True,
            "status": "ready",
        },
        "fast_launch_readiness_status": "pre_acceptance",
        "fast_launch_readiness": {
            "blocking_reasons": [
                "Strict remote acceptance evidence has not been verified for the upload-agent-workflow-result chain."
            ],
            "ready": False,
            "status": "blocked",
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
                "strict_remote_acceptance": {"status": "missing"},
                "rag_elasticsearch_hybrid": {
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
                },
            },
        },
        "runtime_toolchain_status": "passed",
        "runtime_toolchain": {
            "workflow_tool_execution": "deployment_server_local",
            "docker_runtime_host": "api_server",
            "docker_requires_sudo": True,
            "fs_license_exists": True,
            "workflow_count": 2,
            "available_workflow_count": 2,
            "required_workflow_type": "t1_deepprep_anat_report",
            "required_workflow_available": True,
            "unavailable_workflows": [],
            "workflow_types": ["bold_fmriprep_xcpd_report", "t1_deepprep_anat_report"],
        },
        "agent_run_status": "answered",
        "agent_run_id": "agent_run_123",
        "agent_model_gateway_status": "passed",
        "agent_model_gateway_access": "openai_sdk_gateway",
        "agent_model_transport_access": "direct",
        "agent_model_trust_env_proxy": False,
        "agent_safe_metadata": {},
        "agent_project_context_status": "passed",
        "agent_run_project_id": 7,
        "agent_workflow_confirmation_status": "passed",
        "agent_workflow_confirmation": {
            "agent_run_id": "agent_run_confirm",
            "thread_id": "agent_thread_confirm",
            "status": "confirmation_required",
            "intent": "run_workflow",
            "project_id": 7,
            "series_id": 1,
            "workflow_type": "t1_deepprep_anat_report",
            "workflow_metadata": _strict_workflow_metadata(),
            "selected_skill": "image-agent-workflow-runner",
            "production_task_created": False,
        },
        "agent_workflow_resume_status": "passed",
        "agent_workflow_resume": {
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
        },
        "agent_workflow_fingerprint_negative_status": "passed",
        "agent_workflow_fingerprint_negative": {
            "agent_run_id": "agent_run_tampered",
            "thread_id": "agent_thread_confirm",
            "status": "blocked",
            "production_task_created": False,
            "confirmation_gate": "fingerprint_mismatch",
            "task_created": False,
        },
        "unknown_workflow_incubation_status": "passed",
        "unknown_workflow_incubation": {
            "agent_run_id": "agent_run_unknown",
            "thread_id": "agent_thread_unknown",
            "status": "toolchain_proposed",
            "action_lane": "toolchain_incubation",
            "proposal_id": "inc_codex_unknown",
            "proposal_status": "draft",
            "proposal_contract_version": "toolchain_proposal.v1",
            "proposal_promotion_status": "blocked_by_gaps",
            "task_created": False,
            "confirmation_created": False,
            "task_creation_allowed": False,
            "forbidden_actions": ["confirmation_creation", "production_task_creation", "pipeline_runner_launch"],
            "production_task_created": False,
            "proposal_production_task_created": False,
        },
        "intent": "answer_question",
        "selected_skill": "image-agent-operator",
        "remote_evidence_ids_status": "passed",
        "remote_evidence_ids": {"project_id": 7, "upload_session_id": 22, "task_id": 114},
        "task_status_status": "passed",
        "task_status": {
            "project_id": 7,
            "series_id": 1,
            "status": "completed",
            "task_id": 114,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
        },
        "task_events_status": "passed",
        "task_events_task_id": 114,
        "task_events_event_types": ["task.remote_log", "task.status"],
        "task_events_status_event_status": "completed",
        "task_events_remote_log_count": 1,
        "task_events_remote_log_source_stages": ["deepprep"],
        "task_events_main_log_tail_present": True,
        "observe_repair_status": "passed",
        "observe_repair_task_id": 114,
        "observe_repair_policy": "read_only_observe_repair",
        "observe_repair_auto_rerun_allowed": False,
        "observe_repair_task_creation_allowed": False,
        "observe_repair_forbidden_actions": ["auto_retry", "auto_rerun", "task_creation"],
        "observe_repair_production_task_created": False,
        "observe_repair_requires_preflight_before_retry": True,
        "observe_repair_requires_human_confirmation_before_retry": True,
        "observe_repair_repair_suggestion_count": 1,
        "launched_task_status": "passed",
        "launched_task": {
            "initial_status": "queued",
            "project_id": 7,
            "series_id": 1,
            "task_id": 114,
            "workflow_type": "t1_deepprep_anat_report",
            "runtime_workflow_type": "t1_deepprep",
            "launch_source": "agent_workflow_resume",
        },
        "task_workflow_selection_status": "passed",
        "task_workflow_selection": {
            "series_id": 1,
            "workflow_type": "t1_deepprep_anat_report",
            "matched_runnable_workflow": True,
        },
        "rag_document_count": 72,
        "rag_chunk_count": 260,
        "rag_semantic_index": True,
        "rag_rebuild_elasticsearch_hybrid": {
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
        },
        "rag_elasticsearch_hybrid_status": "passed",
        "rag_elasticsearch_hybrid": {
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
            "official_rrf_source_present": True,
        },
        "rag_elasticsearch_hybrid_query_status": "passed",
        "rag_elasticsearch_hybrid_query_mode": "elasticsearch_hybrid",
        "rag_elasticsearch_hybrid_query_retrieval_source": "elasticsearch_hybrid",
        "rag_elasticsearch_hybrid_query_source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
        "rag_elasticsearch_hybrid_query_citation_count": 1,
        "rag_elasticsearch_hybrid_query_top_score": 12.5,
        "rag_elasticsearch_hybrid_query_index": "image_agent_rag",
        "rag_elasticsearch_hybrid_query_lexical_retriever": "standard",
        "rag_elasticsearch_hybrid_query_vector_retriever": "knn",
        "rag_elasticsearch_hybrid_query_dense_vector_field": "embedding",
        "rag_elasticsearch_hybrid_query_fusion": "rrf",
        "rag_elasticsearch_hybrid_query_dense_vector_dims": 1536,
        "rag_elasticsearch_hybrid_query_embedding_provider": "openai",
        "rag_elasticsearch_hybrid_query_embedding_model": "text-embedding-3-small",
        "rag_elasticsearch_hybrid_query_embedding_transport": "openai_compatible_http",
        "rag_elasticsearch_hybrid_query_embedding_endpoint_configured": True,
        "rag_elasticsearch_hybrid_query_embedding_production_ready": True,
        "rag_raw_sources": {
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
                    "complete": True,
                    "raw_source_ids": ["fmriprep_outputs"],
                    "source_urls": ["https://fmriprep.org/en/stable/outputs.html"],
                    "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_outputs.html"],
                    "source_types": ["official_docs"],
                    "manifest_backed": True,
                    "source_url_backed": True,
                }
                ,
                {
                    "vendor_doc": "xcp_d_official_outputs.md",
                    "complete": True,
                    "raw_source_ids": ["xcp_d_outputs"],
                    "source_urls": ["https://xcp-d.readthedocs.io/en/latest/outputs.html"],
                    "raw_files": ["docs/rag/vendor/raw-sources/xcp_d_outputs.html"],
                    "source_types": ["official_docs"],
                    "manifest_backed": True,
                    "source_url_backed": True,
                },
            ],
        },
        "rag_vendor_pointer_integrity_status": "passed",
        "rag_vendor_pointer_integrity_pointer_count": 35,
        "rag_vendor_pointer_integrity_issue_count": 0,
        "rag_vendor_pointer_integrity_referenced_vendor_docs": [
            "fmriprep_official_outputs.md",
            "xcp_d_official_outputs.md",
        ],
        "rag_vendor_pointer_integrity": {
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
        },
        "rag_vendor_coverage_catalog_status": "complete",
        "rag_vendor_coverage_catalog_vendor_doc_count": 2,
        "rag_vendor_coverage_catalog_complete_vendor_doc_count": 2,
        "rag_vendor_coverage_catalog_incomplete_vendor_doc_count": 0,
        "rag_vendor_coverage_catalog_raw_source_count": 2,
        "rag_vendor_coverage_catalog": {
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
        },
        "rag_launchability_matrix_status": "passed",
        "rag_launchability_matrix_source": "docs/rag/workflows/workflow_launchability_matrix.md",
        "rag_launchability_query_status": "passed",
        "rag_launchability_query_intent": "launchability",
        "rag_launchability_query_source": "docs/rag/workflows/workflow_launchability_matrix.md",
        "project_contract_status": "passed",
        "series_with_workflow_eligibility": 1,
        "project_workflow_eligibility_metadata_status": "passed",
        "project_workflow_eligibility_metadata_required_fields": WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS,
        "project_workflow_eligibility_metadata_workflow_types": ["t1_deepprep_anat_report"],
        "project_workflow_eligibility_metadata_item_count": 2,
        "upload_inventory_contract_status": "passed",
        "upload_inventory_completion_status": "passed",
        "upload_inventory_status": "completed",
        "upload_inventory_series_with_workflow_eligibility": 1,
        "upload_inventory_series_ids": [1],
        "upload_inventory_workflow_eligibility_metadata_status": "passed",
        "upload_inventory_workflow_eligibility_metadata_required_fields": WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS,
        "upload_inventory_workflow_eligibility_metadata_workflow_types": ["t1_deepprep_anat_report"],
        "upload_inventory_workflow_eligibility_metadata_item_count": 2,
        "uploaded_series_status": "passed",
        "uploaded_series": {
            "project_id": 7,
            "series_id": 1,
            "modality": "T1",
            "sequence_label": "T1w",
        },
        "task_artifact_manifest_status": "passed",
        "task_result_summary_status": "passed",
        "task_result_summary": {
            "contract_version": "1.0",
            "task_id": 114,
            "workflow_type": "t1_deepprep_anat_report",
            "workflow_metadata": _strict_workflow_metadata(),
            "modality": "T1",
            "feature_groups": ["anat"],
            "output_group_count": 1,
            "output_item_count": 1,
            "downloadable_output_count": 1,
            "downloadable_output_paths": ["reports/index.html"],
            "downloadable_output_urls": ["/tasks/114/artifacts/reports/index.html"],
            "provenance_keys": ["generated_from"],
        },
        "artifact_manifest_artifact_count": 5,
        "artifact_manifest_preview_kinds": ["html", "image", "json"],
        "artifact_manifest_relative_paths": [
            "fmriprep/sub-01.html",
            "xcpd/sub-01/figures/carpetplot.png",
            "reports/index.html",
            "reports/report_manifest.json",
            "reports/t1_qc.png",
        ],
        "artifact_manifest_download_urls": [
            "/tasks/114/artifacts/fmriprep/sub-01.html",
            "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
            "/tasks/114/artifacts/reports/index.html",
            "/tasks/114/artifacts/reports/report_manifest.json",
            "/tasks/114/artifacts/reports/t1_qc.png",
        ],
        "container_native_qc_status": "passed",
        "container_native_qc_artifact_count": 2,
        "container_native_qc_image_count": 1,
        "container_native_qc_relative_paths": ["fmriprep/sub-01.html", "xcpd/sub-01/figures/carpetplot.png"],
        "container_native_qc_served_urls": [
            "/tasks/114/artifacts/fmriprep/sub-01.html",
            "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
        ],
        "container_native_qc_artifacts": [
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
        ],
        "container_native_qc_official_source_ids": [
            "docs/rag/vendor/fmriprep_official_outputs.md",
            "docs/rag/vendor/xcp_d_official_outputs.md",
        ],
        "scientific_report_artifacts_status": "passed",
        "scientific_report_artifact_count": 3,
        "scientific_report_html_count": 1,
        "scientific_report_image_count": 1,
        "scientific_report_json_count": 1,
        "scientific_report_preview_kinds": ["html", "image", "json"],
        "scientific_report_relative_paths": [
            "reports/index.html",
            "reports/report_manifest.json",
            "reports/t1_qc.png",
        ],
        "scientific_report_served_urls": [
            "/tasks/114/artifacts/reports/index.html",
            "/tasks/114/artifacts/reports/report_manifest.json",
            "/tasks/114/artifacts/reports/t1_qc.png",
        ],
        "scientific_report_artifacts": [
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
        ],
    }


def test_verify_remote_smoke_acceptance_accepts_strict_payload():
    verifier = _load_verifier_module()

    report = verifier.verify_acceptance_payload(_strict_smoke_payload())

    assert report["status"] == "passed"
    assert report["summary"] == "status=passed"
    assert report["checked"]["model_smoke_status"] == "passed"
    assert report["checked"]["expected_model_wire_api"] == "responses"
    assert report["checked"]["model_wire_api"] == "responses"
    assert report["checked"]["expected_model_provider_profile"] == "rawchat"
    assert report["checked"]["model_provider_profile"] == "rawchat"
    assert report["checked"]["model_trust_env_proxy"] is False
    assert report["checked"]["model_gateway_access"] == "direct"
    assert report["checked"]["model_tool_loop"] is True
    assert report["checked"]["fast_launch_readiness_status"] == "pre_acceptance"
    assert report["checked"]["fast_launch_production_deployment_status"] == "passed"
    assert report["checked"]["fast_launch_production_deployment_required"] is True
    assert report["checked"]["fast_launch_production_deployment_ready"] is True
    assert report["checked"]["fast_launch_rag_elasticsearch_hybrid_status"] == "passed"
    assert report["checked"]["fast_launch_rag_elasticsearch_hybrid_mode"] == "connected"
    assert report["checked"]["fast_launch_rag_elasticsearch_hybrid_index"] == "image_agent_rag"
    assert report["checked"]["runtime_toolchain_status"] == "passed"
    assert report["checked"]["runtime_toolchain_workflow_tool_execution"] == "deployment_server_local"
    assert report["checked"]["runtime_toolchain_docker_runtime_host"] == "api_server"
    assert report["checked"]["runtime_toolchain_fs_license_exists"] is True
    assert report["checked"]["runtime_toolchain_required_workflow_type"] == "t1_deepprep_anat_report"
    assert report["checked"]["runtime_toolchain_required_workflow_available"] is True
    assert report["checked"]["agent_project_context_status"] == "passed"
    assert report["checked"]["agent_workflow_confirmation_status"] == "passed"
    assert report["checked"]["agent_workflow_confirmation_metadata_workflow_type"] == "t1_deepprep_anat_report"
    assert report["checked"]["agent_workflow_confirmation_metadata_runtime_workflow_type"] == "t1_deepprep"
    assert report["checked"]["agent_workflow_confirmation_metadata_agent_selectable"] is True
    assert report["checked"]["agent_workflow_confirmation_metadata_is_report_only"] is False
    assert report["checked"]["agent_workflow_resume_runtime_workflow_type"] == "t1_deepprep"
    assert report["checked"]["agent_workflow_fingerprint_negative_status"] == "passed"
    assert report["checked"]["agent_workflow_fingerprint_negative_confirmation_gate"] == "fingerprint_mismatch"
    assert report["checked"]["agent_workflow_fingerprint_negative_task_created"] is False
    assert report["checked"]["agent_workflow_fingerprint_negative_production_task_created"] is False
    assert report["checked"]["unknown_workflow_incubation_status"] == "passed"
    assert report["checked"]["unknown_workflow_incubation_action_lane"] == "toolchain_incubation"
    assert report["checked"]["unknown_workflow_incubation_task_created"] is False
    assert report["checked"]["unknown_workflow_incubation_confirmation_created"] is False
    assert report["checked"]["unknown_workflow_incubation_task_creation_allowed"] is False
    assert report["checked"]["unknown_workflow_incubation_forbidden_actions"] == [
        "confirmation_creation",
        "production_task_creation",
        "pipeline_runner_launch",
    ]
    assert report["checked"]["unknown_workflow_incubation_production_task_created"] is False
    assert report["checked"]["unknown_workflow_incubation_proposal_production_task_created"] is False
    assert report["checked"]["task_status_runtime_workflow_type"] == "t1_deepprep"
    assert report["checked"]["launched_task_runtime_workflow_type"] == "t1_deepprep"
    assert report["checked"]["launched_task_launch_source"] == "agent_workflow_resume"
    assert report["checked"]["observe_repair_requires_preflight_before_retry"] is True
    assert report["checked"]["observe_repair_requires_human_confirmation_before_retry"] is True
    assert report["checked"]["rag_vendor_pointer_integrity_status"] == "passed"
    assert report["checked"]["rag_elasticsearch_hybrid_mode"] == "connected"
    assert report["checked"]["rag_elasticsearch_hybrid_configured"] is True
    assert report["checked"]["rag_elasticsearch_hybrid_index"] == "image_agent_rag"
    assert report["checked"]["rag_elasticsearch_hybrid_indexed_chunk_count"] == 260
    assert report["checked"]["rag_elasticsearch_hybrid_dense_vector_dims"] == 1536
    assert report["checked"]["rag_elasticsearch_hybrid_error_absent"] is True
    assert report["checked"]["rag_elasticsearch_hybrid_embedding_error_absent"] is True
    assert report["checked"]["rag_elasticsearch_hybrid_embedding_provider"] == "openai"
    assert report["checked"]["rag_elasticsearch_hybrid_embedding_model"] == "text-embedding-3-small"
    assert report["checked"]["rag_elasticsearch_hybrid_embedding_transport"] == "openai_compatible_http"
    assert report["checked"]["rag_elasticsearch_hybrid_embedding_endpoint_configured"] is True
    assert report["checked"]["rag_elasticsearch_hybrid_embedding_production_ready"] is True
    assert report["checked"]["rag_elasticsearch_hybrid_official_rrf_source_present"] is True
    assert report["checked"]["launched_task_launch_source"] == "agent_workflow_resume"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_indexed_chunk_count"] == 260
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_configured"] is True
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_index"] == "image_agent_rag"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_error_absent"] is True
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_embedding_error_absent"] is True
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_lexical_retriever"] == "standard"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_vector_retriever"] == "knn"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_dense_vector_field"] == "embedding"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_embedding_provider"] == "openai"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_embedding_model"] == "text-embedding-3-small"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_embedding_transport"] == "openai_compatible_http"
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_embedding_endpoint_configured"] is True
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_embedding_production_ready"] is True
    assert report["checked"]["rag_rebuild_elasticsearch_hybrid_fusion"] == "rrf"
    assert report["checked"]["rag_elasticsearch_hybrid_query_mode"] == "elasticsearch_hybrid"
    assert report["checked"]["rag_elasticsearch_hybrid_query_retrieval_source"] == "elasticsearch_hybrid"
    assert report["checked"]["rag_elasticsearch_hybrid_query_source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"
    assert report["checked"]["rag_elasticsearch_hybrid_query_citation_count"] == 1
    assert report["checked"]["rag_elasticsearch_hybrid_query_top_score"] == 12.5
    assert report["checked"]["rag_elasticsearch_hybrid_query_index"] == "image_agent_rag"
    assert report["checked"]["rag_elasticsearch_hybrid_query_lexical_retriever"] == "standard"
    assert report["checked"]["rag_elasticsearch_hybrid_query_vector_retriever"] == "knn"
    assert report["checked"]["rag_elasticsearch_hybrid_query_dense_vector_field"] == "embedding"
    assert report["checked"]["rag_elasticsearch_hybrid_query_fusion"] == "rrf"
    assert report["checked"]["rag_elasticsearch_hybrid_query_embedding_model"] == "text-embedding-3-small"
    assert report["checked"]["rag_vendor_coverage_catalog_status"] == "complete"
    assert report["checked"]["container_native_qc_status"] == "passed"
    assert report["checked"]["scientific_report_artifacts_status"] == "passed"
    assert report["checked"]["task_status_status"] == "passed"
    assert report["checked"]["observe_repair_status"] == "passed"
    assert report["checked"]["observe_repair_policy"] == "read_only_observe_repair"
    assert report["checked"]["observe_repair_auto_rerun_allowed"] is False
    assert report["checked"]["observe_repair_production_task_created"] is False
    assert report["checked"]["task_workflow_selection_status"] == "passed"
    assert report["checked"]["task_result_summary_status"] == "passed"
    assert report["checked"]["task_result_summary_metadata_workflow_type"] == "t1_deepprep_anat_report"
    assert report["checked"]["task_result_summary_metadata_runtime_workflow_type"] == "t1_deepprep"
    assert report["checked"]["task_result_summary_metadata_agent_selectable"] is True
    assert report["checked"]["task_result_summary_metadata_is_report_only"] is False
    assert report["checked"]["uploaded_series_status"] == "passed"
    assert report["checked"]["project_workflow_eligibility_metadata_status"] == "passed"
    assert report["checked"]["project_workflow_eligibility_metadata_item_count"] == 2
    assert report["checked"]["project_workflow_eligibility_metadata_required_field_count"] == len(
        WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS
    )
    assert report["checked"]["project_workflow_eligibility_metadata_workflow_types"] == ["t1_deepprep_anat_report"]
    assert report["checked"]["project_workflow_eligibility_metadata_task_workflow_type_included"] is True
    assert report["checked"]["upload_inventory_workflow_eligibility_metadata_status"] == "passed"
    assert report["checked"]["upload_inventory_workflow_eligibility_metadata_item_count"] == 2
    assert report["checked"]["upload_inventory_workflow_eligibility_metadata_required_field_count"] == len(
        WORKFLOW_ELIGIBILITY_METADATA_REQUIRED_FIELDS
    )
    assert report["checked"]["upload_inventory_workflow_eligibility_metadata_workflow_types"] == [
        "t1_deepprep_anat_report"
    ]
    assert report["checked"]["upload_inventory_workflow_eligibility_metadata_task_workflow_type_included"] is True


def test_verify_remote_smoke_acceptance_accepts_runtime_toolchain_resolved_runtime_workflow():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["runtime_toolchain"]["required_runtime_workflow_type"] = "t1_deepprep"
    payload["runtime_toolchain"]["workflow_types"] = ["bold_fmriprep_xcpd_report", "t1_deepprep"]

    report = verifier.verify_acceptance_payload(payload)

    assert report["checked"]["runtime_toolchain_required_workflow_type"] == "t1_deepprep_anat_report"
    assert report["checked"]["runtime_toolchain_required_runtime_workflow_type"] == "t1_deepprep"
    assert report["checked"]["runtime_toolchain_required_workflow_available"] is True


def test_verify_remote_smoke_acceptance_accepts_unknown_workflow_incubation_without_thread_id():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["unknown_workflow_incubation"]["thread_id"] = None

    report = verifier.verify_acceptance_payload(payload)

    assert report["checked"]["unknown_workflow_incubation_status"] == "passed"
    assert report["checked"]["unknown_workflow_incubation_task_created"] is False
    assert report["checked"]["unknown_workflow_incubation_confirmation_created"] is False


def test_verify_remote_smoke_acceptance_rejects_stale_saved_evidence():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(
            payload,
            max_age_hours=24,
            now_utc=datetime(2026, 6, 10, 13, 0, tzinfo=timezone.utc),
        )

    assert "generated_at_utc is older than 24 hours" in str(exc.value)


@pytest.mark.parametrize(
    ("override", "expected_message"),
    [
        ({"generated_at_utc": ""}, "generated_at_utc must be an ISO-8601 UTC timestamp"),
        ({"generated_at_utc": "2026-06-08T12:00:00"}, "generated_at_utc must be timezone-aware"),
        ({"model_smoke_status": "skipped_missing_model_config"}, "model_smoke_status must be passed"),
        (
            {"model_status": {"wire_api": "chat_completions"}},
            "model_status.wire_api must match smoke_gate.expected_model_wire_api",
        ),
        (
            {"model_status": {"provider_profile": "deepseek"}},
            "model_status.provider_profile must match smoke_gate.expected_model_provider_profile",
        ),
        (
            {"model_status": {"capabilities": {"model_tool_loop": False}}},
            "model_status.capabilities.model_tool_loop must be true",
        ),
        (
            {"model_status": {"trust_env_proxy": True}},
            "rawchat model_status.trust_env_proxy must be false",
        ),
        (
            {"model_status": {"deployment": {"backend_runtime_mode": "remote", "model_gateway_access": "ssh_reverse_tunnel"}}},
            "rawchat model_status.deployment.model_gateway_access must be direct",
        ),
        (
            {"smoke_gate": {"expected_model_wire_api": "chat/completions"}},
            "expected_model_wire_api must be privacy-safe",
        ),
        (
            {"smoke_gate": {"expected_model_provider_profile": "rawchat/v1"}},
            "expected_model_provider_profile must be privacy-safe",
        ),
        (
            {"model_status": {"base_url": "https://sk-test-secret@example.invalid/v1"}},
            "model_status.base_url must not contain credentials",
        ),
        (
            {"model_status": {"api_key": "sk-test-secret"}},
            "model_status must not expose api_key",
        ),
        (
            {
                "model_status": {
                    "deployment": {
                        "reverse_tunnel_command": "ssh -N -R 18080:127.0.0.1:8080 user@remote"
                    }
                }
            },
            "model_status.deployment must not expose reverse_tunnel_command",
        ),
        (
            {"model_status": {"deployment": {"access_token": "sk-test-secret"}}},
            "model_status.deployment must not expose access_token",
        ),
        (
            {"model_status": {"gateway_diagnostics": {"authorization": "Bearer secret-value"}}},
            "model_status.gateway_diagnostics must not expose authorization",
        ),
        ({"deployment_identity_status": "skipped"}, "deployment_identity_status must be passed"),
        ({"production_readiness_status": "blocked"}, "production_readiness_status must be passed"),
        ({"production_readiness": {"ready": False}}, "production_readiness.ready must be true"),
        ({"smoke_gate": {"require_runtime_toolchain": False}}, "smoke_gate.require_runtime_toolchain must be true"),
        ({"runtime_toolchain_status": "skipped"}, "runtime_toolchain_status must be passed"),
        ({"runtime_toolchain": None}, "runtime_toolchain must be present"),
        (
            {"runtime_toolchain": {"workflow_tool_execution": "external_worker"}},
            "runtime_toolchain.workflow_tool_execution must be deployment_server_local",
        ),
        (
            {"runtime_toolchain": {"docker_runtime_host": "worker"}},
            "runtime_toolchain.docker_runtime_host must be api_server",
        ),
        (
            {"runtime_toolchain": {"fs_license_exists": False}},
            "runtime_toolchain.fs_license_exists must be true",
        ),
        (
            {"runtime_toolchain": {"required_workflow_available": False}},
            "runtime_toolchain.required_workflow_available must be true",
        ),
        (
            {"runtime_toolchain": {"required_workflow_type": "dwi_fast_gpu_dti"}},
            "runtime_toolchain.required_workflow_type must match task_status.workflow_type",
        ),
        (
            {"runtime_toolchain": {"fs_license_path": "C:/Users/A/license.txt"}},
            "runtime_toolchain must not expose fs_license_path",
        ),
        ({"agent_run_id": "agent_run_123 C:/Users/A/private"}, "agent_run_id must be privacy-safe"),
        ({"agent_model_gateway_status": "fallback"}, "agent_model_gateway_status must be passed"),
        ({"agent_model_gateway_access": None}, "agent_model_gateway_access must be privacy-safe"),
        (
            {"agent_model_transport_access": "ssh_reverse_tunnel"},
            "agent_model_transport_access must be direct for rawchat direct acceptance",
        ),
        (
            {"agent_model_trust_env_proxy": True},
            "agent_model_trust_env_proxy must be false for rawchat direct acceptance",
        ),
        (
            {"agent_safe_metadata": {"fallback_reason": "model_gateway_unconfigured"}},
            "agent_safe_metadata must not report model_gateway_unconfigured",
        ),
        ({"agent_project_context_status": "skipped"}, "agent_project_context_status must be passed"),
        ({"agent_run_project_id": None}, "agent_run_project_id must match smoke_gate.project_id"),
        ({"agent_workflow_confirmation_status": "skipped"}, "agent_workflow_confirmation_status must be passed"),
        (
            {"agent_workflow_confirmation": {"status": "answered"}},
            "agent_workflow_confirmation.status must be confirmation_required",
        ),
        (
            {"agent_workflow_confirmation": {"production_task_created": True}},
            "agent_workflow_confirmation.production_task_created must be false",
        ),
        (
            {"agent_workflow_confirmation": {"workflow_type": "dwi_fast_gpu_dti"}},
            "agent_workflow_confirmation.workflow_type must match task_status.workflow_type",
        ),
        (
            {"agent_workflow_confirmation": {"workflow_metadata": None}},
            "agent_workflow_confirmation.workflow_metadata must be present",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(
                        workflow_type="T1 DeepPrep anatomical processing, QC, and report"
                    )
                }
            },
            "agent_workflow_confirmation.workflow_metadata.workflow_type must match workflow_type",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(display_name="t1_deepprep_anat_report")
                }
            },
            "agent_workflow_confirmation.workflow_metadata.display_name must not equal workflow_type",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(is_report_only=True)
                }
            },
            "agent_workflow_confirmation.workflow_metadata.is_report_only must be false for strict production launch evidence",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(agent_selectable=False)
                }
            },
            "agent_workflow_confirmation.workflow_metadata.agent_selectable must be true for strict production launch evidence",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata_without("agent_selectable")
                }
            },
            "agent_workflow_confirmation.workflow_metadata.agent_selectable must be true for strict production launch evidence",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata_without("capability_summary")
                }
            },
            "agent_workflow_confirmation.workflow_metadata.capability_summary must be present",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata_without("pipeline_stages")
                }
            },
            "agent_workflow_confirmation.workflow_metadata.pipeline_stages must be present",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(primary_outputs=[])
                }
            },
            "agent_workflow_confirmation.workflow_metadata.primary_outputs must be present",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(qc_outputs=[])
                }
            },
            "agent_workflow_confirmation.workflow_metadata.qc_outputs must be present",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(report_outputs=[])
                }
            },
            "agent_workflow_confirmation.workflow_metadata.report_outputs must be present",
        ),
        (
            {
                "agent_workflow_confirmation": {
                    "workflow_metadata": _strict_workflow_metadata(limitations=[])
                }
            },
            "agent_workflow_confirmation.workflow_metadata.limitations must be present",
        ),
        (
            {"smoke_gate": {"require_agent_workflow_confirmation": False}},
            "smoke_gate.require_agent_workflow_confirmation must be true",
        ),
        ({"agent_workflow_resume_status": "skipped"}, "agent_workflow_resume_status must be passed"),
        (
            {"agent_workflow_resume": {"status": "answered"}},
            "agent_workflow_resume.status must be task_created",
        ),
        (
            {"agent_workflow_resume": {"production_task_created": False}},
            "agent_workflow_resume.production_task_created must be true",
        ),
        (
            {"agent_workflow_resume": {"confirmation_gate": "fingerprint_mismatch"}},
            "agent_workflow_resume.confirmation_gate must be fingerprint_verified",
        ),
        (
            {"smoke_gate": {"require_agent_workflow_resume": False}},
            "smoke_gate.require_agent_workflow_resume must be true",
        ),
        (
            {"smoke_gate": {"require_agent_workflow_fingerprint_negative": False}},
            "smoke_gate.require_agent_workflow_fingerprint_negative must be true",
        ),
        (
            {"agent_workflow_fingerprint_negative_status": "skipped"},
            "agent_workflow_fingerprint_negative_status must be passed",
        ),
        (
            {"agent_workflow_fingerprint_negative": {"status": "task_created"}},
            "agent_workflow_fingerprint_negative.status must be blocked",
        ),
        (
            {"agent_workflow_fingerprint_negative": {"production_task_created": True}},
            "agent_workflow_fingerprint_negative.production_task_created must be false",
        ),
        (
            {"agent_workflow_fingerprint_negative": {"confirmation_gate": "fingerprint_verified"}},
            "agent_workflow_fingerprint_negative.confirmation_gate must be fingerprint_mismatch",
        ),
        (
            {"agent_workflow_fingerprint_negative": {"task_created": True}},
            "agent_workflow_fingerprint_negative.task_created must be false",
        ),
        (
            {"smoke_gate": {"require_unknown_workflow_incubation": False}},
            "smoke_gate.require_unknown_workflow_incubation must be true",
        ),
        (
            {"unknown_workflow_incubation_status": "skipped"},
            "unknown_workflow_incubation_status must be passed",
        ),
        (
            {"unknown_workflow_incubation": {"status": "confirmation_required"}},
            "unknown_workflow_incubation.status must be toolchain_proposed",
        ),
        (
            {"unknown_workflow_incubation": {"action_lane": "production_task"}},
            "unknown_workflow_incubation.action_lane must be toolchain_incubation",
        ),
        (
            {"unknown_workflow_incubation": {"task_created": True}},
            "unknown_workflow_incubation.task_created must be false",
        ),
        (
            {"unknown_workflow_incubation": {"confirmation_created": True}},
            "unknown_workflow_incubation.confirmation_created must be false",
        ),
        (
            {"unknown_workflow_incubation": {"task_creation_allowed": True}},
            "unknown_workflow_incubation.task_creation_allowed must be false",
        ),
        (
            {"unknown_workflow_incubation": {"forbidden_actions": ["production_task_creation"]}},
            "unknown_workflow_incubation.forbidden_actions must include confirmation_creation, production_task_creation, and pipeline_runner_launch",
        ),
        (
            {"unknown_workflow_incubation": {"production_task_created": True}},
            "unknown_workflow_incubation.production_task_created must be false",
        ),
        (
            {"unknown_workflow_incubation": {"proposal_production_task_created": True}},
            "unknown_workflow_incubation.proposal_production_task_created must be false",
        ),
        (
            {"unknown_workflow_incubation": {"proposal_id": "C:/private/proposal"}},
            "unknown_workflow_incubation.proposal_id must be privacy-safe",
        ),
        ({"selected_skill": "image-agent-operator sk-test-secret"}, "selected_skill must be privacy-safe"),
        ({"remote_evidence_ids_status": "skipped"}, "remote_evidence_ids_status must be passed"),
        ({"upload_inventory_completion_status": "skipped"}, "upload_inventory_completion_status must be passed"),
        ({"upload_inventory_status": "running"}, "upload_inventory_status must be completed"),
        ({"upload_inventory_series_ids": []}, "upload_inventory_series_ids must include task_status.series_id"),
        ({"upload_inventory_series_ids": [2]}, "upload_inventory_series_ids must include task_status.series_id"),
        ({"project_workflow_eligibility_metadata_status": "skipped"}, "project_workflow_eligibility_metadata_status must be passed"),
        (
            {"project_workflow_eligibility_metadata_required_fields": ["display_name"]},
            "project_workflow_eligibility_metadata_required_fields must include workflow metadata required fields",
        ),
        (
            {"project_workflow_eligibility_metadata_workflow_types": ["bold_fmriprep_xcpd_report"]},
            "project_workflow_eligibility_metadata_workflow_types must include task_status.workflow_type",
        ),
        ({"upload_inventory_workflow_eligibility_metadata_status": "skipped"}, "upload_inventory_workflow_eligibility_metadata_status must be passed"),
        (
            {"upload_inventory_workflow_eligibility_metadata_required_fields": ["display_name"]},
            "upload_inventory_workflow_eligibility_metadata_required_fields must include workflow metadata required fields",
        ),
        (
            {"upload_inventory_workflow_eligibility_metadata_workflow_types": ["bold_fmriprep_xcpd_report"]},
            "upload_inventory_workflow_eligibility_metadata_workflow_types must include task_status.workflow_type",
        ),
        ({"uploaded_series_status": "skipped"}, "uploaded_series_status must be passed"),
        ({"uploaded_series": {"series_id": 2}}, "uploaded_series.series_id must match task_status.series_id"),
        ({"uploaded_series": {"project_id": 8}}, "uploaded_series.project_id must match smoke_gate.project_id"),
        ({"task_status_status": "skipped"}, "task_status_status must be passed"),
        ({"task_status": {"status": "running"}}, "task_status.status must be completed"),
        ({"task_status": {"task_id": 115}}, "task_status.task_id must match smoke_gate.task_id"),
        ({"task_status": {"runtime_workflow_type": None}}, "task_status.runtime_workflow_type must be present"),
        (
            {"task_status": {"runtime_workflow_type": "t1_deepprep_validate"}},
            "task_status.runtime_workflow_type must match launched_task.runtime_workflow_type",
        ),
        (
            {"agent_workflow_resume": {"runtime_workflow_type": None}},
            "agent_workflow_resume.runtime_workflow_type must be present",
        ),
        (
            {"agent_workflow_resume": {"runtime_workflow_type": "t1_deepprep_validate"}},
            "agent_workflow_resume.runtime_workflow_type must match launched_task.runtime_workflow_type",
        ),
        ({"launched_task_status": "skipped"}, "launched_task_status must be passed"),
        ({"launched_task": {"task_id": 115}}, "launched_task.task_id must match smoke_gate.task_id"),
        ({"launched_task": {"series_id": 2}}, "launched_task.series_id must match task_status.series_id"),
        ({"launched_task": {"workflow_type": "dwi_fast_gpu_dti"}}, "launched_task.workflow_type must match task_status.workflow_type"),
        ({"launched_task": {"project_id": 8}}, "launched_task.project_id must match smoke_gate.project_id"),
        (
            {"launched_task": {"launch_source": "direct_series_run"}},
            "launched_task.launch_source must be agent_workflow_resume",
        ),
        ({"task_result_summary_status": "skipped"}, "task_result_summary_status must be passed"),
        ({"task_result_summary": {"task_id": 115}}, "task_result_summary.task_id must match smoke_gate.task_id"),
        ({"task_result_summary": {"workflow_type": "dwi_fast_gpu_dti"}}, "task_result_summary.workflow_type must match task_status.workflow_type"),
        ({"task_result_summary": {"workflow_metadata": None}}, "task_result_summary.workflow_metadata must be present"),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata(workflow_type="dwi_fast_gpu_dti")}},
            "task_result_summary.workflow_metadata.workflow_type must match workflow_type",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata(runtime_workflow_type="t1_deepprep_validate")}},
            "task_result_summary.workflow_metadata.runtime_workflow_type must match task_status.runtime_workflow_type",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata(display_name="t1_deepprep_anat_report")}},
            "task_result_summary.workflow_metadata.display_name must not equal workflow_type",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata_without("capability_summary")}},
            "task_result_summary.workflow_metadata.capability_summary must be present",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata(primary_outputs=[])}},
            "task_result_summary.workflow_metadata.primary_outputs must be present",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata(is_report_only=True)}},
            "task_result_summary.workflow_metadata.is_report_only must be false for strict production launch evidence",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata(agent_selectable=False)}},
            "task_result_summary.workflow_metadata.agent_selectable must be true for strict production launch evidence",
        ),
        (
            {"task_result_summary": {"workflow_metadata": _strict_workflow_metadata_without("agent_selectable")}},
            "task_result_summary.workflow_metadata.agent_selectable must be true for strict production launch evidence",
        ),
        ({"task_result_summary": {"output_item_count": 0}}, "task_result_summary.output_item_count must be greater than zero"),
        ({"task_result_summary": {"downloadable_output_count": 0}}, "task_result_summary.downloadable_output_count must be greater than zero"),
        ({"task_result_summary": {"downloadable_output_paths": []}}, "task_result_summary.downloadable_output_paths must match downloadable_output_count"),
        ({"task_result_summary": {"downloadable_output_paths": ["C:/private/report.html"]}}, "task_result_summary.downloadable_output_paths entries must be safe relative paths"),
        ({"task_result_summary": {"downloadable_output_urls": ["/tasks/114/artifacts/wrong.html"]}}, "task_result_summary.downloadable_output_urls entries must match task artifact routes"),
        ({"artifact_manifest_relative_paths": []}, "artifact_manifest_relative_paths must be non-empty"),
        ({"artifact_manifest_relative_paths": ["reports/other.html"]}, "task_result_summary downloadable outputs must be present in artifact_manifest"),
        ({"artifact_manifest_download_urls": ["/tasks/114/artifacts/reports/other.html"]}, "task_result_summary downloadable outputs must be present in artifact_manifest"),
        ({"task_result_summary": {"provenance_keys": []}}, "task_result_summary.provenance_keys must be non-empty"),
        ({"task_workflow_selection_status": "skipped"}, "task_workflow_selection_status must be passed"),
        ({"task_workflow_selection": {"matched_runnable_workflow": False}}, "task_workflow_selection.matched_runnable_workflow must be true"),
        ({"task_workflow_selection": {"workflow_type": "bold_fmriprep_xcpd"}}, "task_workflow_selection.workflow_type must match task_status.workflow_type"),
        ({"task_workflow_selection": {"series_id": 2}}, "task_workflow_selection.series_id must match task_status.series_id"),
        ({"rag_launchability_query_source": "Answer mentions docs/rag/workflows/workflow_launchability_matrix.md"}, "launchability query source must cite workflow matrix"),
        ({"container_native_qc_served_urls": []}, "container_native_qc_served_urls must be non-empty"),
        ({"container_native_qc_official_source_ids": ["docs/rag/vendor/fake.md"]}, "container_native_qc_official_source_ids contains unsupported source"),
        ({"smoke_gate": {"require_real_evidence_ids": False}}, "smoke_gate.require_real_evidence_ids must be true"),
        ({"smoke_gate": {"require_completed_upload": False}}, "smoke_gate.require_completed_upload must be true"),
        ({"smoke_gate": {"require_launched_task": False}}, "smoke_gate.require_launched_task must be true"),
        ({"smoke_gate": {"require_deployment_identity": False}}, "smoke_gate.require_deployment_identity must be true"),
        ({"smoke_gate": {"require_production_readiness": False}}, "smoke_gate.require_production_readiness must be true"),
        ({"fast_launch_readiness_status": "skipped"}, "fast_launch_readiness_status must be passed or pre_acceptance"),
        ({"fast_launch_readiness": {"ready": True}}, "fast_launch_readiness.ready must be false before acceptance"),
        ({"fast_launch_readiness": {"blocking_reasons": []}}, "fast_launch_readiness.blocking_reasons must explain missing strict remote acceptance evidence"),
        (
            {
                "fast_launch_readiness": {
                    "checks": {
                        "rag_elasticsearch_hybrid": {
                            "status": "blocked",
                            "mode": "local_contract",
                        }
                    }
                }
            },
            "fast_launch_readiness.checks.rag_elasticsearch_hybrid.status must be passed",
        ),
        ({"smoke_gate": {"require_completed_task": False}}, "smoke_gate.require_completed_task must be true"),
        ({"smoke_gate": {"require_task_events": False}}, "smoke_gate.require_task_events must be true"),
        ({"task_events_status": "skipped"}, "task_events_status must be passed"),
        ({"task_events_task_id": 115}, "task_events_task_id must match smoke_gate.task_id"),
        ({"task_events_event_types": ["task.status"]}, "task_events_event_types must include task.remote_log"),
        ({"task_events_status_event_status": "running"}, "task_events_status_event_status must be completed"),
        ({"task_events_remote_log_count": 0}, "task_events_remote_log_count must be greater than zero"),
        ({"smoke_gate": {"require_observe_repair": False}}, "smoke_gate.require_observe_repair must be true"),
        ({"observe_repair_status": "skipped"}, "observe_repair_status must be passed"),
        ({"observe_repair_task_id": 115}, "observe_repair_task_id must match smoke_gate.task_id"),
        ({"observe_repair_policy": "auto_repair"}, "observe_repair_policy must be read_only_observe_repair"),
        ({"observe_repair_auto_rerun_allowed": True}, "observe_repair_auto_rerun_allowed must be false"),
        ({"observe_repair_task_creation_allowed": True}, "observe_repair_task_creation_allowed must be false"),
        (
            {"observe_repair_forbidden_actions": ["auto_retry", "auto_rerun"]},
            "observe_repair_forbidden_actions must include auto_retry, auto_rerun, and task_creation",
        ),
        ({"observe_repair_production_task_created": True}, "observe_repair_production_task_created must be false"),
        (
            {"observe_repair_requires_preflight_before_retry": False},
            "observe_repair_requires_preflight_before_retry must be true",
        ),
        (
            {"observe_repair_requires_human_confirmation_before_retry": False},
            "observe_repair_requires_human_confirmation_before_retry must be true",
        ),
        ({"smoke_gate": {"require_project_agent_context": False}}, "smoke_gate.require_project_agent_context must be true"),
        ({"task_status": {"workflow_type": "t1_deepprep_mock"}}, "strict deployment acceptance cannot use debug-only workflow"),
        ({"launched_task": {"workflow_type": "t1_deepprep_mock"}}, "strict deployment acceptance cannot use debug-only workflow"),
        ({"agent_workflow_confirmation": {"workflow_type": "t1_deepprep_mock"}}, "strict deployment acceptance cannot use debug-only workflow"),
        (
            {"agent_workflow_confirmation": {"workflow_metadata": _strict_workflow_metadata(runtime_workflow_type="t1_deepprep_validate")}},
            "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type must match launched_task.runtime_workflow_type",
        ),
        ({"launched_task": {"runtime_workflow_type": None}}, "launched_task.runtime_workflow_type must be present"),
        ({"smoke_gate": {"deployment_id": "C:/srv/image_agent"}}, "deployment_id must be privacy-safe"),
        ({"smoke_gate": {"require_vendor_pointer_integrity": False}}, "smoke_gate.require_vendor_pointer_integrity must be true"),
        ({"smoke_gate": {"require_elasticsearch_hybrid_rag": False}}, "smoke_gate.require_elasticsearch_hybrid_rag must be true"),
        ({"rag_elasticsearch_hybrid_status": "skipped"}, "rag_elasticsearch_hybrid_status must be passed"),
        ({"rag_rebuild_elasticsearch_hybrid": None}, "rag_rebuild_elasticsearch_hybrid must be present"),
        ({"rag_rebuild_elasticsearch_hybrid": {"indexed_chunk_count": 259}}, "rag_rebuild_elasticsearch_hybrid.indexed_chunk_count must match status"),
        ({"rag_elasticsearch_hybrid": {"configured": False}}, "rag_elasticsearch_hybrid.configured must be true"),
        ({"rag_elasticsearch_hybrid": {"persisted": False}}, "rag_elasticsearch_hybrid.persisted must be true"),
        ({"rag_elasticsearch_hybrid": {"mode": "local_contract"}}, "rag_elasticsearch_hybrid.mode must be connected"),
        ({"rag_elasticsearch_hybrid": {"index": "C:/private/image_agent_rag"}}, "rag_elasticsearch_hybrid.index must be privacy-safe"),
        ({"rag_rebuild_elasticsearch_hybrid": {"index": "other_index"}}, "rag_rebuild_elasticsearch_hybrid.index must match status"),
        ({"rag_elasticsearch_hybrid": {"indexed_chunk_count": 0}}, "rag_elasticsearch_hybrid.indexed_chunk_count must be greater than zero"),
        ({"rag_elasticsearch_hybrid": {"dense_vector_dims": 0}}, "rag_elasticsearch_hybrid.dense_vector_dims must be greater than zero"),
        ({"rag_rebuild_elasticsearch_hybrid": {"dense_vector_dims": 768}}, "rag_rebuild_elasticsearch_hybrid.dense_vector_dims must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"lexical_retriever": "match"}}, "rag_rebuild_elasticsearch_hybrid.lexical_retriever must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"vector_retriever": "dense_vector"}}, "rag_rebuild_elasticsearch_hybrid.vector_retriever must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"dense_vector_field": "vector"}}, "rag_rebuild_elasticsearch_hybrid.dense_vector_field must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"fusion": "dbsf"}}, "rag_rebuild_elasticsearch_hybrid.fusion must match status"),
        ({"rag_elasticsearch_hybrid": {"error": "[redacted-secret] connection refused"}}, "rag_elasticsearch_hybrid.error must be absent"),
        ({"rag_elasticsearch_hybrid": {"fusion": "dbsf"}}, "rag_elasticsearch_hybrid.fusion must be rrf"),
        ({"rag_elasticsearch_hybrid": {"embedding_provider": "local_hashing"}}, "rag_elasticsearch_hybrid.embedding_provider must be production configured"),
        ({"rag_elasticsearch_hybrid": {"embedding_provider": "local-token-hash-v1"}}, "rag_elasticsearch_hybrid.embedding_provider must be production configured"),
        ({"rag_elasticsearch_hybrid": {"embedding_provider": None}}, "rag_elasticsearch_hybrid.embedding_provider must be production configured"),
        ({"rag_elasticsearch_hybrid": {"embedding_model": ""}}, "rag_elasticsearch_hybrid.embedding_model must be present"),
        ({"rag_elasticsearch_hybrid": {"embedding_transport": ""}}, "rag_elasticsearch_hybrid.embedding_transport must be present"),
        ({"rag_elasticsearch_hybrid": {"embedding_transport": "local"}}, "rag_elasticsearch_hybrid.embedding_transport must be production-safe"),
        ({"rag_rebuild_elasticsearch_hybrid": {"embedding_model": "text-embedding-3-large"}}, "rag_rebuild_elasticsearch_hybrid.embedding_model must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"embedding_transport": "sdk"}}, "rag_rebuild_elasticsearch_hybrid.embedding_transport must match status"),
        ({"rag_elasticsearch_hybrid": {"embedding_endpoint_configured": False}}, "rag_elasticsearch_hybrid.embedding_endpoint_configured must be true"),
        ({"rag_elasticsearch_hybrid": {"embedding_endpoint_configured": None}}, "rag_elasticsearch_hybrid.embedding_endpoint_configured must be true"),
        ({"rag_rebuild_elasticsearch_hybrid": {"embedding_endpoint_configured": False}}, "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"embedding_endpoint_configured": None}}, "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured must match status"),
        ({"rag_elasticsearch_hybrid": {"embedding_production_ready": False}}, "rag_elasticsearch_hybrid.embedding_production_ready must be true"),
        ({"rag_elasticsearch_hybrid": {"embedding_error": "[redacted-secret]"}}, "rag_elasticsearch_hybrid.embedding_error must be absent"),
        ({"rag_rebuild_elasticsearch_hybrid": {"embedding_provider": "local_hashing"}}, "rag_rebuild_elasticsearch_hybrid.embedding_provider must match status"),
        ({"rag_rebuild_elasticsearch_hybrid": {"embedding_error": "[redacted-secret]"}}, "rag_rebuild_elasticsearch_hybrid.embedding_error must be absent"),
        ({"rag_elasticsearch_hybrid": {"official_rrf_source_present": False}}, "rag_elasticsearch_hybrid.official_rrf_source_present must be true"),
        (
            {
                "rag_elasticsearch_hybrid": {
                    "official_rrf_source_present": True,
                    "official_sources": [
                        "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                        "https://internal.example.local/private-rag-notes",
                    ],
                }
            },
            "rag_elasticsearch_hybrid.official_sources must not be saved",
        ),
        ({"rag_elasticsearch_hybrid_query_status": "skipped"}, "rag_elasticsearch_hybrid_query_status must be passed"),
        ({"rag_elasticsearch_hybrid_query_mode": "elasticsearch_hybrid_fallback"}, "rag_elasticsearch_hybrid_query_mode must be elasticsearch_hybrid"),
        ({"rag_elasticsearch_hybrid_query_retrieval_source": "persistent_index"}, "rag_elasticsearch_hybrid_query_retrieval_source must be elasticsearch_hybrid"),
        ({"rag_elasticsearch_hybrid_query_source": "docs/rag/workflows/workflow_launchability_matrix.md"}, "rag_elasticsearch_hybrid_query_source must cite the Elasticsearch hybrid contract"),
        ({"rag_elasticsearch_hybrid_query_citation_count": 0}, "rag_elasticsearch_hybrid_query_citation_count must be greater than zero"),
        ({"rag_elasticsearch_hybrid_query_top_score": 0}, "rag_elasticsearch_hybrid_query_top_score must be greater than zero"),
        ({"rag_elasticsearch_hybrid_query_index": "other_index"}, "rag_elasticsearch_hybrid_query_index must match status"),
        ({"rag_elasticsearch_hybrid_query_lexical_retriever": "match"}, "rag_elasticsearch_hybrid_query_lexical_retriever must match status"),
        ({"rag_elasticsearch_hybrid_query_vector_retriever": "dense_vector"}, "rag_elasticsearch_hybrid_query_vector_retriever must match status"),
        ({"rag_elasticsearch_hybrid_query_dense_vector_field": "vector"}, "rag_elasticsearch_hybrid_query_dense_vector_field must match status"),
        ({"rag_elasticsearch_hybrid_query_fusion": "dbsf"}, "rag_elasticsearch_hybrid_query_fusion must match status"),
        ({"rag_elasticsearch_hybrid_query_dense_vector_dims": 768}, "rag_elasticsearch_hybrid_query_dense_vector_dims must match status"),
        ({"rag_elasticsearch_hybrid_query_embedding_model": "text-embedding-3-large"}, "rag_elasticsearch_hybrid_query_embedding_model must match status"),
        ({"rag_elasticsearch_hybrid_query_embedding_provider": "local_hashing"}, "rag_elasticsearch_hybrid_query_embedding_provider must match status"),
        ({"rag_elasticsearch_hybrid_query_embedding_transport": "sdk"}, "rag_elasticsearch_hybrid_query_embedding_transport must match status"),
        ({"rag_elasticsearch_hybrid_query_embedding_endpoint_configured": False}, "rag_elasticsearch_hybrid_query_embedding_endpoint_configured must match status"),
        ({"rag_elasticsearch_hybrid_query_embedding_production_ready": False}, "rag_elasticsearch_hybrid_query_embedding_production_ready must match status"),
        ({"smoke_gate": {"require_scientific_report_artifacts": False}}, "smoke_gate.require_scientific_report_artifacts must be true"),
        ({"rag_document_count": True}, "rag_document_count must be an integer"),
        ({"smoke_gate": {"project_id": ""}, "remote_evidence_ids": {"project_id": ""}}, "smoke_gate.project_id must be a positive integer"),
        ({"smoke_gate": {"task_id": 0}, "remote_evidence_ids": {"task_id": 0}}, "smoke_gate.task_id must be a positive integer"),
        ({"rag_raw_sources": {"source_count": 0}}, "rag_raw_sources.source_count must be greater than zero"),
        ({"rag_raw_sources": {"vendor_doc_count": 0}}, "rag_raw_sources.vendor_doc_count must be greater than zero"),
        ({"rag_raw_sources": {"manifest_schema_version": None}}, "rag_raw_sources.manifest_schema_version must be present"),
        ({"rag_vendor_pointer_integrity_status": "skipped"}, "rag_vendor_pointer_integrity_status must be passed"),
        ({"rag_vendor_pointer_integrity_pointer_count": 0}, "rag_vendor_pointer_integrity_pointer_count must be greater than zero"),
        ({"rag_vendor_pointer_integrity_issue_count": 1}, "rag_vendor_pointer_integrity_issue_count must be zero"),
        ({"rag_vendor_pointer_integrity_referenced_vendor_docs": []}, "rag_vendor_pointer_integrity_referenced_vendor_docs must be non-empty"),
        ({"rag_vendor_coverage_catalog_status": "issues"}, "rag_vendor_coverage_catalog_status must be complete"),
        ({"rag_vendor_coverage_catalog_vendor_doc_count": 0}, "rag_vendor_coverage_catalog_vendor_doc_count must be greater than zero"),
        ({"rag_vendor_coverage_catalog_complete_vendor_doc_count": 0}, "rag_vendor_coverage_catalog_complete_vendor_doc_count must be greater than zero"),
        ({"rag_vendor_coverage_catalog_incomplete_vendor_doc_count": 1}, "rag_vendor_coverage_catalog_incomplete_vendor_doc_count must be zero"),
        ({"rag_vendor_coverage_catalog_raw_source_count": 0}, "rag_vendor_coverage_catalog_raw_source_count must be greater than zero"),
        ({"rag_vendor_coverage_catalog": {"pointer_count": 99}}, "rag_vendor_coverage_catalog.pointer_count must match pointer integrity summary"),
        ({"rag_raw_sources": {"source_count": 99}}, "rag_vendor_coverage_catalog.raw_source_count must match rag_raw_sources.source_count"),
        ({"container_native_qc_artifact_count": 99}, "container_native_qc_artifact_count must match container_native_qc_artifacts"),
        ({"container_native_qc_artifacts": []}, "container_native_qc_artifacts must be non-empty"),
        ({"scientific_report_artifacts_status": "skipped"}, "scientific_report_artifacts_status must be passed"),
        ({"scientific_report_artifact_count": 99}, "scientific_report_artifact_count must match scientific_report_artifacts"),
        ({"scientific_report_artifacts": []}, "scientific_report_artifacts must be non-empty"),
        ({"scientific_report_image_count": 0}, "scientific_report_image_count below smoke gate minimum"),
        ({"scientific_report_relative_paths": ["reports/other.html"]}, "scientific_report_relative_paths must match scientific_report_artifacts"),
        ({"scientific_report_served_urls": []}, "scientific_report_served_urls must be non-empty"),
        (
            {
                "scientific_report_served_urls": [
                    "/tasks/114/artifacts/reports/index.html",
                    "/tasks/114/artifacts/reports/report_manifest.json",
                    "/tasks/114/artifacts/reports/t1_qc.png",
                    "/tasks/114/artifacts/reports/extra.png",
                ]
            },
            "scientific_report_served_urls must match scientific_report_artifacts",
        ),
        ({"scientific_report_preview_kinds": ["download"]}, "scientific_report_preview_kinds must match scientific_report_artifacts"),
    ],
)
def test_verify_remote_smoke_acceptance_rejects_weak_evidence(override, expected_message):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key].update(value)
        else:
            payload[key] = value

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert expected_message in str(exc.value)


def test_verify_remote_smoke_acceptance_rejects_raw_official_sources_in_saved_rag_summaries():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["rag_before"] = {
        "engine": "elasticsearch_hybrid",
        "hybrid_search": {
            "official_rrf_source_present": True,
            "official_sources": [
                "https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion",
                "https://internal.example.local/private-rag-notes",
            ],
        },
    }

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    message = str(exc.value)
    assert "rag_before.hybrid_search.official_sources must not be saved" in message
    assert "internal.example.local" not in message


def test_verify_remote_smoke_acceptance_rejects_pre_acceptance_with_strict_acceptance_passed():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["fast_launch_readiness"]["checks"]["strict_remote_acceptance"]["status"] = "passed"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert "fast_launch_readiness.checks.strict_remote_acceptance.status must be missing before acceptance" in str(exc.value)


def test_verify_remote_smoke_acceptance_requires_fast_launch_production_deployment_gate():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["fast_launch_readiness"]["checks"].pop("production_deployment")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(
            payload,
            max_age_hours=24,
            now_utc=datetime(2026, 6, 8, 12, 30, tzinfo=timezone.utc),
        )

    assert "fast_launch_readiness.checks.production_deployment must be present" in str(exc.value)


@pytest.mark.parametrize(
    ("artifact_index", "artifact_override", "expected_message"),
    [
        (0, {"native_artifact": True}, "scientific_report_artifacts native_artifact must be false"),
        (0, {"artifact_origin": "container_output"}, "scientific_report_artifacts artifact_origin must be generated_from_result_summary"),
        (
            0,
            {"provenance": {"generated_from": "result_summary", "replaces_native_qc": True}},
            "scientific_report_artifacts provenance.replaces_native_qc must be false",
        ),
        (0, {"relative_path": "C:/tmp/report.html"}, "scientific_report_artifacts relative_path is unsafe"),
        (0, {"relative_path": r"reports\index.html"}, "scientific_report_artifacts relative_path is unsafe"),
        (0, {"download_url": ""}, "scientific_report_artifacts download_url must be non-empty"),
        (0, {"content_type": "image/png"}, "scientific_report_artifacts html content_type must be text/html"),
        (2, {"content_type": "text/html"}, "scientific_report_artifacts image content_type must be image/"),
        (1, {"content_type": "text/html"}, "scientific_report_artifacts json content_type must be application/json"),
    ],
)
def test_verify_remote_smoke_acceptance_rejects_bad_scientific_report_artifact(
    artifact_index,
    artifact_override,
    expected_message,
):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["scientific_report_artifacts"][artifact_index].update(artifact_override)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert expected_message in str(exc.value)


@pytest.mark.parametrize(
    ("artifact_override", "expected_message"),
    [
        ({"relative_path": "C:/tmp/native.html"}, "container_native_qc_artifacts relative_path is unsafe"),
        ({"relative_path": r"xcpd\sub-01.html"}, "container_native_qc_artifacts relative_path is unsafe"),
        ({"relative_path": "xcpd/../secret.html"}, "container_native_qc_artifacts relative_path is unsafe"),
        (
            {"relative_path": "xcpd/sub-01.html", "download_url": "/tasks/114/artifacts/wrong.html"},
            "container_native_qc_artifacts download_url mismatch",
        ),
        ({"content_type": ""}, "container_native_qc_artifacts content_type must be non-empty"),
        ({"preview_kind": "download"}, "container_native_qc_artifacts preview_kind must be html or image"),
        (
            {"preview_kind": "html", "content_type": "image/png"},
            "container_native_qc_artifacts html content_type must be text/html",
        ),
        (
            {"preview_kind": "image", "content_type": "text/html"},
            "container_native_qc_artifacts image content_type must be image/",
        ),
        (
            {"official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"]},
            "container_native_qc_artifacts provenance.official_source_ids must match official_source_ids",
        ),
        ({"artifact_origin": "generated_from_result_summary"}, "container_native_qc_artifacts artifact_origin must be container_output"),
        ({"native_artifact": False}, "container_native_qc_artifacts native_artifact must be true"),
        (
            {"provenance": {"generated_from": "result_summary", "replaces_native_qc": False}},
            "container_native_qc_artifacts provenance.generated_from must be container_native_qc",
        ),
        (
            {"provenance": {"generated_from": "container_native_qc", "replaces_native_qc": True}},
            "container_native_qc_artifacts provenance.replaces_native_qc must be false",
        ),
        (
            {
                "provenance": {
                    "generated_from": "container_native_qc",
                    "replaces_native_qc": False,
                    "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
                }
            },
            "container_native_qc_artifacts provenance.official_source_ids must match official_source_ids",
        ),
    ],
)
def test_verify_remote_smoke_acceptance_rejects_bad_container_native_qc_artifact(
    artifact_override,
    expected_message,
):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["container_native_qc_artifacts"][1].update(artifact_override)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert expected_message in str(exc.value)


def test_verify_remote_smoke_acceptance_rejects_reports_path_container_native_qc_artifact():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    artifact = payload["container_native_qc_artifacts"][1]
    artifact["relative_path"] = "reports/fake_native.png"
    artifact["download_url"] = "/tasks/114/artifacts/reports/fake_native.png"
    payload["container_native_qc_relative_paths"][1] = "reports/fake_native.png"
    payload["container_native_qc_served_urls"][1] = "/tasks/114/artifacts/reports/fake_native.png"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert "container_native_qc_artifacts reports paths must be scientific report artifacts" in str(exc.value)


def test_verify_remote_smoke_acceptance_rejects_incomplete_curated_sources():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["rag_raw_sources"]["curated_sources"][0]["raw_files"] = []

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert "curated_sources entries must be complete with raw_source_ids, source_urls, and raw_files" in str(exc.value)


@pytest.mark.parametrize(
    ("identity_override", "expected_message"),
    [
        ({"deployment_id": "other-release"}, "deployment_identity.deployment_id must match smoke_gate.deployment_id"),
        ({"deployment_id": "/home/yyf/project/image_agent"}, "deployment_id must be privacy-safe"),
        ({"health_app": "wrong_app"}, "deployment_identity.health_app must be image_agent"),
        ({"health_version": ""}, "deployment_identity.health_version must be present"),
        ({"health_version": "/home/yyf/project/image_agent/apps/api"}, "deployment_identity.health_version must be privacy-safe"),
    ],
)
def test_verify_remote_smoke_acceptance_rejects_bad_deployment_identity(
    identity_override,
    expected_message,
):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["deployment_identity"].update(identity_override)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert expected_message in str(exc.value)


def test_verify_remote_smoke_acceptance_rejects_unexpected_health_version():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["smoke_gate"]["expected_health_version"] = "codex-new-release"
    payload["deployment_identity"]["health_version"] = "old-release"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert "deployment_identity.health_version must match smoke_gate.expected_health_version" in str(exc.value)


def test_verify_remote_smoke_acceptance_rejects_weak_curated_source_pointer_metadata():
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["rag_raw_sources"]["curated_sources"][0]["manifest_backed"] = False

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert "curated_sources entries must be manifest-backed and source-url-backed" in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (
            lambda payload: payload["rag_vendor_coverage_catalog"]["vendors"].append(
                {
                    "vendor_doc": "extra_vendor.md",
                    "vendor_path": "docs/rag/vendor/extra_vendor.md",
                    "complete": True,
                    "manifest_backed": True,
                    "source_url_backed": True,
                    "raw_source_count": 1,
                    "source_url_count": 1,
                    "source_types": ["official_docs"],
                    "referenced_by": ["docs/rag/workflows/example.md"],
                    "raw_source_ids": ["extra_vendor"],
                }
            ),
            "rag_vendor_coverage_catalog.vendors must match rag_raw_sources.curated_sources",
        ),
        (
            lambda payload: payload["rag_raw_sources"]["curated_sources"].append(
                {
                    "vendor_doc": "extra_vendor.md",
                    "complete": True,
                    "raw_source_ids": ["extra_vendor"],
                    "source_urls": ["https://example.org/extra"],
                    "raw_files": ["docs/rag/vendor/raw-sources/extra_vendor.html"],
                    "source_types": ["official_docs"],
                    "manifest_backed": True,
                    "source_url_backed": True,
                }
            ),
            "rag_raw_sources.vendor_doc_count must match curated_sources",
        ),
        (
            lambda payload: payload["rag_vendor_coverage_catalog"]["vendors"].append(
                {**payload["rag_vendor_coverage_catalog"]["vendors"][0]}
            ),
            "rag_vendor_coverage_catalog.vendors vendor_doc values must be unique",
        ),
        (
            lambda payload: payload["rag_raw_sources"]["curated_sources"].append(
                {**payload["rag_raw_sources"]["curated_sources"][0]}
            ),
            "curated_sources vendor_doc values must be unique",
        ),
        (
            lambda payload: payload["rag_vendor_coverage_catalog"]["vendors"][0].update(
                {"raw_source_ids": ["other_raw_source"]}
            ),
            "rag_vendor_coverage_catalog raw_source_ids must match curated_sources",
        ),
        (
            lambda payload: payload["rag_vendor_coverage_catalog"]["vendors"][0].update(
                {"raw_source_count": 99}
            ),
            "rag_vendor_coverage_catalog raw_source_count must match curated_sources",
        ),
        (
            lambda payload: payload["rag_vendor_coverage_catalog"]["vendors"][0].update(
                {"source_url_count": 99}
            ),
            "rag_vendor_coverage_catalog source_url_count must match curated_sources",
        ),
        (
            lambda payload: payload["rag_vendor_coverage_catalog"]["vendors"][0].update(
                {"source_types": ["community_wiki"]}
            ),
            "rag_vendor_coverage_catalog source_types must match curated_sources",
        ),
        (
            lambda payload: payload["rag_raw_sources"]["curated_sources"][0].update(
                {"vendor_doc": "nested/vendor.md"}
            ),
            "curated_sources vendor_doc must be a file name",
        ),
        (
            lambda payload: payload["rag_raw_sources"].update({"vendor_doc_count": 99}),
            "rag_raw_sources.vendor_doc_count must match curated_sources",
        ),
    ],
)
def test_verify_remote_smoke_acceptance_rejects_vendor_catalog_curated_source_drift(
    mutate,
    expected_message,
):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    mutate(payload)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert expected_message in str(exc.value)


@pytest.mark.parametrize(
    ("catalog_override", "expected_message"),
    [
        ({"manifest_path": "C:/Users/A/private/manifest.json"}, "rag_vendor_coverage_catalog must not expose manifest_path"),
        ({"persist_dir": "C:/Users/A/private/.rag_index"}, "rag_vendor_coverage_catalog must not expose persist_dir"),
        ({"vendors": []}, "rag_vendor_coverage_catalog.vendors must be non-empty"),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "vendor_path": "C:/private/doc.md"}]},
            "rag_vendor_coverage_catalog vendor_path must be repo-relative",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "raw_snapshots": [{"id": "raw"}]}]},
            "rag_vendor_coverage_catalog vendors must not expose raw_snapshots",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "raw_files": ["docs/rag/vendor/raw-sources/fmriprep.html"]}]},
            "rag_vendor_coverage_catalog vendors must not expose raw_files",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "sha256": "abc"}]},
            "rag_vendor_coverage_catalog vendors must not expose sha256",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "absolute_path": "/srv/image_agent/doc.md"}]},
            "rag_vendor_coverage_catalog vendors must not expose absolute_path",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "backend_path": "/srv/image_agent/doc.md"}]},
            "rag_vendor_coverage_catalog vendors must not expose backend_path",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "vendor_path": "docs/rag/vendor/raw-sources/fmriprep.html"}]},
            "rag_vendor_coverage_catalog vendor_path must be repo-relative",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "vendor_path": r"docs\rag\vendor\fmriprep_official_outputs.md"}]},
            "rag_vendor_coverage_catalog vendor_path must be repo-relative",
        ),
        (
            {"vendors": [{"vendor_doc": "fmriprep_official_outputs.md", "referenced_by": ["docs/rag/workflows/../secret.md"]}]},
            "rag_vendor_coverage_catalog vendors referenced_by must contain repo-relative docs",
        ),
    ],
)
def test_verify_remote_smoke_acceptance_rejects_leaky_vendor_coverage_catalog(
    catalog_override,
    expected_message,
):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    if "vendors" in catalog_override and catalog_override["vendors"]:
        payload["rag_vendor_coverage_catalog"]["vendors"][0].update(catalog_override["vendors"][0])
    elif "vendors" in catalog_override:
        payload["rag_vendor_coverage_catalog"].update(catalog_override)
    else:
        payload["rag_vendor_coverage_catalog"].update(catalog_override)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_acceptance_payload(payload)

    assert expected_message in str(exc.value)


def test_verify_remote_smoke_acceptance_cli_prints_passed_report(tmp_path, capsys):
    verifier = _load_verifier_module()
    payload_path = tmp_path / "remote-smoke-acceptance.json"
    payload_path.write_text(json.dumps(_strict_smoke_payload()), encoding="utf-8")

    verifier.main([str(payload_path), "--max-age-hours", "24", "--now-utc", "2026-06-08T13:00:00Z"])

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["summary"] == "status=passed"
    assert report["source_json"] == str(payload_path)
    assert report["checked"]["max_age_hours"] == 24.0
    assert report["checked"]["generated_at_utc"] == "2026-06-08T12:00:00+00:00"


def test_verify_remote_smoke_acceptance_cli_can_emit_fast_launch_env(tmp_path, capsys):
    verifier = _load_verifier_module()
    payload_path = tmp_path / "remote-smoke-acceptance.json"
    payload_path.write_text(json.dumps(_strict_smoke_payload()), encoding="utf-8")

    verifier.main([
        str(payload_path),
        "--max-age-hours",
        "24",
        "--now-utc",
        "2026-06-08T12:30:00Z",
        "--emit-fast-launch-env",
    ])

    assert capsys.readouterr().out.splitlines() == [
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed",
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID=codex-f57a2ea-20260611T023456",
    ]


def test_verify_remote_smoke_acceptance_cli_env_export_rejects_unsafe_deployment_id(tmp_path):
    verifier = _load_verifier_module()
    payload = _strict_smoke_payload()
    payload["smoke_gate"]["deployment_id"] = "release/with/slash"
    payload["deployment_identity"]["deployment_id"] = "release/with/slash"
    payload_path = tmp_path / "remote-smoke-acceptance.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        verifier.main([str(payload_path), "--emit-fast-launch-env"])

    assert "deployment_id must be privacy-safe" in str(exc.value)


def test_verify_remote_smoke_acceptance_cli_rejects_stale_report(tmp_path):
    verifier = _load_verifier_module()
    payload_path = tmp_path / "remote-smoke-acceptance.json"
    payload_path.write_text(json.dumps(_strict_smoke_payload()), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        verifier.main([str(payload_path), "--max-age-hours", "24", "--now-utc", "2026-06-10T13:00:00Z"])

    assert "generated_at_utc is older than 24 hours" in str(exc.value)
