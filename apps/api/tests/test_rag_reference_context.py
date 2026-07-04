from app.agent.rag_orchestration import retrieve_reference_context


def test_retrieve_reference_context_returns_file_search_like_metadata(tmp_path):
    rag_doc = tmp_path / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    skill_ref = tmp_path / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "workflow-registry-contract.md"
    rag_doc.parent.mkdir(parents=True)
    skill_ref.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\n---\n"
        "# BOLD fMRIPrep XCP-D\nXCP-D outputs motion metrics, connectivity tables, and HTML reports.\n",
        encoding="utf-8",
    )
    skill_ref.write_text(
        "---\nsource_type: skill_reference\nskill: image-agent-workflow-runner\n---\n"
        "# Workflow registry contract\nFixed workflows require preflight and confirmation.\n",
        encoding="utf-8",
    )

    result = retrieve_reference_context("XCP-D fixed workflow confirmation", root=tmp_path, limit=5)

    assert result["query"] == "XCP-D fixed workflow confirmation"
    assert result["results"]
    first = result["results"][0]
    assert {"source", "title", "snippet", "score", "metadata"} <= set(first)
    assert any(hit["metadata"].get("source_type") == "rag_workflow" for hit in result["results"])
    assert any(hit["metadata"].get("source_type") == "skill_reference" for hit in result["results"])


def test_retrieve_reference_context_uses_persistent_index_when_available(tmp_path):
    from app.agent.rag_index import build_local_rag_index

    rag_doc = tmp_path / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md"
    rag_doc.parent.mkdir(parents=True)
    rag_doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: bold_fmriprep_xcpd_report\nmodality: BOLD\n---\n"
        "# BOLD fMRIPrep XCP-D\nXCP-D outputs motion metrics and connectivity tables.\n",
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    result = retrieve_reference_context(
        "connectivity tables",
        root=tmp_path,
        filters={"workflow_type": "bold_fmriprep_xcpd_report"},
        limit=2,
    )

    assert result["mode"] in {"elasticsearch_hybrid_fallback", "llama_index", "local_persistent_index"}
    assert result["results"]
    assert result["results"][0]["metadata"]["workflow_type"] == "bold_fmriprep_xcpd_report"


def test_retrieve_reference_context_pins_launchability_matrix_even_with_stale_index(tmp_path):
    from app.agent.rag_index import build_local_rag_index

    stale_doc = tmp_path / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry.md"
    stale_doc.parent.mkdir(parents=True)
    stale_doc.write_text(
        "---\nsource_type: skill_reference\n---\n"
        "# Registry\nQSIPrep and QSIRecon are workflow names in older notes.\n",
        encoding="utf-8",
    )
    build_local_rag_index(root=tmp_path, persist_dir=tmp_path / ".rag_index")

    matrix = tmp_path / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    matrix.parent.mkdir(parents=True)
    matrix.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: workflow_launchability_matrix\n---\n"
        "# Workflow Launchability Matrix\n"
        "MRIQC is incubation_reference, DPABI is unsupported_external, and QSIPrep is legacy explicit.\n",
        encoding="utf-8",
    )

    result = retrieve_reference_context(
        "Can Image Agent run MRIQC DPABI QSIPrep in production?",
        root=tmp_path,
        limit=3,
    )

    assert result["results"]
    assert result["results"][0]["source"].endswith("workflow_launchability_matrix.md")
    assert result["results"][0]["metadata"]["workflow_type"] == "workflow_launchability_matrix"
