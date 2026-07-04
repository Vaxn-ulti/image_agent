import hashlib
import json

from app.agent.rag_orchestration import _raw_source_evidence_for_citations, build_rag_response, query_local_knowledge, retrieve_reference_context, run_agent_tool_chain
from app.agent.rag_index import build_local_rag_index


def test_query_local_knowledge_returns_cited_planning_and_skill_hits(tmp_path):
    planning = tmp_path / ".planning" / "task" / "findings.md"
    skill = tmp_path / "docs" / "skills" / "image-agent-operator" / "SKILL.md"
    planning.parent.mkdir(parents=True)
    skill.parent.mkdir(parents=True)
    planning.write_text("dwi_fast_gpu_dti returns FA MD AD RD MNI152 atlas tables.\n", encoding="utf-8")
    skill.write_text("Backend DB task/output records outrank retrieved docs.\n", encoding="utf-8")

    hits = query_local_knowledge("DWI MNI152 backend records", root=tmp_path, limit=3)

    assert hits
    assert any(hit["path"].endswith("findings.md") for hit in hits)
    assert all("score" in hit for hit in hits)
    assert all("excerpt" in hit for hit in hits)


def test_build_rag_response_keeps_backend_state_first(tmp_path):
    doc = tmp_path / ".planning" / "task" / "findings.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("BOLD second-level metrics include ALFF fALFF ReHo DMN seed-to-ROI.\n", encoding="utf-8")
    backend_context = {"tasks": [{"id": 7, "workflow_type": "bold_second_level", "status": "completed"}]}

    response = build_rag_response("BOLD metrics status", root=tmp_path, backend_context=backend_context)

    assert response["grounding_policy"]["source_priority"][0] == "backend_task_records"
    assert response["backend_context"] == backend_context
    assert response["citations"]
    assert "task 7" in response["answer"]
    assert "BOLD" in response["answer"]


def test_build_rag_response_uses_persistent_index_citations(tmp_path):
    doc = tmp_path / "docs" / "rag" / "contracts" / "container-qc-artifacts.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nsource_type: rag_contract\n---\n# Container QC\n"
        "xcpd_fmriprep logs carry source_stage labels for live wrapper monitoring.\n",
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    response = build_rag_response("xcpd_fmriprep source_stage", root=tmp_path, backend_context={"tasks": []})

    assert response["citations"]
    assert response["citations"][0]["path"].endswith("container-qc-artifacts.md")
    assert response["citations"][0]["source"] == response["citations"][0]["path"]
    assert "source_stage" in response["citations"][0]["excerpt"]


def test_build_rag_response_exposes_persistent_retrieval_mode(tmp_path, monkeypatch):
    import app.agent.rag_orchestration as rag

    def fake_retrieve_reference_context(query, *, root=None, filters=None, limit=5):
        return {
            "mode": "elasticsearch_hybrid",
            "results": [
                {
                    "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                    "title": "Elasticsearch Hybrid Search Contract",
                    "snippet": "Elasticsearch hybrid retrieval combines BM25, dense vector kNN, and RRF.",
                    "score": 12.0,
                    "metadata": {"source_type": "rag_contract"},
                }
            ],
        }

    monkeypatch.setattr(rag, "retrieve_reference_context", fake_retrieve_reference_context)

    response = rag.build_rag_response("Elasticsearch hybrid RRF evidence", root=tmp_path, backend_context={"tasks": []})

    assert response["retrieval_mode"] == "elasticsearch_hybrid"
    assert response["retrieval_source"] == "elasticsearch_hybrid"
    assert response["citations"][0]["source"] == "docs/rag/contracts/elasticsearch-hybrid-search.md"


def test_build_rag_response_exposes_elasticsearch_query_embedding_index_evidence(tmp_path, monkeypatch):
    import app.agent.rag_orchestration as rag

    def fake_retrieve_reference_context(query, *, root=None, filters=None, limit=5):
        return {
            "mode": "elasticsearch_hybrid",
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
            "results": [
                {
                    "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                    "title": "Elasticsearch Hybrid Search Contract",
                    "snippet": "Elasticsearch hybrid query evidence includes index and embedding metadata.",
                    "score": 12.0,
                    "metadata": {"source_type": "rag_contract"},
                }
            ],
        }

    monkeypatch.setattr(rag, "retrieve_reference_context", fake_retrieve_reference_context)

    response = rag.build_rag_response("Elasticsearch query evidence", root=tmp_path, backend_context={"tasks": []})

    assert response["retrieval_mode"] == "elasticsearch_hybrid"
    assert response["elasticsearch_hybrid_query"] == {
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
    }


