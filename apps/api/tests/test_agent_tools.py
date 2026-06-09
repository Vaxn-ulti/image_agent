import json

from app.agent import tools


def test_read_project_context_includes_series_tasks_outputs_and_workflows(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "PROJECTS_ROOT", tmp_path / "projects")
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
        return []

    context = tools.read_project_context(project_id=7, rows_fn=fake_rows, workflows=[{"type": "bold_deepprep"}])

    assert context["project"] == {"id": 7, "name": "demo"}
    assert context["series"][0]["modality"] == "BOLD"
    assert context["tasks"][0]["id"] == 21
    assert context["outputs"][0]["metadata"] == {}
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
    monkeypatch.setenv("IMAGE_AGENT_FS_LICENSE", str(license_path))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_FMRIPREP_SCRIPT", str(fmriprep_script))
    monkeypatch.setenv("IMAGE_AGENT_BOLD_XCPD_SCRIPT", str(xcpd_script))
    context = {
        "project_root": str(tmp_path / "project"),
        "series": [{"id": 11, "modality": "BOLD", "supported_for_processing": 1}],
        "workflows": [],
    }

    result = tools.preflight_workflow(context, series_id=11, workflow_type="bold_fmriprep_xcpd_report")

    assert result["ok"] is True
    assert any(check["name"] == "remote_fmriprep_script_exists" for check in result["checks"])
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
    main_log.write_text("main progress\n", encoding="utf-8")
    remote_log_dir.mkdir(parents=True)
    (remote_log_dir / "fmriprep.log").write_text("fmriprep live log\n", encoding="utf-8")
    (remote_log_dir / "xcpd_fmriprep.log").write_text("xcp-d live log\n", encoding="utf-8")

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

    task = tools.read_task(118, rows_fn=fake_rows)
    events = tools.read_task_events(118, rows_fn=fake_rows, projects_root=projects_root)

    assert task["status"] == "ok"
    assert task["task"]["workflow_type"] == "bold_fmriprep_xcpd_report"
    assert "main progress" in events["main_log"]["tail"]
    assert events["remote_logs"][0]["name"] == "fmriprep.log"
    assert "fmriprep live log" in events["remote_logs"][0]["tail"]
    stages = {item["name"]: item["source_stage"] for item in events["remote_logs"]}
    assert stages["fmriprep.log"] == "fmriprep"
    assert stages["xcpd_fmriprep.log"] == "xcpd"
    assert any(event["type"] == "task.remote_log" for event in events["events"])


def test_read_result_summary_prefers_registered_summary(tmp_path):
    summary = tmp_path / "bold_result_summary.json"
    summary.write_text(json.dumps({"task_id": 118, "outputs": {"logs": []}}), encoding="utf-8")

    def fake_rows(sql, params=()):
        if "FROM tasks" in sql:
            return [
                {
                    "id": 118,
                    "project_id": 7,
                    "series_id": 11,
                    "workflow_type": "bold_fmriprep_xcpd_report",
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
    accepted = tools.create_workflow_task(
        confirmation={
            "approved": True,
            "workflow_type": "t1_deepprep_anat_report",
            "series_id": 11,
            "action_lane": "fixed_workflow",
        },
        create_task_fn=fake_create,
    )

    assert rejected["status"] == "confirmation_required"
    assert incubating["status"] == "blocked"
    assert debug_mock["status"] == "blocked"
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
