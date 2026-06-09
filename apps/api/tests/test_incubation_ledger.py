from app.agent.incubation import IncubationLedger
from app.agent.tools import propose_toolchain


def test_incubation_ledger_persists_proposal_validation_and_promotion(tmp_path):
    ledger = IncubationLedger(tmp_path)

    proposal = ledger.create_proposal(
        objective="Try a new BOLD cleanup chain",
        input_modality="BOLD",
        primitives=["stage_bids", "run_fmriprep", "run_xcpd"],
        sandbox_dataset="project-7-series-11",
    )
    validation = ledger.append_validation(
        proposal["proposal_id"],
        status="passed",
        report={"checks": [{"name": "writes_result_summary_contract", "status": "pass"}]},
    )
    blocked = ledger.generate_promotion_suggestion(proposal["proposal_id"])
    ledger.append_validation(
        proposal["proposal_id"],
        status="passed",
        report={"checks": [{"name": "container_script_decomposition_review", "status": "pass"}]},
    )
    ledger.append_human_review(
        proposal["proposal_id"],
        reviewer="operator",
        decision="approved",
        notes="Reviewed sandbox evidence.",
    )
    suggestion = ledger.generate_promotion_suggestion(proposal["proposal_id"])

    reloaded = IncubationLedger(tmp_path).get_proposal(proposal["proposal_id"])

    assert proposal["status"] == "proposed"
    assert validation["validation_run"] == 1
    assert blocked["status"] == "promotion_blocked"
    assert "requires at least 2 passed sandbox validation runs" in blocked["blocking_errors"]
    assert suggestion["status"] == "promotion_suggested"
    assert suggestion["production_enabled"] is False
    assert suggestion["readiness"]["ready"] is True
    assert suggestion["artifact_drafts"]["workflow_registry_entry"]["status"] == "draft_from_incubation"
    assert suggestion["artifact_drafts"]["workflow_registry_entry"]["agent_selectable"] is False
    assert suggestion["artifact_drafts"]["backend_runner_contract"]["must_not_use"]
    assert suggestion["artifact_drafts"]["result_summary_contract"]["required"] is True
    assert reloaded["proposal_id"] == proposal["proposal_id"]
    assert reloaded["validation_runs"][0]["status"] == "passed"
    assert len(reloaded["validation_runs"]) == 2
    assert reloaded["human_reviews"][0]["decision"] == "approved"


def test_incubation_ledger_records_decomposed_script_and_container_steps(tmp_path):
    script = tmp_path / "candidate_workflow.sh"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "# image-agent primitive: stage_bids",
                "docker run --rm --gpus all -v \"$BIDS:/data:ro\" pennlinc/qsiprep:latest /data /out participant",
                "python apps/api/app/scripts/verify_scientific_reports.py --task-ids 1",
            ]
        ),
        encoding="utf-8",
    )
    ledger = IncubationLedger(tmp_path / "ledger")

    proposal = ledger.create_proposal(
        objective="Decompose a candidate DWI container script",
        input_modality="DWI",
        primitives=[],
        script_paths=[script],
        script_text="singularity run docker://pennlinc/qsirecon:latest /data /out participant",
        known_script_roots=[tmp_path],
    )
    reloaded = IncubationLedger(tmp_path / "ledger").get_proposal(proposal["proposal_id"])

    assert reloaded["production_enabled"] is False
    assert reloaded["production_task_created"] is False
    assert reloaded["decomposition"]["status"] == "parsed"
    assert reloaded["composition_plan"]["production_enabled"] is False
    assert "result-summary.json" in reloaded["composition_plan"]["repeatability_requirements"][2]
    assert reloaded["promotion_gate"]["status"] == "promotion_blocked_until_all_required_checks_pass"
    assert [entry["kind"] for entry in reloaded["primitive_chain"]] == [
        "declared_primitive",
        "container",
        "script",
        "container",
    ]
    assert reloaded["primitive_chain"][1]["image"] == "pennlinc/qsiprep:latest"
    assert reloaded["primitive_chain"][3]["image"] == "docker://pennlinc/qsirecon:latest"


def test_incubation_ledger_rejects_script_paths_outside_known_roots(tmp_path):
    allowed_root = tmp_path / "known"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    script = outside_root / "candidate.sh"
    script.write_text("docker run --rm image:latest\n", encoding="utf-8")
    ledger = IncubationLedger(tmp_path / "ledger")

    try:
        ledger.create_proposal(
            objective="Unsafe source",
            input_modality="BOLD",
            primitives=[],
            script_paths=[script],
            known_script_roots=[allowed_root],
        )
    except ValueError as exc:
        assert "outside known script roots" in str(exc)
    else:
        raise AssertionError("Expected unknown script path to be rejected")


