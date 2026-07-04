import json

from app.agent import tools
from app.agent import tool_registry
from app.workflows.remote_scripts import BOLD_REQUIRED_TEMPLATEFLOW_FILES


def _write_required_templateflow_files(root):
    for relative_path in BOLD_REQUIRED_TEMPLATEFLOW_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"templateflow")


def test_read_project_context_includes_series_tasks_outputs_and_workflows(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "PROJECTS_ROOT", tmp_path / "projects")
    sidecar = tmp_path / "sub-01_task-rest_bold.json"
    sidecar.write_text(json.dumps({"TaskName": "rest", "RepetitionTime": 2.0, "PrivateField": "hidden"}), encoding="utf-8")
    recorded_queries = []

    def fake_rows(sql, params=()):
        recorded_queries.append((sql, params))
        if "FROM projects" in sql:
            return [{"id": 7, "name": "demo"}]
        if "FROM imaging_series" in sql:
            return [{"id": 11, "modality": "BOLD", "metadata_json": "{}"}]
        if "FROM tasks" in sql:
            return [{"id": 21, "workflow_type": "bold_deepprep", "status": "completed", "progress": 100}]
        if "FROM outputs" in sql:
            return [{"task_id": 21, "output_type": "summary", "path": "summary.json", "metadata_json": "{}"}]
        if "FROM files" in sql:
            return [{"id": 31, "project_id": 7, "original_name": "sub-01_task-rest_bold.json", "file_type": "JSON", "size": 42, "sha256": "abc", "storage_path": str(sidecar), "created_at": "2026-06-22T00:00:00"}]
        return []

    context = tools.read_project_context(project_id=7, rows_fn=fake_rows, workflows=[{"type": "bold_deepprep"}])

    assert context["project"] == {"id": 7, "name": "demo"}
    assert context["series"][0]["modality"] == "BOLD"
    assert context["tasks"][0]["id"] == 21
    assert context["outputs"][0]["metadata"] == {}
    assert context["project_files"][0]["json_summary"] == {"RepetitionTime": 2.0, "TaskName": "rest"}
    assert "storage_path" not in context["project_files"][0]
    assert context["workflows"] == [{"type": "bold_deepprep"}]
    assert recorded_queries


def test_preflight_workflow_blocks_modality_mismatch():
    context = {
        "series": [{"id": 11, "modality": "T1", "supported_for_processing": 1}],
        "workflows": [{"type": "bold_fmriprep_xcpd", "modality": "BOLD"}],
    }

    result = tools.preflight_workflow(context, series_id=11, workflow_type="bold_fmriprep_xcpd")

    assert result["ok"] is False
    assert result["blocking_errors"] == ["Workflow requires BOLD but series is T1"]


def test_preflight_workflow_accepts_matching_supported_series():
    context = {
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": [{"type": "bold_fmriprep_xcpd", "modality": "BOLD"}],
    }

    result = tools.preflight_workflow(context, series_id=11, workflow_type="bold_fmriprep_xcpd")

    assert result["ok"] is True
    assert result["requires_confirmation"] is True
    assert result["blocking_errors"] == []


def test_preflight_workflow_blocks_non_agent_selectable_registry_workflow():
    context = {
        "series": [{"id": 11, "modality": "T1", "supported_for_processing": 1}],
        "workflows": [],
    }

    result = tools.preflight_workflow(context, series_id=11, workflow_type="t1_deepprep_validate")

    assert result["ok"] is False
    assert result["action_lane"] == "fixed_workflow"
    assert any("not selectable for Agent production launch" in error for error in result["blocking_errors"])


def test_preflight_workflow_schema_exposes_only_fixed_workflows():
    spec = tool_registry.list_function_tools()
    preflight = next(item for item in spec if item["name"] == "preflight_workflow")
    workflow_enum = preflight["parameters"]["properties"]["workflow_type"]["enum"]

    assert "t1_deepprep_anat_report" in workflow_enum
    assert "dwi_fast_gpu_dti" in workflow_enum
    assert "t1_deepprep_mock" not in workflow_enum


