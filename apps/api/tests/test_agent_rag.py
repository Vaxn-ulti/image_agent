from app.agent import rag_orchestration
from app.agent.deepseek import SYSTEM_PROMPT


def test_agent_grounding_policy_prioritizes_backend_records_over_rag():
    policy = rag_orchestration.grounding_policy()

    assert policy["source_priority"][0] == "backend_task_records"
    assert "rag_documents" in policy["source_priority"]
    assert policy["rag_may_override_backend"] is False


def test_agent_dependency_status_reports_langgraph_and_llamaindex_keys():
    status = rag_orchestration.dependency_status()

    assert "langgraph" in status
    assert "llama_index" in status
    assert "available" in status["langgraph"]
    assert "available" in status["llama_index"]


def test_deepseek_system_prompt_matches_fixed_workflow_support():
    assert "BOLD/fMRI DeepPrep preprocessing" in SYSTEM_PROMPT
    assert "ALFF" in SYSTEM_PROMPT
    assert "dwi_fast_gpu_dti" in SYSTEM_PROMPT
    assert "Backend DB task/output records outrank retrieved documents" in SYSTEM_PROMPT


def test_build_rag_response_answers_dwi_workflow_capability_from_workflow_doc(tmp_path):
    doc = tmp_path / "docs" / "rag" / "workflows" / "dwi_fast_gpu_dti.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nsource_type: rag_workflow\nworkflow_type: dwi_fast_gpu_dti\n---\n"
        "# DWI Fast GPU DTI Workflow RAG\n"
        "The workflow produces FA/MD/AD/RD maps, atlas regional TSV tables, QC/provenance, and an HTML report. "
        "It is not full QSIPrep and not full QSIRecon. It requires DWI NIfTI, bval, bvec, and JSON metadata.\n",
        encoding="utf-8",
    )

    response = rag_orchestration.build_rag_response(
        "What does the DWI fast GPU DTI workflow produce?",
        root=tmp_path,
        backend_context={"tasks": []},
    )

    assert response["citations"][0]["path"].endswith("dwi_fast_gpu_dti.md")
    assert "FA/MD/AD/RD maps" in response["answer"]
    assert "atlas" in response["answer"]
    assert "not full QSIPrep" in response["answer"]


def test_build_rag_response_answers_upload_requirements_from_modalities_doc(tmp_path):
    doc = tmp_path / "docs" / "rag" / "data-requirements" / "modalities-bids.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nsource_type: rag_data_requirement\n---\n"
        "# Modalities and BIDS Requirements RAG\n"
        "DWI requires sub-01_dwi.nii.gz, sub-01_dwi.bval, sub-01_dwi.bvec, and sub-01_dwi.json. "
        "T1 uses a T1w NIfTI with matching JSON. BOLD uses a bold NIfTI with task JSON metadata.\n",
        encoding="utf-8",
    )

    response = rag_orchestration.build_rag_response(
        "What uploads are required for DWI sidecar sets?",
        root=tmp_path,
        backend_context={"tasks": []},
    )

    assert response["citations"][0]["path"].endswith("modalities-bids.md")
    assert "DWI NIfTI" in response["answer"]
    assert "bval" in response["answer"]
    assert "bvec" in response["answer"]
    assert "JSON sidecar" in response["answer"]


def test_build_rag_response_answers_non_diagnostic_policy_from_safety_doc(tmp_path):
    doc = tmp_path / "docs" / "rag" / "safety" / "non-diagnostic.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "---\nsource_type: rag_safety\npolicy: non_diagnostic\n---\n"
        "# Non-Diagnostic Safety RAG\n"
        "The image_agent is not a clinician and must not diagnose from workflow outputs. "
        "Clinical interpretation should come from a qualified radiologist or clinician.\n",
        encoding="utf-8",
    )

    response = rag_orchestration.build_rag_response(
        "Can Image Agent diagnose dementia from these FA values?",
        root=tmp_path,
        backend_context={"tasks": []},
    )

    assert response["citations"][0]["path"].endswith("non-diagnostic.md")
    assert "must not diagnose" in response["answer"]
    assert "qualified radiologist or clinician" in response["answer"]
