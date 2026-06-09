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