def test_observe_repair_task_tool_is_exposed_as_read_only_contract():
    spec = tool_registry.list_function_tools()
    tool = next(item for item in spec if item["name"] == "observe_repair_task")

    assert tool["parameters"]["properties"]["task_id"]["type"] == "integer"
    assert "read-only" in tool["description"].lower()
    assert "never retries" in tool["description"].lower()
    assert "reruns" in tool["description"].lower()


def test_preflight_workflow_checks_remote_runtime_when_project_root_present(tmp_path, monkeypatch):
    private_root = tmp_path / "private-host-root"
    license_path = private_root / "license.txt"
    fmriprep_script = private_root / "run_fmriprep.sh"
    xcpd_script = private_root / "run_xcpd.sh"
    private_root.mkdir()
    license_path.write_text("license", encoding="utf-8")
    fmriprep_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    xcpd_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fmriprep_script.chmod(0o755)
    xcpd_script.chmod(0o755)
    templateflow = tmp_path / "templateflow"
    _write_required_templateflow_files(templateflow)
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    monkeypatch.setenv("IMAGE_AGENT_TEMPLATEFLOW_HOME", str(templateflow))
    context = {
        "project_root": str(tmp_path / "project"),
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": [],
    }

    result = tools.preflight_workflow(context, series_id=11, workflow_type="bold_fmriprep_xcpd_report")

    assert result["ok"] is True
    assert any(check["name"] == "deployment_local_fmriprep_script_exists" for check in result["checks"])
    assert "private-host-root" not in json.dumps(result)
    assert "run_fmriprep.sh" in json.dumps(result)


def test_parse_output_metadata_keeps_invalid_json_as_empty_dict():
    output = {"metadata_json": "{bad"}

    parsed = tools.parse_output(output)

    assert parsed["metadata"] == {}
    assert "metadata_json" not in parsed


def test_list_workflows_filters_by_lane_and_agent_selectable():
    workflows = [
        {"type": "fixed", "lane": "fixed_workflow", "agent_selectable": True},
        {"type": "hidden", "lane": "fixed_workflow", "agent_selectable": False},
        {"type": "incubating", "lane": "toolchain_incubation", "agent_selectable": True},
    ]

    result = tools.list_workflows(workflows=workflows, lane="fixed_workflow", agent_selectable=True)

    assert result == [{"type": "fixed", "lane": "fixed_workflow", "agent_selectable": True}]


def test_list_data_candidates_scores_registered_series_without_sensitive_metadata(tmp_path):
    project_root = tmp_path / "projects"
    storage = project_root / "7" / "raw" / "bold.nii.gz"
    storage.parent.mkdir(parents=True)
    storage.write_bytes(b"nifti")

    def fake_rows(sql, params=()):
        assert "FROM imaging_series" in sql
        return [
            {
                "id": 11,
                "project_id": 7,
                "file_id": 3,
                "bids_path": str(project_root / "7" / "bids"),
                "sequence_label": "rest_bold",
                "supported_for_processing": 1,
                "unsupported_reason": "",
                "modality": "BOLD",
                "format": "NIFTI_BIDS",
                "confidence": 0.96,
                "metadata_json": json.dumps({"password": "hide-me", "TaskName": "rest", "dataset_description": True}),
                "status": "detected",
                "created_at": "now",
                "original_name": "bold.nii.gz",
                "storage_path": str(storage),
                "file_type": "NIFTI",
                "size": 5,
                "sha256": "abc",
            }
        ]

    result = tools.list_data_candidates(
        7,
        rows_fn=fake_rows,
        projects_root=project_root,
        workflow_type="bold_fmriprep_xcpd_report",
    )
    candidate = result["candidates"][0]

    assert result["production_task_created"] is False
    assert candidate["recommended_for_incubation"] is True
    assert candidate["file"]["storage_path_scope"] == "inside_projects_root"
    assert candidate["readiness"]["score"] >= 75
    assert "password" not in candidate["data_layout"]["metadata_keys"]
    assert "hide-me" not in json.dumps(result)