def test_propose_toolchain_decomposes_text_without_enabling_production():
    proposal = propose_toolchain(
        objective="Inspect a pasted container step",
        input_modality="BOLD",
        script_text="docker run --rm nipreps/fmriprep:latest /data /out participant",
    )

    assert proposal["production_task_created"] is False
    assert proposal["production_enabled"] is False
    assert proposal["decomposition"]["status"] == "parsed"
    assert proposal["primitive_chain"][0]["kind"] == "container"
    assert proposal["primitive_chain"][0]["image"] == "nipreps/fmriprep:latest"


def test_toolchain_decomposition_handles_remote_sudo_multiline_docker_commands(tmp_path):
    script = tmp_path / "run_fmriprep.sh"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "sudo -S docker run --rm --gpus all --network host \\",
                "  -e TEMPLATEFLOW_HOME=/templateflow \\",
                "  -v /project/derivatives/118/bids:/data:ro \\",
                "  -v /project/derivatives/118/output/fmriprep:/out \\",
                "  -v /project/license.txt:/opt/freesurfer/license.txt:ro \\",
                "  nipreps/fmriprep:latest /data /out participant \\",
                "  --participant-label 01 --fs-license-file /opt/freesurfer/license.txt",
                "python postprocess_xcpd_bold_features.py --task-id 118 --password=do-not-store",
            ]
        ),
        encoding="utf-8",
    )
    ledger = IncubationLedger(tmp_path / "ledger")

    proposal = ledger.create_proposal(
        objective="Decompose remote BOLD wrapper",
        input_modality="BOLD",
        primitives=[],
        script_paths=[script],
        known_script_roots=[tmp_path],
    )
    chain = proposal["primitive_chain"]

    assert [entry["kind"] for entry in chain] == ["container", "script"]
    container = chain[0]
    assert container["runtime"] == "docker"
    assert container["image"] == "nipreps/fmriprep:latest"
    assert container["uses_gpu"] is True
    assert container["contract"]["stage"] == "fmriprep_preprocessing"
    assert "BIDS dataset with BOLD files" in container["contract"]["required_inputs"]
    assert "fMRIPrep HTML report" in container["contract"]["expected_outputs"]
    assert {"name": "fmriprep_html_report_exists", "status": "required"} in container["contract"]["validation_checks"]
    assert {"name": "read_only_input_mounts_verified", "status": "required"} in container["contract"]["validation_checks"]
    assert {"name": "writable_mounts_scoped_to_sandbox", "status": "required"} in container["contract"]["validation_checks"]
    assert "TEMPLATEFLOW_HOME=/templateflow" in container["environment"]
    assert "/project/derivatives/118/bids:/data:ro" in container["volumes"]
    assert "/project/derivatives/118/output/fmriprep:/out" in container["volumes"]
    assert "--participant-label" in container["arguments"]
    assert chain[1]["kind"] == "script"
    assert chain[1]["contract"]["stage"] == "feature_postprocessing"
    assert "feature tables" in chain[1]["contract"]["expected_outputs"]
    assert "do-not-store" not in chain[1]["command_preview"]


def test_container_decomposition_structures_mount_roles_and_safety_checks(tmp_path):
    script = "\n".join(
        [
            "docker run --rm --gpus all \\",
            "  -e TEMPLATEFLOW_HOME=/templateflow \\",
            "  -e FS_LICENSE=/opt/freesurfer/license.txt \\",
            "  -v /project/derivatives/118/bids:/data:ro \\",
            "  -v /project/derivatives/118/output/fmriprep:/out \\",
            "  -v /project/derivatives/118/work/fmriprep:/work \\",
            "  -v /project/derivatives/118/work/templateflow:/templateflow \\",
            "  -v /project/license.txt:/opt/freesurfer/license.txt:ro \\",
            "  nipreps/fmriprep:latest /data /out participant --fs-license-file /opt/freesurfer/license.txt",
        ]
    )
    proposal = propose_toolchain(
        objective="Classify fMRIPrep container mounts",
        input_modality="BOLD",
        script_text=script,
    )

    container = proposal["primitive_chain"][0]
    mounts = {mount["container_path"]: mount for mount in container["mounts"]}

    assert mounts["/data"]["role"] == "input_data"
    assert mounts["/data"]["read_only"] is True
    assert mounts["/out"]["role"] == "output_data"
    assert mounts["/out"]["read_only"] is False
    assert mounts["/work"]["role"] == "work_dir"
    assert mounts["/templateflow"]["role"] == "templateflow_cache"
    assert mounts["/opt/freesurfer/license.txt"]["role"] == "license_file"
    assert mounts["/opt/freesurfer/license.txt"]["read_only"] is True
    assert "TEMPLATEFLOW_HOME" in container["environment_map"]
    assert "FS_LICENSE" in container["environment_map"]
    assert "host paths are symbolic or sandbox-scoped" in container["contract"]["security_notes"]
    assert {"name": "input_mounts_are_read_only", "status": "required"} in container["contract"]["validation_checks"]
    assert {"name": "license_mount_is_read_only", "status": "required"} in container["contract"]["validation_checks"]
    assert {"name": "output_and_work_mounts_are_sandbox_scoped", "status": "required"} in container["contract"]["validation_checks"]