def test_build_rag_response_sanitizes_langgraph_elasticsearch_query_evidence(tmp_path, monkeypatch):
    import app.agent.rag_orchestration as rag

    class FakeApp:
        def invoke(self, state):
            return {
                "answer": "Hybrid retrieval evidence should stay privacy-safe.",
                "citations": [
                    {
                        "source": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "path": "docs/rag/contracts/elasticsearch-hybrid-search.md",
                        "excerpt": "Elasticsearch hybrid query evidence is safe to show.",
                    }
                ],
                "retrieval_mode": "elasticsearch_hybrid",
                "retrieval_source": "elasticsearch_hybrid",
                "elasticsearch_hybrid_query": {
                    "index": "image_agent_rag_release",
                    "lexical_retriever": "standard",
                    "vector_retriever": "knn",
                    "dense_vector_field": "embedding",
                    "fusion": "rrf",
                    "rrf_unavailable_reason": "license_non_compliant",
                    "dense_vector_dims": 1536,
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_transport": "openai_compatible_http",
                    "embedding_endpoint_configured": True,
                    "embedding_production_ready": True,
                    "embedding_base_url": "https://embedding.example/v1",
                    "embedding_api_key": "sk-secret-token",
                    "error": "Authorization: Bearer sk-secret-token",
                },
            }

    monkeypatch.setattr(rag, "_langgraph_app", lambda: FakeApp())
    monkeypatch.setattr(
        rag,
        "_citation_context",
        lambda query, root=None, limit=5: {
            "citations": [],
            "retrieval_mode": "elasticsearch_hybrid",
            "retrieval_source": "elasticsearch_hybrid",
        },
    )

    response = rag.build_rag_response("Elasticsearch privacy-safe evidence", root=tmp_path, backend_context={"tasks": []})

    assert response["elasticsearch_hybrid_query"] == {
        "index": "image_agent_rag_release",
        "lexical_retriever": "standard",
        "vector_retriever": "knn",
        "dense_vector_field": "embedding",
        "fusion": "rrf",
        "rrf_unavailable_reason": "license_non_compliant",
        "dense_vector_dims": 1536,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_transport": "openai_compatible_http",
        "embedding_endpoint_configured": True,
        "embedding_production_ready": True,
    }
    serialized = json.dumps(response)
    assert "sk-secret-token" not in serialized
    assert "embedding.example" not in serialized
    assert "Authorization" not in serialized


def test_build_rag_response_exposes_raw_source_evidence_for_curated_vendor_citations(tmp_path):
    vendor_doc = tmp_path / "docs" / "rag" / "vendor" / "fmriprep_official_outputs.md"
    raw_root = vendor_doc.parent / "raw-sources"
    raw_source = raw_root / "fmriprep_outputs.html"
    vendor_doc.parent.mkdir(parents=True)
    raw_root.mkdir()
    raw_source.write_text("<html>fMRIPrep official outputs include visual reports</html>", encoding="utf-8")
    raw_bytes = raw_source.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    vendor_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "retrieved_date: 2026-06-07\n"
        "status: curated_summary\n"
        "---\n"
        "# fMRIPrep Official Outputs\n"
        "fMRIPrep writes visual reports and derivative outputs for quality review.\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-07T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": "fmriprep_official_outputs.md",
                        "url": "https://fmriprep.org/en/stable/outputs.html",
                        "file": raw_source.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": raw_sha256,
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    response = build_rag_response("fMRIPrep visual reports outputs", root=tmp_path, backend_context={"tasks": []})

    assert response["citations"][0]["path"].endswith("fmriprep_official_outputs.md")
    evidence = response["raw_source_evidence"]
    assert evidence["policy"] == "raw snapshots are traceability evidence and are not indexed wholesale"
    assert evidence["sources"] == [
        {
            "vendor_doc": "fmriprep_official_outputs.md",
            "curated_source": "docs/rag/vendor/fmriprep_official_outputs.md",
            "raw_source_ids": ["fmriprep_outputs"],
            "source_urls": ["https://fmriprep.org/en/stable/outputs.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_outputs.html"],
            "source_types": ["official_docs"],
            "raw_snapshots": [
                {
                    "id": "fmriprep_outputs",
                    "file": "docs/rag/vendor/raw-sources/fmriprep_outputs.html",
                    "url": "https://fmriprep.org/en/stable/outputs.html",
                    "sha256": raw_sha256,
                    "bytes": len(raw_bytes),
                    "retrieved_at": "2026-06-07T00:00:00Z",
                    "source_type": "official_docs",
                    "status": "downloaded",
                }
            ],
            "complete": True,
        }
    ]
    assert evidence["unmatched_citations"] == []
    assert evidence["raw_sources_indexed"] is False


