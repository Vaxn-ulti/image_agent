import json

from app.agent import tool_dispatcher
from app.agent.tool_dispatcher import dispatch_model_tool_calls, dispatch_tool_call


def test_dispatcher_runs_preflight_as_whitelisted_function_tool():
    context = {
        "project_id": 7,
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": [{"type": "bold_fmriprep_xcpd_report", "modality": "BOLD", "lane": "fixed_workflow"}],
    }

    result = dispatch_tool_call(
        "preflight_workflow",
        {"series_id": 11, "workflow_type": "bold_fmriprep_xcpd_report"},
        project_context=context,
        rag_root=".",
    )

    assert result["status"] == "ok"
    assert result["tool"] == "preflight_workflow"
    assert result["result"]["ok"] is True
    assert result["production_task_created"] is False


def test_dispatcher_blocks_unknown_and_unconfirmed_production_tools():
    unknown = dispatch_tool_call("shell", {"command": "docker ps"})
    production = dispatch_tool_call(
        "create_workflow_task",
        {
            "confirmation": {
                "approved": True,
                "action_lane": "fixed_workflow",
                "workflow_type": "t1_deepprep_anat_report",
                "series_id": 11,
            }
        },
    )

    assert unknown["status"] == "blocked"
    assert production["status"] == "blocked"
    assert production["production_task_created"] is False


def test_dispatcher_executes_read_tools_with_rows_fn_and_remote_log_context(tmp_path):
    projects_root = tmp_path / "projects"
    log_dir = projects_root / "7" / "derivatives" / "118" / "output" / "logs"
    main_log = tmp_path / "task.log"
    main_log.write_text("main task log\n", encoding="utf-8")
    log_dir.mkdir(parents=True)
    (log_dir / "fmriprep.log").write_text("remote fmriprep progress\n", encoding="utf-8")

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
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

    result = dispatch_tool_call(
        "read_task_events",
        {"task_id": 118},
        rows_fn=fake_rows,
        projects_root=projects_root,
    )

    assert result["status"] == "ok"
    assert result["result"]["status"] == "ok"
    assert result["result"]["remote_logs"][0]["name"] == "fmriprep.log"
    assert "remote fmriprep progress" in result["result"]["remote_logs"][0]["tail"]


def test_dispatcher_lists_and_selects_data_candidates_with_rows_fn(tmp_path):
    project_root = tmp_path / "projects"
    storage = project_root / "7" / "raw" / "bold.nii.gz"
    storage.parent.mkdir(parents=True)
    storage.write_bytes(b"bold")

    def fake_rows(sql, params=()):
        if "FROM imaging_series" in sql:
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
                    "metadata_json": json.dumps({"dataset_description": True}),
                    "status": "detected",
                    "created_at": "now",
                    "original_name": "bold.nii.gz",
                    "storage_path": str(storage),
                    "file_type": "NIFTI",
                    "size": 4,
                    "sha256": "bold",
                }
            ]
        return []

    missing_rows = dispatch_tool_call("list_data_candidates", {"project_id": 7})
    listed = dispatch_tool_call(
        "list_data_candidates",
        {"project_id": 7, "workflow_type": "bold_fmriprep_xcpd_report"},
        rows_fn=fake_rows,
        projects_root=project_root,
    )
    selected = dispatch_tool_call(
        "select_incubation_dataset",
        {"project_id": 7, "workflow_type": "bold_fmriprep_xcpd_report"},
        rows_fn=fake_rows,
        projects_root=project_root,
    )

    assert missing_rows["status"] == "blocked"
    assert listed["status"] == "ok"
    assert listed["result"]["candidates"][0]["recommended_for_incubation"] is True
    assert selected["result"]["status"] == "selected"
    assert selected["result"]["selected"]["series_id"] == 11
    assert selected["production_task_created"] is False


