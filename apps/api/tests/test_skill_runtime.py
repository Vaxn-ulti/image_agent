from app.agent.skill_loader import load_skill_context, select_skill


def test_select_skill_routes_core_intents():
    assert select_skill("Please run BOLD fMRIPrep XCP-D", {"intent": "run_workflow"}) == "image-agent-workflow-runner"
    assert select_skill("Explain this result summary", {"intent": "inspect_result"}) == "image-agent-result-reviewer"
    assert select_skill("Add this vendor document to RAG", {"intent": "curate_rag"}) == "image-agent-rag-curator"
    assert select_skill("How should we change the agent architecture?", {"intent": "architect"}) == "image-agent-architect"
    assert select_skill("What is the current task status?", {"intent": "answer_question"}) == "image-agent-operator"


def test_load_skill_context_reads_skill_and_declared_references():
    context = load_skill_context("image-agent-workflow-runner")

    assert context["name"] == "image-agent-workflow-runner"
    assert "SKILL.md" in context["skill_path"]
    assert context["body"]
    assert context["references"]
    assert any(ref["path"].endswith("registry-and-preflight.md") for ref in context["references"])
