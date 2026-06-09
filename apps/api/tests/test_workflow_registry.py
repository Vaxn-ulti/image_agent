from app.workflows.registry import (
    allowed_runtime_workflows,
    get_workflow,
    list_workflows,
    resolve_runtime_workflow_type,
)


def test_workflow_registry_exposes_openai_style_contract_fields():
    workflow = get_workflow("bold_fmriprep_xcpd_report")

    assert workflow["type"] == "bold_fmriprep_xcpd_report"
    assert workflow["lane"] == "fixed_workflow"
    assert workflow["agent_selectable"] is True
    assert workflow["requires_confirmation"] is True
    assert workflow["runtime_class"]
    assert workflow["runtime_backend"] == "remote_script_wrapper"
    assert workflow["result_summary_schema"] == "BOLD"
    assert workflow["input_requirements"]
    assert workflow["expected_outputs"]


def test_workflow_registry_filters_agent_selectable_fixed_lane():
    workflows = list_workflows(lane="fixed_workflow", agent_selectable=True)
    workflow_types = {workflow["type"] for workflow in workflows}

    assert "t1_deepprep_anat_report" in workflow_types
    assert "bold_fmriprep_xcpd_report" in workflow_types
    assert all(workflow["lane"] == "fixed_workflow" for workflow in workflows)
    assert all(workflow["agent_selectable"] is True for workflow in workflows)


def test_incubation_workflows_are_not_production_executable():
    workflow = get_workflow("toolchain_proposal")

    assert workflow["lane"] == "toolchain_incubation"
    assert workflow["agent_selectable"] is True
    assert workflow["requires_confirmation"] is False
    assert workflow["status"] == "incubation"
    assert "toolchain_proposal" not in allowed_runtime_workflows()

    for workflow_type in (
        "dwi_qsiprep",
        "dwi_qsiprep_validate",
        "dwi_qsirecon",
        "dwi_qsirecon_validate",
        "dwi_qsi_full",
        "dwi_qsi_full_validate",
        "dicom_convert",
        "dicom_convert_validate",
    ):
        workflow = get_workflow(workflow_type)
        assert workflow["lane"] == "toolchain_incubation"
        assert workflow_type not in allowed_runtime_workflows()
        runtime_workflow_type = workflow.get("runtime_workflow_type")
        if runtime_workflow_type:
            assert runtime_workflow_type not in allowed_runtime_workflows()


def test_debug_mock_is_direct_api_runnable_but_not_agent_selectable():
    workflow = get_workflow("t1_deepprep_mock")

    assert workflow["lane"] == "toolchain_incubation"
    assert workflow["status"] == "debug_only"
    assert workflow["agent_selectable"] is False
    assert workflow["api_runnable"] is True
    assert "t1_deepprep_mock" in allowed_runtime_workflows()


def test_alias_workflow_resolves_to_runtime_workflow_type():
    assert resolve_runtime_workflow_type("t1_deepprep_anat_report") == "t1_deepprep"
    assert resolve_runtime_workflow_type("bold_fmriprep_xcpd_report") == "bold_fmriprep_xcpd_report"
    assert resolve_runtime_workflow_type("bold_fmriprep_xcpd_report_validate") == "bold_fmriprep_xcpd_report_validate"


def test_bold_fmriprep_xcpd_validate_is_runtime_allowed_but_not_agent_selectable():
    workflow = get_workflow("bold_fmriprep_xcpd_report_validate")

    assert workflow["lane"] == "fixed_workflow"
    assert workflow["runtime_backend"] == "remote_script_wrapper"
    assert workflow["agent_selectable"] is False
    assert "bold_fmriprep_xcpd_report_validate" in allowed_runtime_workflows()