def test_select_incubation_dataset_prefers_matching_supported_candidate(tmp_path):
    project_root = tmp_path / "projects"
    bold = project_root / "7" / "raw" / "bold.nii.gz"
    t1 = project_root / "7" / "raw" / "t1.nii.gz"
    bold.parent.mkdir(parents=True)
    bold.write_bytes(b"bold")
    t1.write_bytes(b"t1")

    def fake_rows(sql, params=()):
        return [
            {
                "id": 12,
                "project_id": 7,
                "file_id": 4,
                "bids_path": "",
                "sequence_label": "anat",
                "supported_for_processing": 1,
                "unsupported_reason": "",
                "modality": "T1",
                "format": "NIFTI",
                "confidence": 0.9,
                "metadata_json": "{}",
                "status": "detected",
                "created_at": "now",
                "original_name": "t1.nii.gz",
                "storage_path": str(t1),
                "file_type": "NIFTI",
                "size": 2,
                "sha256": "t1",
            },
            {
                "id": 11,
                "project_id": 7,
                "file_id": 3,
                "bids_path": str(project_root / "7" / "bids"),
                "sequence_label": "rest_bold",
                "supported_for_processing": 1,
                "unsupported_reason": "",
                "modality": "BOLD",
                "format": "NIFTI_BIDS",
                "confidence": 0.96,
                "metadata_json": json.dumps({"dataset_description": True}),
                "status": "detected",
                "created_at": "now",
                "original_name": "bold.nii.gz",
                "storage_path": str(bold),
                "file_type": "NIFTI",
                "size": 4,
                "sha256": "bold",
            },
        ]

    result = tools.select_incubation_dataset(
        7,
        rows_fn=fake_rows,
        projects_root=project_root,
        workflow_type="bold_fmriprep_xcpd_report",
    )

    assert result["status"] == "selected"
    assert result["selected"]["series_id"] == 11
    assert result["selected"]["modality"] == "BOLD"
    assert result["production_task_created"] is False


def test_read_task_and_events_include_remote_wrapper_logs(tmp_path, monkeypatch):
    projects_root = tmp_path / "projects"
    main_log = tmp_path / "task.log"
    remote_log_dir = projects_root / "7" / "derivatives" / "118" / "output" / "logs"
    main_log.write_text("main progress at /home/yyf/project/image_agent/private\n", encoding="utf-8")
    remote_log_dir.mkdir(parents=True)
    (remote_log_dir / "fmriprep.log").write_text("fmriprep live log at C:/Users/A/private\n", encoding="utf-8")
    (remote_log_dir / "xcpd_fmriprep.log").write_text("xcp-d live log\n", encoding="utf-8")

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "runtime_workflow_type": "bold_fmriprep_xcpd_report_validate",
                    "status": "running",
                    "progress": 20,
                    "error_message": None,
                    "log_path": str(main_log),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": None,
                }
            ]
        return []

    task = tools.read_task(118, rows_fn=fake_rows)
    events = tools.read_task_events(118, rows_fn=fake_rows, projects_root=projects_root)

    assert task["status"] == "ok"
    assert task["task"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert task["task"]["runtime_workflow_type"] == "bold_fmriprep_xcpd_report_validate"
    assert "log_path" not in task["task"]
    assert str(main_log) not in json.dumps(task)
    assert "main progress" in events["main_log"]["tail"]
    assert "path" not in events["main_log"]
    assert "log_path" not in events["task"]
    assert "/home/yyf/project/image_agent" not in json.dumps(events)
    assert "C:/Users/A/private" not in json.dumps(events)
    assert "[redacted-host-path]" in events["main_log"]["tail"]
    assert events["remote_logs"][0]["name"] == "fmriprep.log"
    assert "fmriprep live log" in events["remote_logs"][0]["tail"]
    assert "path" not in events["remote_logs"][0]
    stages = {item["name"]: item["source_stage"] for item in events["remote_logs"]}
    assert stages["fmriprep.log"] == "fmriprep"
    assert stages["xcpd_fmriprep.log"] == "xcpd"
    assert any(event["type"] == "task.remote_log" for event in events["events"])


def test_read_task_events_falls_back_to_main_log_when_remote_logs_absent(tmp_path):
    projects_root = tmp_path / "projects"
    main_log = tmp_path / "task.log"
    main_log.write_text(
        "main pipeline log at /home/yyf/project/image_agent/private\n"
        "completed without nested native logs\n",
        encoding="utf-8",
    )
    (projects_root / "7" / "derivatives" / "119" / "output").mkdir(parents=True)

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 119,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "t1_deepprep_anat_report",
                    "runtime_workflow_type": "t1_deepprep",
                    "status": "completed",
                    "progress": 100,
                    "error_message": None,
                    "log_path": str(main_log),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": "now",
                }
            ]
        return []

    events = tools.read_task_events(119, rows_fn=fake_rows, projects_root=projects_root)
    observe = tools.observe_repair_task(119, rows_fn=fake_rows, projects_root=projects_root)
    serialized = json.dumps(observe)

    assert any(event["type"] == "task.remote_log" for event in events["events"])
    assert events["remote_logs"][0]["name"] == "task.log"
    assert events["remote_logs"][0]["source_stage"] == "pipeline_runner"
    assert "completed without nested native logs" in events["remote_logs"][0]["tail"]
    assert observe["remote_logs"][0]["source_stage"] == "pipeline_runner"
    assert "/home/yyf/project/image_agent" not in serialized


