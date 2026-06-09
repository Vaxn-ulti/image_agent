from app.agent.prompt_loader import load_prompt_bundle
import hashlib
import json

from app.agent.rag_index import build_local_rag_index, rag_vendor_coverage_catalog, rag_vendor_pointer_integrity, retrieve_from_local_rag_index, vendor_raw_source_status
from app.agent.state import AGENT_STATE_FIELDS


def _curated_without_snapshots(item):
    return {key: value for key, value in item.items() if key != "raw_snapshots"}


def test_agent_state_declares_openai_style_orchestration_fields():
    assert {
        "messages",
        "project_id",
        "action_lane",
        "retrieved_context",
        "selected_skill",
        "selected_workflow_type",
        "proposed_toolchain",
        "preflight",
        "confirmation_result",
        "task_status",
        "result_summary",
    } <= set(AGENT_STATE_FIELDS)


def test_prompt_loader_reads_all_instruction_files():
    bundle = load_prompt_bundle()

    assert "planner" in bundle
    assert "responder" in bundle
    assert "safety" in bundle
    assert "tool-use" in bundle
    assert "rag-use" in bundle
    assert "image_agent" in bundle["planner"]


def test_local_rag_index_persists_manifest_for_docs_and_skills(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "contracts" / "result-summary.md"
    skill_doc = root / "docs" / "skills" / "image-agent-operator" / "SKILL.md"
    rag_doc.parent.mkdir(parents=True)
    skill_doc.parent.mkdir(parents=True)
    rag_doc.write_text("# Result Summary\nbackend result-summary contract\n", encoding="utf-8")
    skill_doc.write_text("---\nname: image-agent-operator\n---\n# Operator\nbackend grounding\n", encoding="utf-8")

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")

    assert manifest["engine"] in {"llama_index", "local_manifest"}
    assert manifest["document_count"] == 2
    assert (root / ".rag_index" / "manifest.json").exists()
    assert any(item["source"].endswith("result-summary.md") for item in manifest["documents"])
    assert any(item["source"].endswith("SKILL.md") for item in manifest["documents"])


def test_local_rag_index_persists_semantic_chunks_with_hashes_and_filters(tmp_path):
    root = tmp_path / "repo"
    rag_doc = root / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    skill_ref = root / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry-and-preflight.md"
    rag_doc.parent.mkdir(parents=True)
    skill_ref.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\nmodality: BOLD\n"
        "source_url: https://example.org/bold\nretrieved_date: 2026-06-06\n---\n"
        "# BOLD fMRIPrep XCP-D\nXCP-D outputs connectivity tables and HTML reports.\n",
        encoding="utf-8",
    )
    skill_ref.write_text(
        "---\nsource_type: skill_reference\nskill: image-agent-workflow-runner\npriority: policy\n---\n"
        "# Registry and preflight\nFixed workflows require backend preflight and user confirmation.\n",
        encoding="utf-8",
    )

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    result = retrieve_from_local_rag_index(
        "XCP-D connectivity tables",
        root=root,
        persist_dir=root / ".rag_index",
        filters={"workflow_type": "bold_fmriprep_xcpd_report"},
        limit=3,
    )

    assert manifest["semantic_index"] is True
    if manifest["engine"] == "llama_index":
        assert (root / ".rag_index" / "docstore.json").exists()
    else:
        assert manifest["engine"] == "local_manifest"
        assert (root / ".rag_index" / "chunks.jsonl").exists()
    assert all(item["sha256"] for item in manifest["documents"])
    assert result["mode"] in {"llama_index", "local_persistent_index"}
    assert result["results"]
    assert result["results"][0]["metadata"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert "sha256" in result["results"][0]["metadata"]


def test_local_rag_index_excludes_vendor_raw_sources_even_when_markdown(tmp_path):
    root = tmp_path / "repo"
    curated = root / "docs" / "rag" / "vendor" / "openai_official_responses_function_tools.md"
    raw_root = root / "docs" / "rag" / "vendor" / "raw-sources"
    raw_source = raw_root / "openai_python_sdk_readme.md"
    curated.parent.mkdir(parents=True)
    raw_root.mkdir(parents=True)
    curated.write_text("# OpenAI SDK Contract\nofficial OpenAI Python SDK responses.create\n", encoding="utf-8")
    raw_source.write_text("# Raw SDK README\nunique_raw_sdk_phrase_should_not_be_indexed\n", encoding="utf-8")
    raw_bytes = raw_source.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "openai_python_sdk_readme",
                        "vendor_doc": "openai_official_responses_function_tools.md",
                        "url": "https://raw.githubusercontent.com/openai/openai-python/main/README.md",
                        "file": raw_source.name,
                        "source_type": "official_repository",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = build_local_rag_index(root=root, persist_dir=root / ".rag_index")
    status = vendor_raw_source_status(root=root, indexed_sources=[doc["source"] for doc in manifest["documents"]])
    result = retrieve_from_local_rag_index(
        "unique_raw_sdk_phrase_should_not_be_indexed",
        root=root,
        persist_dir=root / ".rag_index",
        limit=5,
    )

    assert [doc["source"] for doc in manifest["documents"]] == ["docs/rag/vendor/openai_official_responses_function_tools.md"]
    assert status["raw_sources_indexed"] is False
    assert all("docs/rag/vendor/raw-sources" not in item["source"] for item in result["results"])


def test_vendor_raw_source_status_verifies_hashes_without_indexing_raw_html(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    raw_root.mkdir(parents=True)
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "generated_at": "2026-06-06T00:00:00Z",
        "sources": [
            {
                "id": "fmriprep_usage",
                "vendor_doc": "fmriprep_official_container_usage.md",
                "url": "https://fmriprep.org/en/stable/usage.html",
                "file": raw_file.name,
                "source_type": "official_docs",
                "retrieved_at": "2026-06-06T00:00:00Z",
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "bytes": len(raw_bytes),
                "status": "downloaded",
            }
        ],
    }
    (raw_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["manifest_exists"] is True
    assert status["source_count"] == 1
    assert status["vendor_doc_count"] == 1
    assert status["missing_files"] == []
    assert status["hash_mismatches"] == []
    assert status["raw_sources_indexed"] is False
    assert status["curated_provenance_issues"] == []
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
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
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == [
        {
            "id": "fmriprep_usage",
            "file": "docs/rag/vendor/raw-sources/fmriprep_usage.html",
            "url": "https://fmriprep.org/en/stable/usage.html",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "bytes": len(raw_bytes),
            "retrieved_at": "2026-06-06T00:00:00Z",
            "source_type": "official_docs",
            "status": "downloaded",
        }
    ]


def test_rag_vendor_pointer_integrity_requires_complete_vendor_docs(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    workflow = root / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    contract = root / "docs" / "rag" / "contracts" / "container-qc-artifacts.md"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    workflow.parent.mkdir(parents=True)
    contract.parent.mkdir(parents=True)
    raw_file = raw_root / "fmriprep_outputs.html"
    raw_file.write_text("<html>official outputs</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_outputs.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "---\n"
        "# fMRIPrep Outputs\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": "fmriprep_official_outputs.md",
                        "url": "https://fmriprep.org/en/stable/outputs.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    workflow.write_text(
        "# Matrix\n"
        "Official grounding: `docs/rag/vendor/fmriprep_official_outputs.md`.\n",
        encoding="utf-8",
    )
    contract.write_text(
        "# Contract\n"
        "Accepted `official_source_ids` include `docs/rag/vendor/fmriprep_official_outputs.md`.\n",
        encoding="utf-8",
    )

    status = rag_vendor_pointer_integrity(root=root)

    assert status["ok"] is True
    assert status["pointer_count"] == 2
    assert status["issue_count"] == 0
    assert sorted(status["referenced_vendor_docs"]) == ["fmriprep_official_outputs.md"]
    assert status["pointers_by_doc"] == {
        "docs/rag/contracts/container-qc-artifacts.md": ["docs/rag/vendor/fmriprep_official_outputs.md"],
        "docs/rag/workflows/workflow_launchability_matrix.md": ["docs/rag/vendor/fmriprep_official_outputs.md"],
    }

    contract.write_text(
        "# Contract\n"
        "Bad pointer: `docs/rag/vendor/missing_official_outputs.md`.\n",
        encoding="utf-8",
    )
    failed = rag_vendor_pointer_integrity(root=root)

    assert failed["ok"] is False
    assert {
        "source_doc": "docs/rag/contracts/container-qc-artifacts.md",
        "vendor_doc": "missing_official_outputs.md",
        "vendor_path": "docs/rag/vendor/missing_official_outputs.md",
        "issue": "missing_or_incomplete_vendor_doc",
    } in failed["issues"]


def test_rag_vendor_coverage_catalog_summarizes_vendor_docs_without_raw_text(tmp_path):
    root = tmp_path
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    workflow_root = root / "docs" / "rag" / "workflows"
    vendor_doc = vendor_root / "fmriprep_official_outputs.md"
    raw_doc = raw_root / "fmriprep_outputs.html"
    workflow_doc = workflow_root / "bold_fmriprep_xcpd_report.md"
    raw_root.mkdir(parents=True)
    workflow_root.mkdir(parents=True)
    vendor_doc.write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/outputs.html\n"
        "raw_source_ids: fmriprep_outputs\n"
        "---\n"
        "# fMRIPrep outputs\n"
        "Curated summary.\n",
        encoding="utf-8",
    )
    raw_doc.write_text("<html>raw official fMRIPrep output page text</html>", encoding="utf-8")
    raw_bytes = raw_doc.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-06T00:00:00Z",
                "sources": [
                    {
                        "id": "fmriprep_outputs",
                        "vendor_doc": vendor_doc.name,
                        "url": "https://fmriprep.org/en/stable/outputs.html",
                        "file": raw_doc.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    workflow_doc.write_text(
        "# Workflow\n"
        "Native reports are grounded by docs/rag/vendor/fmriprep_official_outputs.md.\n",
        encoding="utf-8",
    )

    catalog = rag_vendor_coverage_catalog(root=root, indexed_sources=[])

    assert catalog["status"] == "complete"
    assert catalog["policy"] == "curated summaries are indexed; raw snapshots are provenance evidence only"
    assert catalog["vendor_doc_count"] == 1
    assert catalog["complete_vendor_doc_count"] == 1
    assert catalog["raw_source_count"] == 1
    assert catalog["raw_sources_indexed"] is False
    assert catalog["pointer_integrity_ok"] is True
    assert catalog["vendors"] == [
        {
            "vendor_doc": "fmriprep_official_outputs.md",
            "vendor_path": "docs/rag/vendor/fmriprep_official_outputs.md",
            "complete": True,
            "manifest_backed": True,
            "source_url_backed": True,
            "raw_source_count": 1,
            "source_url_count": 1,
            "source_types": ["official_docs"],
            "referenced_by": ["docs/rag/workflows/bold_fmriprep_xcpd_report.md"],
            "raw_source_ids": ["fmriprep_outputs"],
        }
    ]
    serialized = json.dumps(catalog)
    assert "raw official fMRIPrep output page text" not in serialized
    assert "manifest_path" not in serialized
    assert "persist_dir" not in serialized
    assert str(root) not in serialized
    assert "raw_snapshots" not in serialized
    assert "sha256" not in serialized
    assert "docs/rag/vendor/raw-sources" not in serialized


def test_vendor_raw_source_status_flags_raw_html_if_indexed(tmp_path):
    root = tmp_path / "repo"
    raw_root = root / "docs" / "rag" / "vendor" / "raw-sources"
    raw_root.mkdir(parents=True)
    raw_file = raw_root / "xcp_d_usage.html"
    raw_file.write_text("<html>XCP-D usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "xcp_d_usage",
                        "vendor_doc": "xcp_d_official_container_usage.md",
                        "url": "https://xcp-d.readthedocs.io/en/stable/usage.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(
        root=root,
        indexed_sources=["docs/rag/vendor/raw-sources/xcp_d_usage.html"],
    )

    assert status["raw_sources_indexed"] is True
    assert status["indexed_raw_sources"] == ["docs/rag/vendor/raw-sources/xcp_d_usage.html"]


def test_vendor_raw_source_status_flags_unknown_curated_raw_source_ids(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage, missing_source\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["curated_provenance_issues"] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "issue": "unknown_raw_source_id",
            "raw_source_id": "missing_source",
        }
    ]
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage", "missing_source"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": ["docs/rag/vendor/raw-sources/fmriprep_usage.html"],
            "source_types": ["official_docs"],
            "manifest_backed": False,
            "source_url_backed": True,
            "complete": False,
        }
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == [
        {
            "id": "fmriprep_usage",
            "file": "docs/rag/vendor/raw-sources/fmriprep_usage.html",
            "url": "https://fmriprep.org/en/stable/usage.html",
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "bytes": len(raw_bytes),
            "retrieved_at": "2026-06-06T00:00:00Z",
            "source_type": "official_docs",
            "status": "downloaded",
        }
    ]


def test_vendor_raw_source_status_audits_vendor_docs_not_named_by_manifest(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (vendor_root / "unbacked_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://example.org/unbacked.html\n"
        "raw_source_ids: unbacked_source\n"
        "---\n"
        "# Unbacked\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert {
        "vendor_doc": "unbacked_official_container_usage.md",
        "issue": "unknown_raw_source_id",
        "raw_source_id": "unbacked_source",
    } in status["curated_provenance_issues"]
    assert [item["vendor_doc"] for item in status["curated_sources"]] == [
        "fmriprep_official_container_usage.md",
        "unbacked_official_container_usage.md",
    ]
    assert status["curated_sources"][1]["complete"] is False


def test_vendor_raw_source_status_rejects_raw_source_id_from_other_vendor_doc(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "xcp_d_usage.html"
    raw_file.write_text("<html>official XCP-D usage</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://xcp-d.readthedocs.io/en/stable/usage.html\n"
        "raw_source_ids: xcp_d_usage\n"
        "---\n"
        "# fMRIPrep wrongly citing XCP-D\n",
        encoding="utf-8",
    )
    (vendor_root / "xcp_d_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://xcp-d.readthedocs.io/en/stable/usage.html\n"
        "raw_source_ids: xcp_d_usage\n"
        "---\n"
        "# XCP-D\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "xcp_d_usage",
                        "vendor_doc": "xcp_d_official_container_usage.md",
                        "url": "https://xcp-d.readthedocs.io/en/stable/usage.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert {
        "vendor_doc": "fmriprep_official_container_usage.md",
        "issue": "raw_source_vendor_doc_mismatch",
        "raw_source_id": "xcp_d_usage",
        "manifest_vendor_doc": "xcp_d_official_container_usage.md",
    } in status["curated_provenance_issues"]
    fmriprep_entry = next(item for item in status["curated_sources"] if item["vendor_doc"] == "fmriprep_official_container_usage.md")
    assert fmriprep_entry["manifest_backed"] is False
    assert fmriprep_entry["complete"] is False


def test_vendor_raw_source_status_rejects_manifest_file_path_escape(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": "../fmriprep_usage.html",
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": "",
                        "bytes": 12,
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert {
        "vendor_doc": "fmriprep_official_container_usage.md",
        "issue": "raw_source_file_path_unsafe",
        "raw_source_id": "fmriprep_usage",
        "file": "../fmriprep_usage.html",
    } in status["curated_provenance_issues"]
    assert status["missing_files"] == ["../fmriprep_usage.html"]
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": [],
            "source_types": [],
            "manifest_backed": False,
            "source_url_backed": False,
            "complete": False,
        }
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == []


def test_vendor_raw_source_status_marks_curated_doc_incomplete_when_raw_file_hash_bad(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "fmriprep_usage.html"
    raw_file.write_text("<html>official fMRIPrep usage changed</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "fmriprep_official_container_usage.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://fmriprep.org/en/stable/usage.html\n"
        "raw_source_ids: fmriprep_usage\n"
        "---\n"
        "# fMRIPrep\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "fmriprep_usage",
                        "vendor_doc": "fmriprep_official_container_usage.md",
                        "url": "https://fmriprep.org/en/stable/usage.html",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": "0" * 64,
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["hash_mismatches"] == ["fmriprep_usage.html"]
    assert {
        "vendor_doc": "fmriprep_official_container_usage.md",
        "issue": "raw_source_file_integrity_failed",
        "raw_source_id": "fmriprep_usage",
        "file": "fmriprep_usage.html",
    } in status["curated_provenance_issues"]
    assert [_curated_without_snapshots(item) for item in status["curated_sources"]] == [
        {
            "vendor_doc": "fmriprep_official_container_usage.md",
            "raw_source_ids": ["fmriprep_usage"],
            "source_urls": ["https://fmriprep.org/en/stable/usage.html"],
            "raw_files": [],
            "source_types": [],
            "manifest_backed": False,
            "source_url_backed": False,
            "complete": False,
        }
    ]
    assert status["curated_sources"][0]["raw_snapshots"] == []


def test_vendor_raw_source_status_flags_curated_source_url_not_backed_by_manifest(tmp_path):
    root = tmp_path / "repo"
    vendor_root = root / "docs" / "rag" / "vendor"
    raw_root = vendor_root / "raw-sources"
    vendor_root.mkdir(parents=True)
    raw_root.mkdir()
    raw_file = raw_root / "templateflow_installation.html"
    raw_file.write_text("<html>official TemplateFlow installation</html>", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (vendor_root / "templateflow_official_cache_archive_client.md").write_text(
        "---\n"
        "source_type: rag_vendor\n"
        "source_url: https://www.templateflow.org/usage/client/\n"
        "raw_source_ids: templateflow_installation\n"
        "---\n"
        "# TemplateFlow\n",
        encoding="utf-8",
    )
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "templateflow_installation",
                        "vendor_doc": "templateflow_official_cache_archive_client.md",
                        "url": "https://github.com/templateflow/python-client/blob/master/docs/installation.rst",
                        "file": raw_file.name,
                        "source_type": "official_docs",
                        "retrieved_at": "2026-06-06T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(root=root, indexed_sources=[])

    assert status["curated_provenance_issues"] == [
        {
            "vendor_doc": "templateflow_official_cache_archive_client.md",
            "issue": "source_url_not_backed_by_raw_source_ids",
            "source_url": "https://www.templateflow.org/usage/client/",
            "raw_source_ids": ["templateflow_installation"],
        }
    ]

def test_vendor_raw_source_status_flags_raw_source_with_windows_path(tmp_path):
    root = tmp_path / "repo"
    raw_root = root / "docs" / "rag" / "vendor" / "raw-sources"
    raw_root.mkdir(parents=True)
    raw_file = raw_root / "openai_python_sdk_readme.md"
    raw_file.write_text("# OpenAI Python SDK raw source\n", encoding="utf-8")
    raw_bytes = raw_file.read_bytes()
    (raw_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "openai_python_sdk_readme",
                        "vendor_doc": "openai_official_responses_function_tools.md",
                        "url": "https://raw.githubusercontent.com/openai/openai-python/main/README.md",
                        "file": raw_file.name,
                        "source_type": "official_repository",
                        "retrieved_at": "2026-06-07T00:00:00Z",
                        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                        "bytes": len(raw_bytes),
                        "status": "downloaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    status = vendor_raw_source_status(
        root=root,
        indexed_sources=[r"docs\rag\vendor\raw-sources\openai_python_sdk_readme.md"],
    )

    assert status["raw_sources_indexed"] is True
    assert status["indexed_raw_sources"] == ["docs/rag/vendor/raw-sources/openai_python_sdk_readme.md"]
