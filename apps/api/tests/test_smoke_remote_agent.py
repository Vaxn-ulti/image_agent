import importlib.util
import json
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


def _good_workflow_eligibility():
    return {
        "policy_version": "workflow_eligibility_v1",
        "production_task_created": False,
        "runnable_workflows": [{"workflow_type": "t1_deepprep_anat_report"}],
        "blocked_workflows": [],
    }


def _complete_vendor_raw_sources(**overrides):
    payload = {
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
                "vendor_doc": "fmriprep_official_container_usage.md",
                "raw_source_ids": ["fmriprep_usage"],
                "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
                "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_usage.html"],
                "source_types": ["official_docs"],
                "manifest_backed": True,
                "source_url_backed": True,
                "complete": True,
            }
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
                "provider": "OpenAI",
                "base_url": "https://sk-test-secret@example.invalid/v1",
                "api_key": "sk-test-secret",
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
            }
        raise AssertionError(f"unexpected request: {url}")

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
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["health"]["app"] == "image_agent"
    assert payload["model_smoke_status"] == "passed"
    assert payload["model_status"]["configured"] is True
    assert payload["model_status"]["provider"] == "OpenAI"
    assert "api_key" not in payload["model_status"]
    assert "sk-test-secret" not in json.dumps(payload["model_status"])
    assert payload["model_status"]["base_url"] == "https://example.invalid/v1"
    assert payload["agent_run_id"] == "agent_run_123"
    assert payload["agent_run_status"] == "answered"
    assert payload["intent"] == "answer_question"
    assert payload["agent_intent"] == "answer_question"
    assert payload["selected_skill"] == "image-agent-operator"
    assert payload["rag_vendor_pointer_integrity_status"] == "passed"
    assert calls[0][1].endswith("/health")


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
            return [{"id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}]
        if url.endswith("/projects/7/datasets/22/inventory"):
            return {
                "upload_session_id": 22,
                "status": "completed",
                "inventory": {
                    "inventory_status": "completed",
                    "series": [{"series_id": 1, "modality": "T1", "workflow_eligibility": _good_workflow_eligibility()}],
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
            "official_source_ids": ["docs/rag/vendor/fmriprep_official_outputs.md"],
        },
        {
            "relative_path": "xcpd/sub-01/figures/carpetplot.png",
            "download_url": "/tasks/114/artifacts/xcpd/sub-01/figures/carpetplot.png",
            "content_type": "image/png",
            "preview_kind": "image",
            "official_source_ids": ["docs/rag/vendor/xcp_d_official_outputs.md"],
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
                    "engine": "llama_index",
                    "indexed_sources": ["docs/rag/workflows/workflow_launchability_matrix.md"],
                },
            }
        if url.endswith("/agent/rag/query"):
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
                    "engine": "llama_index",
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
        "require_deployment_identity": True,
        "deployment_id": "codex-f57a2ea-20260611T023456",
        "min_documents": 60,
        "min_chunks": 200,
        "require_raw_source_policy": True,
        "require_vendor_pointer_integrity": True,
        "require_real_evidence_ids": False,
        "require_launchability_matrix": False,
        "require_container_native_qc": False,
        "min_native_qc_images": 0,
        "require_scientific_report_artifacts": False,
        "min_scientific_report_images": 0,
        "project_id": None,
        "task_id": None,
        "upload_session_id": None,
    }
    assert artifact_payload["deployment_identity_status"] == "passed"
    assert artifact_payload["deployment_identity"] == {
        "deployment_id": "codex-f57a2ea-20260611T023456",
        "health_app": "image_agent",
        "health_version": "0.2.0",
    }
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
                    "workflow_eligibility": {
                        "policy_version": "workflow_eligibility_v1",
                        "production_task_created": False,
                        "runnable_workflows": [{"workflow_type": "dwi_fast_gpu_dti"}],
                        "blocked_workflows": [],
                    },
                }
            ]
        if url.endswith("/tasks/114/artifact-manifest"):
            return {
                "contract_version": "artifact_manifest_v1",
                "task_id": 114,
                "workflow_type": "dwi_fast_gpu_dti",
                "modality": "DWI",
                "result_summary": {"available": True, "contract_version": "1.0"},
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
    assert payload["series_with_workflow_eligibility"] == 1
    assert payload["artifact_manifest_preview_kinds"] == ["html"]
    assert any(call[1].endswith("/projects/7/series") for call in calls)
    assert any(call[1].endswith("/tasks/114/artifact-manifest") for call in calls)


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
                    "workflow_eligibility": {
                        "policy_version": "workflow_eligibility_v1",
                        "production_task_created": False,
                        "runnable_workflows": [{"workflow_type": "t1_deepprep_anat_report"}],
                        "blocked_workflows": [],
                    },
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
                            "workflow_eligibility": {
                                "policy_version": "workflow_eligibility_v1",
                                "production_task_created": False,
                                "runnable_workflows": [{"workflow_type": "t1_deepprep_anat_report"}],
                                "blocked_workflows": [],
                            },
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
    assert payload["upload_inventory_modalities"] == ["T1"]
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
