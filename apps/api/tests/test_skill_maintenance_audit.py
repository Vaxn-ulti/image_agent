import json

from apps.api.scripts.audit_skill_maintenance import audit_skill_maintenance


def test_skill_routing_matrix_covers_image_agent_skills():
    matrix_path = "docs/skills/maintenance/routing-matrix.json"
    with open(matrix_path, "r", encoding="utf-8") as handle:
        matrix = json.load(handle)

    skills = {item["skill_name"]: item for item in matrix["skills"]}
    expected = {
        "image-agent-operator",
        "image-agent-architect",
        "image-agent-developer",
        "image-agent-workflow-runner",
        "image-agent-result-reviewer",
        "image-agent-rag-curator",
        "neuroimaging-workflow-runner",
    }

    assert matrix["schema_version"] == 1
    assert set(skills) == expected
    for skill_name, item in skills.items():
        assert item["primary_triggers"], skill_name
        assert item["owns"], skill_name
        assert item["defers_to"] != [skill_name]
    assert "dwi_fast_gpu_dti" in json.dumps(matrix)
    assert "legacy QSIPrep/QSIRecon" in json.dumps(matrix)


def test_skill_maintenance_audit_passes_current_repository():
    result = audit_skill_maintenance(".")

    assert result["status"] == "passed"
    assert result["routing_matrix"]["covered_skill_count"] == 7
    assert result["skills"]["checked_skill_count"] == 7
    assert result["references"]["checked_reference_count"] >= 25
    assert result["references"]["long_reference_count"] >= 2
    assert result["references"]["long_references_with_toc"] == result["references"]["long_reference_count"]
    assert result["evals"]["skills_with_required_categories"] == 7
    assert result["findings"] == []