def test_observe_repair_task_redacts_sensitive_tool_payload_without_creating_tasks(tmp_path):
    projects_root = tmp_path / "projects"
    main_log = tmp_path / "task.log"
    remote_log_dir = projects_root / "7" / "derivatives" / "118" / "output" / "logs"
    main_log.write_text(
        "OPENAI_API_KEY=sk-agent-secret failed for patient-118 at C:/Users/A/private\n",
        encoding="utf-8",
    )
    remote_log_dir.mkdir(parents=True)
    (remote_log_dir / "fmriprep.log").write_text(
        "remote TOKEN=repair-secret wrote /home/yyf/project/image_agent/private\n",
        encoding="utf-8",
    )
    counts = {"tasks": 1, "outputs": 1}

    def fake_rows(sql, params=()):
        if "COUNT(*) AS count FROM tasks" in sql:
            return [{"count": counts["tasks"]}]
        if "COUNT(*) AS count FROM outputs" in sql:
            return [{"count": counts["outputs"]}]
        if "FROM tasks" in sql:
            return [
                {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "runtime_workflow_type": "bold_fmriprep_xcpd_report_validate",
                    "status": "failed",
                    "progress": 20,
                    "error_message": "failed at /home/yyf/project/image_agent/private/patient-118",
                    "log_path": str(main_log),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": "now",
                }
            ]
        if "FROM outputs" in sql:
            return [
                {
                    "task_id": 118,
                    "output_type": "json",
                    "path": str(tmp_path / "missing_result_summary.json"),
                    "metadata_json": '{"kind":"result_summary"}',
                }
            ]
        return []

    before_tasks = fake_rows("SELECT COUNT(*) AS count FROM tasks")[0]["count"]
    before_outputs = fake_rows("SELECT COUNT(*) AS count FROM outputs")[0]["count"]

    result = tools.observe_repair_task(118, rows_fn=fake_rows, projects_root=projects_root)

    serialized = json.dumps(result)
    assert result["policy"] == "read_only_observe_repair"
    assert result["auto_rerun_allowed"] is False
    assert result["task_creation_allowed"] is False
    assert result["forbidden_actions"] == ["auto_retry", "auto_rerun", "task_creation"]
    assert result["production_task_created"] is False
    assert result["requires_preflight_before_retry"] is True
    assert result["requires_human_confirmation_before_retry"] is True
    assert any(item["kind"] == "failed_task_repair_plan" for item in result["repair_suggestions"])
    assert any(item["kind"] == "result_summary_repair_plan" for item in result["repair_suggestions"])
    assert "sk-agent-secret" not in serialized
    assert "repair-secret" not in serialized
    assert "patient-118" not in serialized
    assert "C:/Users/A/private" not in serialized
    assert "/home/yyf/project/image_agent" not in serialized
    assert "log_path" not in serialized
    assert before_tasks == fake_rows("SELECT COUNT(*) AS count FROM tasks")[0]["count"]
    assert before_outputs == fake_rows("SELECT COUNT(*) AS count FROM outputs")[0]["count"]