def test_build_rag_response_exposes_raw_source_evidence_for_workflow_grounding(tmp_path):
    workflow_doc = tmp_path / "docs" / "rag" / "workflows" / "t1_deepprep_anat_report.md"
    vendor_doc = tmp_path / "docs" / "rag" / "vendor" / "deepprep_official_container_usage.md"
    raw_root = vendor_doc.parent / "raw-sources"
    raw_source = raw_root / "deepprep_usage_local.html"
    workflow_doc.parent.mkdir(parents=True)
    vendor_doc.parent.mkdir(parents=True)
    raw_root.mkdir()
    raw_source.write_text("<html>DeepPrep local usage official container documentation</html>", encoding="utf-8")
    raw_bytes = raw_source.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    vendor_doc.write_text(
        "---\n"
        "source_url: https://deepprep.readthedocs.io/en/latest/local.html\n"
        "raw_source_ids: deepprep_usage_local\n"
        "retrieved_date: 2026-06-07\n"
        "status: curated_summary\n"
        "---\n"
        "# DeepPrep Official Container Usage\n"
        "Official container command usage and runtime arguments are summarized here.\n",
        encoding="utf-8",
    )
    workflow_doc.write_text(
        "---\n"
        "source_type: rag_workflow\n"
        "workflow_type: t1_deepprep_anat_report\n"
        "official_grounding:\n"
        "  - docs/rag/vendor/deepprep_official_container_usage.md\n"
        "expected_artifacts:\n"
        "  - reports/index.html\n"
        "---\n"
        "# T1 DeepPrep Anatomy Report\n"
        "unique_t1_workflow_grounding_phrase depends on native QC and container outputs.\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-07T00:00:00Z",
                "sources": [
                    {
                        "id": "deepprep_usage_local",
                        "vendor_doc": "deepprep_official_container_usage.md",
                        "url": "https://deepprep.readthedocs.io/en/latest/local.html",
                        "file": raw_source.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": raw_sha256,
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    response = build_rag_response("unique_t1_workflow_grounding_phrase", root=tmp_path, backend_context={"tasks": []})

    assert response["citations"][0]["path"].endswith("t1_deepprep_anat_report.md")
    evidence = response["raw_source_evidence"]
    assert evidence["sources"] == [
        {
            "vendor_doc": "deepprep_official_container_usage.md",
            "curated_source": "docs/rag/vendor/deepprep_official_container_usage.md",
            "raw_source_ids": ["deepprep_usage_local"],
            "source_urls": ["https://deepprep.readthedocs.io/en/latest/local.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/deepprep_usage_local.html"],
            "source_types": ["official_docs"],
            "raw_snapshots": [
                {
                    "id": "deepprep_usage_local",
                    "file": "docs/rag/vendor/raw-sources/deepprep_usage_local.html",
                    "url": "https://deepprep.readthedocs.io/en/latest/local.html",
                    "sha256": raw_sha256,
                    "bytes": len(raw_bytes),
                    "retrieved_at": "2026-06-07T00:00:00Z",
                    "source_type": "official_docs",
                    "status": "downloaded",
                }
            ],
            "complete": True,
        }
    ]
    assert evidence["unmatched_citations"] == []


def test_fallback_retrieve_reference_context_preserves_yaml_list_metadata(tmp_path):
    workflow_doc = tmp_path / "docs" / "rag" / "workflows" / "t1_deepprep_anat_report.md"
    workflow_doc.parent.mkdir(parents=True)
    workflow_doc.write_text(
        "---\n"
        "source_type: rag_workflow\n"
        "workflow_type: t1_deepprep_anat_report\n"
        "status: production_supported\n"
        "official_grounding:\n"
        "  - docs/rag/vendor/deepprep_official_container_usage.md\n"
        "  - docs/rag/vendor/freesurfer_official_container_reconall.md\n"
        "expected_artifacts:\n"
        "  - summary/t1_result_summary.json\n"
        "unsupported_boundaries:\n"
        "  - no clinical diagnosis\n"
        "---\n"
        "# T1 DeepPrep Anatomy Report\n"
        "unique fallback metadata phrase for native DeepPrep QC.\n",
        encoding="utf-8",
    )

    result = retrieve_reference_context("unique fallback metadata phrase", root=tmp_path, limit=1)

    assert result["mode"] == "local_file_search"
    metadata = result["results"][0]["metadata"]
    assert metadata["official_grounding"] == [
        "docs/rag/vendor/deepprep_official_container_usage.md",
        "docs/rag/vendor/freesurfer_official_container_reconall.md",
    ]
    assert metadata["expected_artifacts"] == ["summary/t1_result_summary.json"]
    assert metadata["unsupported_boundaries"] == ["no clinical diagnosis"]


def test_raw_source_evidence_uses_workflow_official_grounding_metadata(tmp_path):
    vendor_doc = tmp_path / "docs" / "rag" / "vendor" / "deepprep_official_container_usage.md"
    raw_root = vendor_doc.parent / "raw-sources"
    raw_source = raw_root / "deepprep_usage_local.html"
    vendor_doc.parent.mkdir(parents=True)
    raw_root.mkdir()
    raw_source.write_text("<html>DeepPrep local usage official container documentation</html>", encoding="utf-8")
    raw_bytes = raw_source.read_bytes()
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    vendor_doc.write_text(
        "---\n"
        "source_url: https://deepprep.readthedocs.io/en/latest/local.html\n"
        "raw_source_ids: deepprep_usage_local\n"
        "retrieved_date: 2026-06-07\n"
        "status: curated_summary\n"
        "---\n"
        "# DeepPrep Official Container Usage\n"
        "Official container command usage and runtime arguments are summarized here.\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-07T00:00:00Z",
                "sources": [
                    {
                        "id": "deepprep_usage_local",
                        "vendor_doc": "deepprep_official_container_usage.md",
                        "url": "https://deepprep.readthedocs.io/en/latest/local.html",
                        "file": raw_source.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": raw_sha256,
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    evidence = _raw_source_evidence_for_citations(
        [
            {
                "source": "docs/rag/workflows/t1_deepprep_anat_report.md",
                "metadata": {
                    "source_type": "rag_workflow",
                    "official_grounding": ["docs/rag/vendor/deepprep_official_container_usage.md"],
                },
            }
        ],
        root=tmp_path,
    )

    assert evidence["sources"] == [
        {
            "vendor_doc": "deepprep_official_container_usage.md",
            "curated_source": "docs/rag/vendor/deepprep_official_container_usage.md",
            "raw_source_ids": ["deepprep_usage_local"],
            "source_urls": ["https://deepprep.readthedocs.io/en/latest/local.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/deepprep_usage_local.html"],
            "source_types": ["official_docs"],
            "raw_snapshots": [
                {
                    "id": "deepprep_usage_local",
                    "file": "docs/rag/vendor/raw-sources/deepprep_usage_local.html",
                    "url": "https://deepprep.readthedocs.io/en/latest/local.html",
                    "sha256": raw_sha256,
                    "bytes": len(raw_bytes),
                    "retrieved_at": "2026-06-07T00:00:00Z",
                    "source_type": "official_docs",
                    "status": "downloaded",
                }
            ],
            "complete": True,
        }
    ]
    assert evidence["unmatched_citations"] == []


def test_build_rag_response_grounds_launchability_questions_in_matrix(tmp_path):
    matrix = tmp_path / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    vendor = tmp_path / "docs" / "rag" / "vendor" / "mriqc_official_container_usage_outputs.md"
    matrix.parent.mkdir(parents=True)
    vendor.parent.mkdir(parents=True)
    matrix.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: workflow_launchability_matrix\n---\n"
        "# Workflow Launchability Matrix\n"
        "MRIQC is `incubation_reference`, DPABI is `unsupported_external`, and QSIPrep is legacy/explicit.\n"
        "Do not create production tasks from this matrix. `workflow_eligibility` remains authoritative for launchability.\n"
        "`/tasks/{task_id}/result-summary` remains authoritative for completed outputs.\n",
        encoding="utf-8",
    )
    vendor.write_text(
        "---\nsource_type: rag_vendor\n---\n"
        "# MRIQC Official Container Usage\n"
        "mriqc /data /out participant produces reports and IQMs.\n",
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    response = build_rag_response(
        "Can Image Agent run MRIQC, DPABI, or QSIPrep in production?",
        root=tmp_path,
        backend_context={"tasks": []},
    )

    assert response["intent"] == "launchability"
    assert response["citations"]
    assert response["citations"][0]["path"].endswith("workflow_launchability_matrix.md")
    assert "incubation_reference" in response["answer"]
    assert "unsupported_external" in response["answer"]
    assert "workflow_eligibility remains authoritative" in response["answer"]
    assert "Do not create production tasks from this matrix" in response["answer"]


def test_build_rag_response_pins_launchability_matrix_when_index_is_stale(tmp_path):
    stale_doc = tmp_path / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry.md"
    stale_doc.parent.mkdir(parents=True)
    stale_doc.write_text(
        "---\nsource_type: skill_reference\n---\n"
        "# Registry\nMRIQC QSIPrep QSIRecon support notes without the new matrix.\n",
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    matrix = tmp_path / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    matrix.parent.mkdir(parents=True)
    matrix.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: workflow_launchability_matrix\n---\n"
        "# Workflow Launchability Matrix\n"
        "MRIQC is `incubation_reference`, DPABI is `unsupported_external`, and QSIPrep is legacy/explicit.\n",
        encoding="utf-8",
    )

    response = build_rag_response(
        "Can Image Agent run MRIQC DPABI QSIPrep in production?",
        root=tmp_path,
        backend_context={"tasks": []},
    )

    assert response["citations"][0]["path"].endswith("workflow_launchability_matrix.md")
    assert "incubation_reference" in response["answer"]


def test_build_rag_response_summarizes_backend_when_docs_do_not_match(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [{"id": 9, "workflow_type": "dwi_fast_gpu_dti", "status": "running", "progress": 45}],
        "outputs": [],
    }

    response = build_rag_response("current task state", root=tmp_path, backend_context=backend_context)

    assert response["citations"] == []
    assert "Project 3" in response["answer"]
    assert "task 9: dwi_fast_gpu_dti is running (45%)" in response["answer"]


def test_build_rag_response_distinguishes_stable_workflow_id_from_runtime_alias(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [
            {
                "id": 9,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
                "progress": 100,
            }
        ],
        "outputs": [],
    }

    response = build_rag_response("current task state", root=tmp_path, backend_context=backend_context)

    assert "task 9: t1_deepprep_anat_report" in response["answer"]
    assert "runtime runner t1_deepprep" in response["answer"]


def test_build_rag_response_summarizes_supported_workflow_capabilities_from_backend_context(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [],
        "outputs": [],
        "supported_workflows": [
            {
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "lane": "fixed_workflow",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs anatomical T1 processing, QC, and report outputs.",
                "requires_confirmation": True,
                "is_report_only": False,
            },
            {
                "workflow_type": "toolchain_proposal",
                "runtime_workflow_type": None,
                "lane": "toolchain_incubation",
                "display_name": "Incubating toolchain proposal",
                "capability_summary": "Captures unknown workflow proposals for human review.",
                "requires_confirmation": False,
                "is_report_only": False,
            },
        ],
    }

    response = build_rag_response("What fixed workflows can Image Agent run?", root=tmp_path, backend_context=backend_context)

    assert "Supported workflow capabilities" in response["answer"]
    assert "t1_deepprep_anat_report" in response["answer"]
    assert "T1 DeepPrep anatomical processing, QC, and report" in response["answer"]
    assert "runtime runner t1_deepprep" in response["answer"]
    assert "toolchain_proposal is toolchain_incubation" in response["answer"]


def test_build_rag_response_marks_complete_fixed_workflow_as_not_report_only(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [],
        "outputs": [],
        "supported_workflows": [
            {
                "workflow_type": "bold_fmriprep_xcpd_report",
                "runtime_workflow_type": "bold_fmriprep_xcpd_report",
                "lane": "fixed_workflow",
                "display_name": "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report",
                "capability_summary": "Runs BOLD preprocessing, XCP-D metrics, QC, and report outputs.",
                "requires_confirmation": True,
                "is_report_only": False,
            }
        ],
    }

    response = build_rag_response("Is bold_fmriprep_xcpd_report only a report workflow?", root=tmp_path, backend_context=backend_context)

    assert "bold_fmriprep_xcpd_report is fixed_workflow" in response["answer"]
    assert "not report-only" in response["answer"]
    assert "requires human confirmation" in response["answer"]


def test_build_rag_response_preserves_t1_stable_workflow_id_and_runtime_alias(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [],
        "outputs": [],
        "supported_workflows": [
            {
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
                "lane": "fixed_workflow",
                "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                "capability_summary": "Runs anatomical T1 processing, QC, summaries, and report artifacts.",
                "requires_confirmation": True,
                "is_report_only": False,
            }
        ],
    }

    response = build_rag_response("Is t1_deepprep_anat_report only a report workflow?", root=tmp_path, backend_context=backend_context)

    assert "t1_deepprep_anat_report is fixed_workflow" in response["answer"]
    assert "runtime runner t1_deepprep" in response["answer"]
    assert "not report-only" in response["answer"]
    assert "requires human confirmation" in response["answer"]


def test_build_rag_response_marks_dwi_fixed_workflow_as_not_report_only(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [],
        "outputs": [],
        "supported_workflows": [
            {
                "workflow_type": "dwi_fast_gpu_dti",
                "runtime_workflow_type": "dwi_fast_gpu_dti",
                "lane": "fixed_workflow",
                "display_name": "DWI fast GPU DTI maps, atlas metrics, QC, and report",
                "capability_summary": "Runs DWI correction, tensor maps, atlas metrics, QC, summaries, and report artifacts.",
                "requires_confirmation": True,
                "is_report_only": False,
            }
        ],
    }

    response = build_rag_response("Is dwi_fast_gpu_dti just a report workflow?", root=tmp_path, backend_context=backend_context)

    assert "dwi_fast_gpu_dti is fixed_workflow" in response["answer"]
    assert "not report-only" in response["answer"]
    assert "requires human confirmation" in response["answer"]


def test_build_rag_response_uses_result_summary_workflow_metadata(tmp_path):
    backend_context = {
        "project_id": 3,
        "tasks": [
            {
                "id": 41,
                "workflow_type": "t1_deepprep",
                "runtime_workflow_type": "t1_deepprep",
                "status": "completed",
                "progress": 100,
            }
        ],
        "outputs": [],
        "result_summaries": [
            {
                "task_id": 41,
                "workflow_type": "t1_deepprep",
                "modality": "T1",
                "spaces": ["T1w"],
                "feature_groups": ["quality_control"],
                "outputs": {},
                "provenance": {},
                "workflow_metadata": {
                    "workflow_type": "t1_deepprep_anat_report",
                    "runtime_workflow_type": "t1_deepprep",
                    "display_name": "T1 DeepPrep anatomical processing, QC, and report",
                    "capability_summary": "Runs anatomical T1 processing, QC, summaries, and report artifacts.",
                    "is_report_only": False,
                },
            }
        ],
    }

    response = build_rag_response("show task 41 result-summary report", root=tmp_path, backend_context=backend_context)

    assert "Result summaries" in response["answer"]
    assert "task 41" in response["answer"]
    assert "T1 DeepPrep anatomical processing, QC, and report" in response["answer"]
    assert "stable workflow id t1_deepprep" in response["answer"]
    assert "public workflow metadata t1_deepprep_anat_report" in response["answer"]
    assert "not report-only" in response["answer"]


def test_build_rag_response_exposes_intent_and_next_step_hint(tmp_path):
    response = build_rag_response("我想看状态并理解下一步", root=tmp_path, backend_context={"tasks": []})

    assert response["intent"] in {"status", "next_step"}
    assert response["recommended_next_step"]
    assert response["tool_chain_hint"]
    assert response["mode"] in {"fallback", "langgraph"}


def test_agent_tool_chain_inspects_tasks_outputs_and_reports(tmp_path):
    report_summary = tmp_path / "summary" / "dwi_scientific_report_summary.json"
    report_summary.parent.mkdir()
    report_summary.write_text(
        '{"modality":"DWI","outputs":{"reports":[{"relative_path":"reports/index.html"},{"relative_path":"reports/report_manifest.json"}]}}',
        encoding="utf-8",
    )
    backend_context = {
        "tasks": [{"id": 114, "workflow_type": "dwi_fast_gpu_dti", "status": "completed", "progress": 100}],
        "outputs": [
            {"task_id": 114, "output_type": "json", "path": str(tmp_path / "summary" / "dwi_result_summary.json"), "metadata_json": '{"kind":"result_summary"}'},
            {"task_id": 114, "output_type": "json", "path": str(report_summary), "metadata_json": '{"kind":"scientific_report_summary"}'},
        ],
    }

    invocations = run_agent_tool_chain("show task status and report", backend_context)
    tools = {item["tool"]: item["result"] for item in invocations}

    assert tools["inspect_task_status"]["completed_task_ids"] == [114]
    assert tools["inspect_registered_outputs"]["result_summary_tasks"] == [114]
    assert tools["inspect_scientific_reports"]["report_summaries"][0]["has_index_html"] is True
    assert tools["recommend_next_action"]["policy"].startswith("read-only")


def test_agent_tool_chain_reads_reports_from_result_summary_contract(tmp_path):
    backend_context = {
        "tasks": [{"id": 41, "workflow_type": "t1_deepprep", "status": "completed", "progress": 100}],
        "outputs": [],
        "result_summaries": [
            {
                "task_id": 41,
                "modality": "T1",
                "outputs": {
                    "reports": [
                        {"relative_path": "reports/index.html", "content_type": "text/html"},
                        {"relative_path": "reports/t1_region_thickness.png", "content_type": "image/png"},
                    ]
                },
            }
        ],
    }

    invocations = run_agent_tool_chain("查看任务41状态和报告", backend_context)
    tools = {item["tool"]: item["result"] for item in invocations}

    assert tools["inspect_scientific_reports"]["result_summary_reports"][0]["task_id"] == 41
    assert tools["inspect_scientific_reports"]["result_summary_reports"][0]["figure_count"] == 1
    assert "Review the result-summary report figures" in tools["recommend_next_action"]["recommended_action"]


def test_agent_tool_chain_failed_task_repair_advice_is_read_only():
    backend_context = {
        "tasks": [
            {
                "id": 9,
                "workflow_type": "bold_fmriprep_xcpd_report",
                "status": "failed",
                "progress": 42,
                "error_message": "container exited",
            }
        ],
        "outputs": [],
    }

    invocations = run_agent_tool_chain("task failed, retry it", backend_context)
    tools = {item["tool"]: item["result"] for item in invocations}
    recommendation = tools["recommend_next_action"]["recommended_action"].lower()

    assert tools["recommend_next_action"]["policy"].startswith("read-only")
    assert "preflight" in recommendation
    assert "human confirmation" in recommendation
    assert "automatically" not in recommendation
    assert "choose a targeted retry" not in recommendation


def test_agent_tool_chain_missing_report_repair_advice_does_not_rerun_automatically(tmp_path):
    backend_context = {
        "tasks": [{"id": 41, "workflow_type": "t1_deepprep", "status": "completed", "progress": 100}],
        "outputs": [
            {
                "task_id": 41,
                "output_type": "json",
                "path": str(tmp_path / "summary" / "t1_result_summary.json"),
                "metadata_json": '{"kind":"result_summary"}',
            }
        ],
    }

    invocations = run_agent_tool_chain("show task status and report", backend_context)
    tools = {item["tool"]: item["result"] for item in invocations}
    recommendation = tools["recommend_next_action"]["recommended_action"].lower()

    assert tools["recommend_next_action"]["policy"].startswith("read-only")
    assert "repair" in recommendation
    assert "human confirmation" in recommendation
    assert "rerun the report generator" not in recommendation


def test_chinese_task_status_query_is_classified_as_status(tmp_path):
    response = build_rag_response("查看任务41、111、114的状态", root=tmp_path, backend_context={"tasks": []})

    assert response["intent"] == "status"
    assert response["tool_invocations"]