def test_dispatcher_handles_responses_tool_call_arguments_json():
    calls = [
        {
            "id": "call_1",
            "name": "list_workflows",
            "arguments": json.dumps({"lane": "fixed_workflow", "agent_selectable": True}),
        }
    ]

    trace = dispatch_model_tool_calls(calls)

    assert trace[0]["tool"] == "list_workflows"
    assert trace[0]["call_id"] == "call_1"
    assert trace[0]["status"] == "ok"
    assert all(item["lane"] == "fixed_workflow" for item in trace[0]["result"])


def test_dispatcher_rejects_unknown_tool_arguments_before_execution():
    result = dispatch_tool_call(
        "list_workflows",
        {"lane": "fixed_workflow", "adhoc_frontend_field": "drift"},
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert "Unknown tool argument" in result["message"]
    assert "adhoc_frontend_field" in result["message"]


def test_dispatcher_rejects_missing_required_tool_arguments_before_execution():
    result = dispatch_tool_call(
        "preflight_workflow",
        {"series_id": 11},
        project_context={"series": [], "workflows": []},
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert "Missing required tool argument" in result["message"]
    assert "workflow_type" in result["message"]


def test_dispatcher_rejects_invalid_tool_argument_types_before_execution():
    def fake_rows(sql, params=()):
        raise AssertionError("rows_fn must not run for invalid tool arguments")

    result = dispatch_tool_call("read_task", {"task_id": "not-an-int"}, rows_fn=fake_rows)

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert "Invalid tool argument type" in result["message"]
    assert "task_id" in result["message"]


def test_dispatcher_rejects_invalid_tool_argument_enum_before_execution():
    result = dispatch_tool_call(
        "preflight_workflow",
        {"series_id": 1, "workflow_type": "made_up_workflow"},
    )

    assert result["status"] == "blocked"
    assert result["production_task_created"] is False
    assert "Invalid tool argument value" in result["message"]
    assert "workflow_type" in result["message"]


def test_dispatcher_allows_nullable_enum_arguments():
    result = dispatch_tool_call("list_workflows", {"lane": None})

    assert result["status"] == "ok"
    assert result["production_task_created"] is False
    assert result["result"]


def test_tool_trace_response_items_use_responses_function_call_output():
    trace = [{"status": "ok", "tool": "list_workflows", "call_id": "call_1", "result": [{"type": "fixed"}]}]

    items = tool_dispatcher.tool_trace_response_items(trace)

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": json.dumps(trace[0], ensure_ascii=False, default=str),
        }
    ]


def test_dispatcher_propose_toolchain_reads_allowlisted_remote_script_paths(tmp_path, monkeypatch):
    script_root = tmp_path / "remote_scripts"
    script_root.mkdir()
    fmriprep = script_root / "run_fmriprep.sh"
    xcpd = script_root / "run_xcpd_fmriprep.sh"
    fmriprep.write_text(
        "docker run --rm --gpus all -v /task/bids:/data:ro nipreps/fmriprep:latest /data /out participant\n",
        encoding="utf-8",
    )
    xcpd.write_text(
        "docker run --rm -v /task/output/fmriprep:/fmriprep:ro pennlinc/xcp_d:26.0.2 /fmriprep /out participant\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IMAGE_AGENT_INCUBATION_SCRIPT_ROOTS", str(script_root))

    result = dispatch_tool_call(
        "propose_toolchain",
        {
            "objective": "Incubate fMRIPrep then XCP-D from remote wrappers",
            "input_modality": "BOLD",
            "script_paths": [str(fmriprep), str(xcpd)],
        },
    )

    assert result["status"] == "ok"
    proposal = result["result"]
    assert proposal["production_task_created"] is False
    assert proposal["decomposition"]["status"] == "parsed"
    assert [step["image"] for step in proposal["primitive_chain"]] == [
        "nipreps/fmriprep:latest",
        "pennlinc/xcp_d:26.0.2",
    ]
    assert [step["contract"]["stage"] for step in proposal["primitive_chain"]] == [
        "fmriprep_preprocessing",
        "xcpd_postprocessing",
    ]