def test_read_task_enriches_historical_runtime_alias_with_public_workflow_metadata(tmp_path):
    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 41,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "t1_deepprep",
                    "runtime_workflow_type": "t1_deepprep",
                    "status": "completed",
                    "progress": 100,
                    "error_message": None,
                    "log_path": str(tmp_path / "task.log"),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": "later",
                }
            ]
        return []

    result = tools.read_task(41, rows_fn=fake_rows)

    assert result["status"] == "ok"
    assert result["task"]["workflow_type"] == "t1_deepprep"
    assert result["task"]["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert result["task"]["workflow_metadata"]["runtime_workflow_type"] == "t1_deepprep"
    assert result["task"]["workflow_metadata"]["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert result["task"]["workflow_metadata"]["is_report_only"] is False
    assert "log_path" not in result["task"]


def test_read_result_summary_prefers_registered_summary(tmp_path):
    summary = tmp_path / "bold_result_summary.json"
    summary.write_text(
        json.dumps(
            {
                "task_id": 118,
                "workflow_type": "bold_fmriprep_xcpd_report",
                "outputs": {"logs": []},
                "summary_path": str(summary),
            }
        ),
        encoding="utf-8",
    )

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "runtime_workflow_type": "bold_fmriprep_xcpd_report",
                    "status": "completed",
                    "progress": 100,
                    "error_message": None,
                    "log_path": str(tmp_path / "task.log"),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": "later",
                }
            ]
        if "FROM outputs" in sql:
            return [
                {
                    "task_id": 118,
                    "output_type": "json",
                    "path": str(summary),
                    "metadata_json": json.dumps({"kind": "result_summary"}),
                }
            ]
        return []

    result = tools.read_result_summary(118, rows_fn=fake_rows, projects_root=tmp_path / "projects")

    assert result["status"] == "ok"
    assert result["result_summary"]["task_id"] == 118
    assert result["result_summary"]["workflow_metadata"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert result["result_summary"]["workflow_metadata"]["display_name"] == "BOLD fMRIPrep + XCP-D processing, metrics, QC, and report"
    assert result["result_summary"]["workflow_metadata"]["is_report_only"] is False
    assert "summary_path" not in result["result_summary"]


def test_read_result_summary_fallback_enriches_historical_runtime_alias(tmp_path):
    projects_root = tmp_path / "projects"
    summary_dir = projects_root / "7" / "derivatives" / "41" / "output" / "summary"
    summary_dir.mkdir(parents=True)
    summary = summary_dir / "t1_result_summary.json"
    summary.write_text(
        json.dumps(
            {
                "task_id": 41,
                "workflow_type": "t1_deepprep",
                "outputs": {"logs": []},
                "summary_path": str(summary),
            }
        ),
        encoding="utf-8",
    )

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 41,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "t1_deepprep",
                    "runtime_workflow_type": "t1_deepprep",
                    "status": "completed",
                    "progress": 100,
                    "error_message": None,
                    "log_path": str(tmp_path / "task.log"),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": "later",
                }
            ]
        return []

    result = tools.read_result_summary(41, rows_fn=fake_rows, projects_root=projects_root)

    assert result["status"] == "ok"
    assert result["result_summary"]["workflow_type"] == "t1_deepprep"
    assert result["result_summary"]["workflow_metadata"]["workflow_type"] == "t1_deepprep_anat_report"
    assert result["result_summary"]["workflow_metadata"]["runtime_workflow_type"] == "t1_deepprep"
    assert result["result_summary"]["workflow_metadata"]["display_name"] == "T1 DeepPrep anatomical processing, QC, and report"
    assert result["result_summary"]["workflow_metadata"]["is_report_only"] is False
    assert "summary_path" not in result["result_summary"]


