from app.workflows.registry import (
    allowed_runtime_workflows,
    get_workflow,
    list_workflows,
    resolve_runtime_workflow_type,
    workflow_public_metadata,
    workflow_public_metadata_for_record,
)
from app.workflows.eligibility import build_workflow_eligibility


def test_workflow_registry_exposes_openai_style_contract_fields():
    workflow = get_workflow("bold_fmriprep_xcpd_report")

    assert workflow["type"] == "bold_fmriprep_xcpd_report"
    assert workflow["lane"] == "fixed_workflow"
    assert workflow["agent_selectable"] is True
    assert workflow["requires_confirmation"] is True
    assert workflow["runtime_class"]
    assert workflow["runtime_backend"] == "deployment_local_script_wrapper"
    assert workflow["execution_location"] == "deployment_server_local"
    assert workflow["external_worker_server_required"] is False
    assert workflow["result_summary_schema"] == "BOLD"
    assert workflow["runtime_images"] == {
        "fmriprep": "nipreps/fmriprep:25.2.5",
        "xcpd": "pennlinc/xcp_d:26.0.2",
    }
    assert workflow["input_requirements"]
    assert workflow["expected_outputs"]


def test_workflow_registry_exposes_structured_capabilities_for_agent_selection():
    workflow = get_workflow("bold_fmriprep_xcpd_report")

    assert workflow["display_name"] == "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report"
    assert workflow["workflow_family"] == "bold"
    assert workflow["workflow_role"] == "complete_processing"
    assert workflow["is_report_only"] is False
    assert "full BOLD preprocessing" in workflow["capability_summary"]
    assert "derived metrics" in workflow["capability_summary"]
    assert "report" in workflow["capability_summary"]
    stage_names = [stage["name"] for stage in workflow["pipeline_stages"]]
    assert stage_names == ["BIDS preparation", "fMRIPrep preprocessing", "XCP-D postprocessing", "result packaging"]
    assert "preprocessed BOLD derivatives" in workflow["primary_outputs"]
    assert "ALFF/fALFF/ReHo and connectivity metrics" in workflow["primary_outputs"]
    assert "container-native fMRIPrep and XCP-D QC artifacts" in workflow["qc_outputs"]
    assert "HTML scientific report" in workflow["report_outputs"]
    assert "report_only" not in workflow["agent_selection_aliases"]


def test_agent_selectable_workflows_have_capability_metadata_not_name_only():
    workflows = list_workflows(lane="fixed_workflow", agent_selectable=True)

    for workflow in workflows:
        assert workflow["display_name"]
        assert workflow["capability_summary"]
        assert workflow["workflow_family"] == workflow["modality"].lower()
        assert workflow["workflow_role"] in {"complete_processing", "anat_processing"}
        assert workflow["pipeline_stages"]
        assert workflow["primary_outputs"]
        assert isinstance(workflow["qc_outputs"], list)
        assert isinstance(workflow["report_outputs"], list)
        assert isinstance(workflow["limitations"], list)
        assert isinstance(workflow["agent_selection_aliases"], list)


def test_all_fixed_workflows_have_structured_display_metadata_without_renaming_ids():
    workflows = list_workflows(lane="fixed_workflow")
    required_fields = (
        "display_name",
        "capability_summary",
        "workflow_family",
        "workflow_role",
        "pipeline_stages",
        "primary_outputs",
        "qc_outputs",
        "report_outputs",
        "limitations",
        "is_report_only",
    )

    assert workflows
    for workflow in workflows:
        for field in required_fields:
            assert field in workflow, f"{workflow['type']} missing {field}"
        assert workflow["type"]
        assert workflow["runtime_workflow_type"]
        assert workflow["type"] != workflow["display_name"]
        assert workflow["workflow_family"] in {"t1", "bold", "dwi", "dicom", "other"}
        assert workflow["workflow_role"] in {
            "anat_processing",
            "complete_processing",
            "preprocessing",
            "metrics",
            "validation",
        }
        assert isinstance(workflow["pipeline_stages"], list) and workflow["pipeline_stages"]
        assert all(stage.get("name") and stage.get("purpose") for stage in workflow["pipeline_stages"])
        assert isinstance(workflow["primary_outputs"], list)
        assert isinstance(workflow["qc_outputs"], list)
        assert isinstance(workflow["report_outputs"], list)
        assert isinstance(workflow["limitations"], list)
        assert isinstance(workflow["is_report_only"], bool)


