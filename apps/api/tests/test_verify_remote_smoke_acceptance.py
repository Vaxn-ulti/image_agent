import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


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
            "require_raw_source_policy": True,
            "require_vendor_pointer_integrity": True,
            "require_real_evidence_ids": True,
            "require_launchability_matrix": True,
            "require_container_native_qc": True,
            "min_native_qc_images": 1,
            "require_scientific_report_artifacts": True,
            "min_scientific_report_images": 1,
            "project_id": 7,
            "upload_session_id": 22,
            "task_id": 114,
        },
        "health": {"status": "ok", "app": "image_agent"},
        "deployment_identity_status": "passed",
        "deployment_identity": {
            "deployment_id": "codex-f57a2ea-20260611T023456",
            "health_app": "image_agent",
            "health_version": "0.2.0",
        },
        "model_status": {"configured": True, "provider": "OpenAI"},
        "model_smoke_status": "passed",
        "production_readiness_status": "passed",
        "production_readiness": {
            "blocking_reasons": [],
            "ready": True,
            "required": True,
            "status": "ready",
        },
        "agent_run_status": "answered",
        "agent_run_id": "agent_run_123",
        "intent": "answer_question",
        "selected_skill": "image-agent-operator",
        "remote_evidence_ids_status": "passed",
        "remote_evidence_ids": {"project_id": 7, "upload_session_id": 22, "task_id": 114},
        "rag_document_count": 72,
        "rag_chunk_count": 260,
        "rag_semantic_index": True,
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
        "upload_inventory_contract_status": "passed",
        "upload_inventory_series_with_workflow_eligibility": 1,
        "task_artifact_manifest_status": "passed",
        "artifact_manifest_artifact_count": 5,
        "artifact_manifest_preview_kinds": ["html", "image", "json"],
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
    assert report["checked"]["rag_vendor_pointer_integrity_status"] == "passed"
    assert report["checked"]["rag_vendor_coverage_catalog_status"] == "complete"
    assert report["checked"]["container_native_qc_status"] == "passed"
    assert report["checked"]["scientific_report_artifacts_status"] == "passed"


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
        ({"deployment_identity_status": "skipped"}, "deployment_identity_status must be passed"),
        ({"production_readiness_status": "blocked"}, "production_readiness_status must be passed"),
        ({"production_readiness": {"ready": False}}, "production_readiness.ready must be true"),
        ({"agent_run_id": "agent_run_123 C:/Users/A/private"}, "agent_run_id must be privacy-safe"),
        ({"selected_skill": "image-agent-operator sk-test-secret"}, "selected_skill must be privacy-safe"),
        ({"remote_evidence_ids_status": "skipped"}, "remote_evidence_ids_status must be passed"),
        ({"rag_launchability_query_source": "Answer mentions docs/rag/workflows/workflow_launchability_matrix.md"}, "launchability query source must cite workflow matrix"),
        ({"container_native_qc_served_urls": []}, "container_native_qc_served_urls must be non-empty"),
        ({"container_native_qc_official_source_ids": ["docs/rag/vendor/fake.md"]}, "container_native_qc_official_source_ids contains unsupported source"),
        ({"smoke_gate": {"require_real_evidence_ids": False}}, "smoke_gate.require_real_evidence_ids must be true"),
        ({"smoke_gate": {"require_deployment_identity": False}}, "smoke_gate.require_deployment_identity must be true"),
        ({"smoke_gate": {"require_production_readiness": False}}, "smoke_gate.require_production_readiness must be true"),
        ({"smoke_gate": {"deployment_id": "C:/srv/image_agent"}}, "deployment_id must be privacy-safe"),
        ({"smoke_gate": {"require_vendor_pointer_integrity": False}}, "smoke_gate.require_vendor_pointer_integrity must be true"),
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


def test_verify_remote_smoke_acceptance_cli_rejects_stale_report(tmp_path):
    verifier = _load_verifier_module()
    payload_path = tmp_path / "remote-smoke-acceptance.json"
    payload_path.write_text(json.dumps(_strict_smoke_payload()), encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        verifier.main([str(payload_path), "--max-age-hours", "24", "--now-utc", "2026-06-10T13:00:00Z"])

    assert "generated_at_utc is older than 24 hours" in str(exc.value)