def test_read_result_summary_reports_missing_summary(tmp_path):
    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 119,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "status": "running",
                    "progress": 20,
                    "error_message": None,
                    "log_path": str(tmp_path / "task.log"),
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": None,
                }
            ]
        return []

    result = tools.read_result_summary(119, rows_fn=fake_rows, projects_root=tmp_path / "projects")

    assert result["status"] == "not_found"
    assert result["result_summary"] is None


def test_read_project_context_includes_runtime_workflow_type(tmp_path):
    project_root = tmp_path / "projects"

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
                    "runtime_workflow_type": "bold_fmriprep_xcpd_report_validate",
                    "status": "running",
                    "progress": 20,
                    "error_message": None,
                    "created_at": "now",
                    "started_at": "now",
                    "finished_at": None,
                }
            ]
        if "FROM projects" in sql:
            return [{"id": 7}]
        if "FROM imaging_series" in sql:
            return []
        if "FROM outputs" in sql:
            return []
        return []

    context = tools.read_project_context(7, rows_fn=fake_rows, workflows=[], projects_root=project_root)

    assert context["tasks"][0]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert context["tasks"][0]["runtime_workflow_type"] == "bold_fmriprep_xcpd_report_validate"


def test_create_workflow_task_requires_approved_fixed_workflow_confirmation():
    calls = []

    def fake_create(series_id, workflow_type, qsiprep_task_id=None):
        calls.append((series_id, workflow_type, qsiprep_task_id))
        return {"id": 99, "series_id": series_id, "workflow_type": workflow_type, "status": "queued"}

    rejected = tools.create_workflow_task(
        confirmation={"approved": False, "workflow_type": "t1_deepprep_anat_report", "series_id": 11},
        create_task_fn=fake_create,
    )
    incubating = tools.create_workflow_task(
        confirmation={
            "approved": True,
            "workflow_type": "toolchain_proposal",
            "series_id": 11,
            "action_lane": "toolchain_incubation",
        },
        create_task_fn=fake_create,
    )
    debug_mock = tools.create_workflow_task(
        confirmation={
            "approved": True,
            "workflow_type": "t1_deepprep_mock",
            "series_id": 11,
            "action_lane": "toolchain_incubation",
        },
        create_task_fn=fake_create,
    )
    non_selectable = tools.create_workflow_task(
        confirmation={
            "approved": True,
            "workflow_type": "t1_deepprep_validate",
            "series_id": 11,
            "action_lane": "fixed_workflow",
            "preflight": {
                "ok": True,
                "workflow_type": "t1_deepprep_validate",
                "runtime_workflow_type": "t1_deepprep_validate",
            },
        },
        create_task_fn=fake_create,
    )
    missing_preflight = tools.create_workflow_task(
        confirmation={
            "approved": True,
            "workflow_type": "t1_deepprep_anat_report",
            "series_id": 11,
            "action_lane": "fixed_workflow",
        },
        create_task_fn=fake_create,
    )
    accepted = tools.create_workflow_task(
        confirmation={
            "approved": True,
            "workflow_type": "t1_deepprep_anat_report",
            "series_id": 11,
            "action_lane": "fixed_workflow",
            "preflight": {
                "ok": True,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep",
            },
        },
        create_task_fn=fake_create,
    )

    assert rejected["status"] == "confirmation_required"
    assert incubating["status"] == "blocked"
    assert debug_mock["status"] == "blocked"
    assert non_selectable["status"] == "blocked"
    assert non_selectable["production_task_created"] is False
    assert "not selectable for Agent production launch" in non_selectable["message"]
    assert missing_preflight["status"] == "blocked"
    assert missing_preflight["production_task_created"] is False
    assert "preflight" in missing_preflight["message"]
    assert accepted["status"] == "task_created"
    assert accepted["task"]["workflow_type"] == "t1_deepprep"
    assert calls == [(11, "t1_deepprep", None)]