def test_workflow_public_metadata_exposes_stable_id_runtime_alias_and_lane_boundaries():
    metadata = workflow_public_metadata("t1_deepprep_anat_report")

    assert metadata["workflow_type"] == "t1_deepprep_anat_report"
    assert metadata["runtime_workflow_type"] == "t1_deepprep"
    assert metadata["lane"] == "fixed_workflow"
    assert metadata["status"] == "production"
    assert metadata["agent_selectable"] is True
    assert metadata["requires_confirmation"] is True
    assert metadata["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert metadata["is_report_only"] is False
    assert metadata["workflow_type"] != metadata["display_name"]


def test_public_metadata_for_runtime_record_keeps_agent_selectable_stable_workflow_boundary():
    metadata = workflow_public_metadata("t1_deepprep_validate")
    record_metadata = workflow_public_metadata_for_record("t1_deepprep", "t1_deepprep")

    assert metadata["workflow_type"] == "t1_deepprep_validate"
    assert metadata["agent_selectable"] is False
    assert metadata["requires_confirmation"] is True
    assert record_metadata["workflow_type"] == "t1_deepprep_anat_report"
    assert record_metadata["runtime_workflow_type"] == "t1_deepprep"
    assert record_metadata["agent_selectable"] is True
    assert record_metadata["is_report_only"] is False


def test_workflow_eligibility_items_include_public_metadata_without_replacing_machine_id():
    eligibility = build_workflow_eligibility(
        {
            "id": 101,
            "modality": "T1",
            "sequence_label": "T1w_MPRAGE",
            "supported_for_processing": True,
            "metadata": {},
        }
    )

    recommendation = eligibility["primary_recommendation"]

    assert recommendation["workflow_type"] == "t1_deepprep_anat_report"
    assert recommendation["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert recommendation["workflow_metadata"]["runtime_workflow_type"] == "t1_deepprep"
    assert recommendation["workflow_metadata"]["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert recommendation["workflow_metadata"]["agent_selectable"] is True
    assert recommendation["workflow_metadata"]["is_report_only"] is False
    assert eligibility["production_task_created"] is False


def test_fixed_workflow_runtime_images_are_version_locked():
    workflows = list_workflows(lane="fixed_workflow")

    for workflow in workflows:
        for image in (workflow.get("runtime_images") or {}).values():
            image_tail = image.rsplit("/", 1)[-1]
            assert "@sha256:" in image or ":" in image_tail, f"{workflow['type']} image is untagged: {image}"
            assert ":latest" not in image and not image.endswith(":latest"), f"{workflow['type']} image must not use latest: {image}"


def test_workflow_registry_filters_agent_selectable_fixed_lane():
    workflows = list_workflows(lane="fixed_workflow", agent_selectable=True)
    workflow_types = {workflow["type"] for workflow in workflows}

    assert "t1_deepprep_anat_report" in workflow_types
    assert "bold_fmriprep_xcpd_report" in workflow_types
    assert "dwi_fast_gpu_dti" in workflow_types
    assert "dwi_fast_gpu_dti_validate" not in workflow_types
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
    assert workflow["runtime_backend"] == "deployment_local_script_wrapper"
    assert workflow["agent_selectable"] is False
    assert "bold_fmriprep_xcpd_report_validate" in allowed_runtime_workflows()
