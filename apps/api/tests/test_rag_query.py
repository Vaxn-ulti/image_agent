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


def test_chinese_task_status_query_is_classified_as_status(tmp_path):
    response = build_rag_response("查看任务41、111、114的状态", root=tmp_path, backend_context={"tasks": []})

    assert response["intent"] == "status"
    assert response["tool_invocations"]