def test_incubation_proposal_builds_validation_plan_with_evidence_requirements():
    proposal = propose_toolchain(
        objective="Validate BOLD fMRIPrep XCP-D wrapper",
        input_modality="BOLD",
        script_text="\n".join(
            [
                "docker run --rm --gpus all -v /sandbox/bids:/data:ro -v /sandbox/fmriprep:/out nipreps/fmriprep:latest /data /out participant",
                "docker run --rm -v /sandbox/fmriprep:/fmriprep:ro -v /sandbox/xcpd:/out pennlinc/xcp_d:26.0.2 /fmriprep /out participant",
            ]
        ),
    )

    validation_plan = proposal["validation_plan"]
    checks = {item["name"]: item for item in validation_plan["checks"]}

    assert validation_plan["production_enabled"] is False
    assert validation_plan["minimum_passed_runs"] == 2
    assert checks["fmriprep_html_report_exists"]["evidence_kind"] == "artifact"
    assert "HTML report" in checks["fmriprep_html_report_exists"]["expected_evidence"]
    assert checks["xcpd_metrics_tables_exist"]["evidence_kind"] == "artifact"
    assert checks["input_mounts_are_read_only"]["evidence_kind"] == "mount_audit"
    assert checks["container_exit_code_zero"]["evidence_kind"] == "runtime"
    assert any("no production task" in item for item in validation_plan["global_requirements"])
    assert proposal["promotion_gate"]["validation_plan_id"] == validation_plan["plan_id"]


def test_incubation_proposal_builds_container_inspection_plan():
    proposal = propose_toolchain(
        objective="Inspect and validate BOLD containers",
        input_modality="BOLD",
        script_text="\n".join(
            [
                "docker run --rm --gpus all -v /sandbox/bids:/data:ro -v /sandbox/fmriprep:/out nipreps/fmriprep:latest /data /out participant",
                "docker run --rm -v /sandbox/fmriprep:/fmriprep:ro -v /sandbox/xcpd:/out pennlinc/xcp_d:26.0.2 /fmriprep /out participant",
            ]
        ),
    )

    inspection = proposal["container_inspection_plan"]
    containers = inspection["containers"]
    validation_checks = {item["name"]: item for item in proposal["validation_plan"]["checks"]}

    assert inspection["status"] == "required_before_sandbox_execution"
    assert inspection["container_count"] == 2
    assert containers[0]["image"] == "nipreps/fmriprep:latest"
    assert containers[0]["inspection_method"] == "backend_runtime_only"
    assert any(probe["command"] == "fmriprep --version" for probe in containers[0]["version_probes"])
    assert {"artifact_kind": "report", "pattern": "sub-*.html"} in containers[0]["native_output_path_probes"]
    assert containers[1]["stage"] == "xcpd_postprocessing"
    assert any(probe["command"] == "xcp_d --version" for probe in containers[1]["version_probes"])
    assert "patient-data mounts" in containers[0]["forbidden_during_inspection"]
    assert validation_checks["container_image_inspected"]["evidence_kind"] == "container_inspection"
    assert validation_checks["container_digest_recorded"]["evidence_kind"] == "container_inspection"
    assert validation_checks["container_entrypoint_recorded"]["evidence_kind"] == "container_inspection"
    assert validation_checks["container_versions_recorded"]["evidence_kind"] == "container_inspection"
    assert validation_checks["container_native_output_paths_verified"]["evidence_kind"] == "container_inspection"
    assert any("inspect container image metadata" in item for item in proposal["validation_plan"]["global_requirements"])


def test_incubation_proposal_builds_xcpd_and_report_contracts(tmp_path):
    script = "\n".join(
        [
            "docker run --rm -v /sandbox/fmriprep:/fmriprep:ro -v /sandbox/xcpd:/out pennlinc/xcp_d:26.0.2 /fmriprep /out participant --participant-label 01",
            "python make_bold_map_figures.py --xcpd /sandbox/xcpd --out /sandbox/reports",
            "python validate_xcpd_deepprep_outputs.py --task-id 1",
        ]
    )
    ledger = IncubationLedger(tmp_path / "ledger")

    proposal = ledger.create_proposal(
        objective="Decompose XCP-D and report generation",
        input_modality="BOLD",
        primitives=[],
        script_text=script,
    )

    chain = proposal["primitive_chain"]
    assert [step["contract"]["stage"] for step in chain] == [
        "xcpd_postprocessing",
        "report_generation",
        "validation_audit",
    ]
    plan = proposal["composition_plan"]
    assert "XCP-D HTML report" in plan["expected_outputs"]
    assert "QC figures" in plan["expected_outputs"]
    assert {"name": "xcpd_metrics_tables_exist", "status": "required"} in plan["validation_checks"]
    assert {"name": "html_and_figures_registered", "status": "required"} in plan["validation_checks"]
    assert {"name": "validation_report_written", "status": "required"} in plan["validation_checks"]
    assert proposal["promotion_gate"]["production_enabled"] is False