def test_toolchain_incubation_tools_return_non_production_contracts():
    proposal = tools.propose_toolchain(
        objective="run a new BOLD cleanup chain",
        input_modality="BOLD",
        primitives=["stage_bids", "run_fmriprep", "run_xcpd"],
    )
    validation = tools.sandbox_validate_toolchain(proposal)
    promotion = tools.promote_toolchain_to_workflow(proposal, approved=False)

    assert proposal["lane"] == "toolchain_incubation"
    assert validation["production_task_created"] is False
    assert validation["container_inspection"]["status"] == "not_required"
    assert promotion["status"] == "needs_human_approval"


def test_sandbox_validate_toolchain_can_run_backend_container_inspection():
    proposal = tools.propose_toolchain(
        objective="inspect fMRIPrep image",
        input_modality="BOLD",
        script_text="docker run --rm -e API_TOKEN=do-not-leak -v /sandbox/bids:/data:ro nipreps/fmriprep:latest /data /out participant",
    )
    commands = []

    def fake_runner(command):
        commands.append(command)
        return (
            0,
            json.dumps(
                [
                    {
                        "Id": "sha256:abc",
                        "RepoDigests": ["nipreps/fmriprep@sha256:def"],
                        "Created": "2026-06-01T00:00:00Z",
                        "Config": {
                            "Entrypoint": ["fmriprep"],
                            "Cmd": ["--help"],
                            "Env": ["API_TOKEN=do-not-leak", "PATH=/usr/local/bin"],
                            "Labels": {"org.opencontainers.image.version": "25.0.0"},
                            "WorkingDir": "/work",
                            "User": "1000",
                        },
                    }
                ]
            ),
            "",
        )

    validation = tools.sandbox_validate_toolchain(proposal, inspection_runner=fake_runner)
    inspection = validation["container_inspection"]["inspections"][0]

    assert commands == [["docker", "image", "inspect", "nipreps/fmriprep:latest"]]
    assert validation["container_inspection"]["status"] == "passed"
    assert validation["container_inspection"]["production_task_created"] is False
    assert inspection["metadata"]["image_id"] == "sha256:abc"
    assert inspection["metadata"]["repo_digests"] == ["nipreps/fmriprep@sha256:def"]
    assert inspection["metadata"]["entrypoint"] == ["fmriprep"]
    assert inspection["metadata"]["env_keys"] == ["API_TOKEN", "PATH"]
    assert "do-not-leak" not in json.dumps(validation)
    assert {"name": "container_image_inspection", "status": "passed"} in validation["checks"]


def test_toolchain_promotion_requires_repeated_validation_and_only_returns_suggestion():
    proposal = tools.propose_toolchain(
        objective="run a new BOLD cleanup chain",
        input_modality="BOLD",
        primitives=["stage_bids", "run_fmriprep", "run_xcpd"],
    )

    blocked = tools.promote_toolchain_to_workflow(proposal, approved=True)
    proposal["validation_runs"] = [{"status": "passed"}, {"status": "passed"}]
    proposal["human_reviews"] = [{"decision": "approved", "reviewer": "operator"}]
    ready = tools.promote_toolchain_to_workflow(proposal, approved=True)

    assert blocked["status"] == "promotion_blocked"
    assert blocked["production_task_created"] is False
    assert ready["status"] == "promotion_suggestion_ready"
    assert ready["artifact_drafts"]["workflow_registry_entry"]["status"] == "draft_from_incubation"
    assert ready["artifact_drafts"]["workflow_registry_entry"]["agent_selectable"] is False
    assert ready["artifact_drafts"]["preflight_contract"]["must_pass_before_confirmation"] is True
    assert ready["production_enabled"] is False
    assert ready["production_task_created"] is False
