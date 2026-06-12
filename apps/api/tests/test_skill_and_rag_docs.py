import hashlib
import importlib.util
import json
from pathlib import Path

from app.agent.rag_index import _parse_frontmatter


REPO_ROOT = Path(__file__).resolve().parents[3]


REQUIRED_SKILLS = [
    "image-agent-operator",
    "image-agent-architect",
    "image-agent-developer",
    "image-agent-workflow-runner",
    "image-agent-result-reviewer",
    "image-agent-rag-curator",
    "neuroimaging-workflow-runner",
]


REQUIRED_SKILL_SECTIONS = [
    "## Trigger Rules",
    "## Operating Rules",
    "## Reference Loading",
    "## Output Shape",
    "## Eval Hints",
]


REQUIRED_RAG_DOCS = [
    "workflows/workflow_launchability_matrix.md",
    "workflows/t1_deepprep_anat_report.md",
    "workflows/bold_fmriprep_xcpd_report.md",
    "workflows/dwi_fast_gpu_dti.md",
    "contracts/result-summary.md",
    "contracts/task-events.md",
    "contracts/container-qc-artifacts.md",
    "contracts/agent-run-ledger.md",
    "interpretation/t1_features.md",
    "interpretation/bold_features.md",
    "data-requirements/modalities-bids.md",
    "troubleshooting/common-errors.md",
    "safety/non-diagnostic.md",
    "safety/rag-priority.md",
]


REQUIRED_VENDOR_DOCS = [
    "fmriprep_official_container_usage.md",
    "fmriprep_official_outputs.md",
    "xcp_d_official_container_usage.md",
    "xcp_d_official_outputs.md",
    "deepprep_official_container_usage.md",
    "freesurfer_official_container_reconall.md",
    "freesurfer_official_license.md",
    "bids_validator_official_cli_docker.md",
    "templateflow_official_cache_archive_client.md",
    "docker_official_image_inspect.md",
    "podman_official_image_inspect.md",
    "singularity_apptainer_official_inspect.md",
    "bids_official_mri_derivatives.md",
    "openai_official_responses_function_tools.md",
    "dcm2niix_official_conversion.md",
    "qsiprep_official_container_usage_outputs.md",
    "qsirecon_official_container_usage_workflows.md",
    "fsl_official_fast_dti_tools.md",
    "mrtrix3_official_dti_toolbox.md",
    "mriqc_official_container_usage_outputs.md",
    "dpabi_official_container_boundary.md",
]


REQUIRED_VENDOR_SOURCE_IDS = [
    "docker_image_inspect",
    "podman_image_inspect",
    "singularityce_inspect",
    "apptainer_inspect",
    "fmriprep_outputs",
    "xcp_d_outputs",
    "bids_mri",
    "bids_derivatives",
    "openai_function_calling_responses",
    "openai_tools_responses",
    "openai_python_sdk_readme",
    "openai_responses_api_reference",
    "dcm2niix_readme",
    "qsiprep_usage",
    "qsiprep_preprocessing_outputs",
    "qsirecon_quickstart",
    "qsirecon_builtin_workflows",
    "qsirecon_custom_workflows",
    "fsl_eddy_users_guide",
    "fsl_dtifit",
    "fsl_flirt_user_guide",
    "fsl_fnirt_user_guide",
    "fsl_utils",
    "mrtrix3_mrinfo",
    "mrtrix3_dwi2mask",
    "mrtrix3_mrconvert",
    "mrtrix3_dwi2tensor",
    "mrtrix3_tensor2metric",
    "mrtrix3_mrstats",
    "mrtrix3_mrcalc",
    "deepprep_outputs",
    "freesurfer_recon_all_outputs",
    "freesurfer_license_registration",
    "mriqc_usage",
    "mriqc_reports",
    "mriqc_installation",
    "nipreps_docker_guidelines",
    "nipreps_singularity_guidelines",
    "dpabi_home",
    "dpabi_standalone_docker",
    "dpabisurfslurm_hpc_singularity",
    "dpabi_github_repo",
    "dpabi_dockerfile",
    "dpabi_docker_hub",
]


REQUIRED_WORKFLOW_METADATA = {
    "workflows/t1_deepprep_anat_report.md": {
        "workflow_type": "t1_deepprep_anat_report",
        "status": "production_supported",
    },
    "workflows/bold_fmriprep_xcpd_report.md": {
        "workflow_type": "bold_fmriprep_xcpd_report",
        "status": "incubation_reference",
    },
    "workflows/dwi_fast_gpu_dti.md": {
        "workflow_type": "dwi_fast_gpu_dti",
        "status": "production_supported",
    },
    "workflows/workflow_launchability_matrix.md": {
        "workflow_type": "workflow_launchability_matrix",
        "status": "current_contract",
    },
}


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    raw_metadata = text.split("---\n", 2)[1]
    metadata = {}
    for line in raw_metadata.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _metadata_list(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def test_skill_creator_style_skills_have_references_and_parseable_evals():
    skills_root = REPO_ROOT / "docs" / "skills"
    evals = json.loads((skills_root / "evals" / "evals.json").read_text(encoding="utf-8"))
    eval_skill_names = {item["skill_name"] for item in evals["evals"]}
    categories = {item["category"] for item in evals["evals"]}

    for skill in REQUIRED_SKILLS:
        skill_dir = skills_root / skill
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        skill_evals = [item for item in evals["evals"] if item["skill_name"] == skill]
        skill_categories = {item["category"] for item in skill_evals}
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "references").is_dir()
        assert any((skill_dir / "references").glob("*.md"))
        assert "description: Use when" in skill_text
        for section in REQUIRED_SKILL_SECTIONS:
            assert section in skill_text
        assert skill in eval_skill_names
        assert {"normal_path", "missing_info", "risk_conflict"} <= skill_categories
        assert len(skill_evals) >= 3
    assert {"normal_path", "missing_info", "risk_conflict"} <= categories


def test_rag_corpus_contains_required_sections_and_vendor_metadata():
    rag_root = REPO_ROOT / "docs" / "rag"

    for relative in REQUIRED_RAG_DOCS:
        assert (rag_root / relative).exists()

    for vendor_doc in REQUIRED_VENDOR_DOCS:
        text = (rag_root / "vendor" / vendor_doc).read_text(encoding="utf-8")
        assert "source_url:" in text
        assert "retrieved_date: 2026-06-" in text
        assert "status: curated_summary" in text
        assert "## Container/CLI Usage" in text
        assert "## image_agent Notes" in text or "## Image Agent Notes" in text


def test_workflow_rag_docs_have_machine_readable_frontmatter():
    rag_root = REPO_ROOT / "docs" / "rag"
    required_keys = {
        "source_type",
        "workflow_type",
        "status",
        "official_grounding",
        "expected_artifacts",
        "unsupported_boundaries",
    }

    for relative, expected in REQUIRED_WORKFLOW_METADATA.items():
        metadata, _body = _parse_frontmatter((rag_root / relative).read_text(encoding="utf-8"))
        assert required_keys <= set(metadata), relative
        assert metadata["source_type"] == "rag_workflow"
        assert metadata["workflow_type"] == expected["workflow_type"]
        assert metadata["status"] == expected["status"]
        for list_key in ("official_grounding", "expected_artifacts", "unsupported_boundaries"):
            assert isinstance(metadata[list_key], list), f"{relative} {list_key}"
            assert metadata[list_key], f"{relative} {list_key}"
        for grounded_source in metadata["official_grounding"]:
            assert (REPO_ROOT / grounded_source).exists(), f"{relative} missing {grounded_source}"


def test_all_indexed_rag_docs_have_basic_machine_readable_frontmatter():
    rag_root = REPO_ROOT / "docs" / "rag"
    allowed_source_types = {
        "rag_contract",
        "rag_data_requirement",
        "rag_interpretation",
        "rag_safety",
        "rag_troubleshooting",
        "rag_vendor",
        "rag_workflow",
    }

    for path in rag_root.rglob("*.md"):
        relative = path.relative_to(rag_root).as_posix()
        if relative.startswith("vendor/raw-sources/"):
            continue

        metadata, _body = _parse_frontmatter(path.read_text(encoding="utf-8"))

        assert metadata.get("source_type") in allowed_source_types, relative
        assert metadata.get("status"), relative
        assert str(metadata.get("retrieved_date", "")).startswith("2026-06-"), relative


def test_vendor_raw_sources_manifest_covers_curated_summaries():
    raw_root = REPO_ROOT / "docs" / "rag" / "vendor" / "raw-sources"
    manifest_path = raw_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["sources"]
    assert "traceable source evidence" in manifest["note"]

    sources_by_vendor_doc = {}
    source_ids = set()
    for source in manifest["sources"]:
        for key in (
            "id",
            "vendor_doc",
            "url",
            "file",
            "source_type",
            "retrieved_at",
            "sha256",
            "bytes",
            "status",
        ):
            assert key in source
        assert source["status"] == "downloaded"
        assert source["source_type"].startswith("official_")
        assert source["url"].startswith("https://")
        assert len(source["sha256"]) == 64
        assert source["bytes"] > 0

        raw_file = raw_root / source["file"]
        assert raw_file.exists()
        raw_bytes = raw_file.read_bytes()
        assert len(raw_bytes) == source["bytes"]
        assert hashlib.sha256(raw_bytes).hexdigest() == source["sha256"]
        source_ids.add(source["id"])
        sources_by_vendor_doc.setdefault(source["vendor_doc"], []).append(source)

    for vendor_doc in REQUIRED_VENDOR_DOCS:
        assert vendor_doc in sources_by_vendor_doc
        assert (REPO_ROOT / "docs" / "rag" / "vendor" / vendor_doc).exists()
    for source_id in REQUIRED_VENDOR_SOURCE_IDS:
        assert source_id in source_ids


def test_vendor_raw_sources_are_not_text_normalized_in_git_archives():
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "docs/rag/vendor/raw-sources/** -text" in attributes


def test_curated_vendor_docs_declare_manifest_backed_raw_source_ids_and_urls():
    vendor_root = REPO_ROOT / "docs" / "rag" / "vendor"
    raw_manifest = json.loads((vendor_root / "raw-sources" / "manifest.json").read_text(encoding="utf-8"))
    sources_by_id = {source["id"]: source for source in raw_manifest["sources"]}

    for vendor_doc in REQUIRED_VENDOR_DOCS:
        metadata = _frontmatter((vendor_root / vendor_doc).read_text(encoding="utf-8"))
        raw_source_ids = _metadata_list(metadata.get("raw_source_ids", ""))
        assert raw_source_ids, f"{vendor_doc} must declare manifest-backed raw_source_ids"

        for raw_source_id in raw_source_ids:
            assert raw_source_id in sources_by_id
            assert sources_by_id[raw_source_id]["vendor_doc"] == vendor_doc

        manifest_urls = {sources_by_id[raw_source_id]["url"] for raw_source_id in raw_source_ids}
        for source_url in _metadata_list(metadata.get("source_url", "")):
            assert source_url in manifest_urls


def test_container_qc_artifact_policy_is_in_rag_and_skills():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "container-qc-artifacts.md").read_text(encoding="utf-8")
    workflow_skill = (REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "SKILL.md").read_text(encoding="utf-8")
    reviewer_skill = (REPO_ROOT / "docs" / "skills" / "image-agent-result-reviewer" / "SKILL.md").read_text(encoding="utf-8")
    reviewer_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-result-reviewer"
        / "references"
        / "container-qc-artifacts.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "container-native QC",
        "fMRIPrep HTML report",
        "XCP-D HTML report",
        "DeepPrep QC",
        "FreeSurfer snapshots",
        "do not replace",
    ):
        assert phrase in rag_doc
    assert "container-qc-artifacts.md" in workflow_skill
    assert "container-qc-artifacts.md" in reviewer_skill
    assert "container-native QC" in reviewer_ref
    assert "outputs.reports" in reviewer_ref


def test_container_qc_artifact_policy_requires_curated_official_source_ids():
    paths = [
        REPO_ROOT / "docs" / "rag" / "contracts" / "container-qc-artifacts.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "container-qc-artifacts.md",
        REPO_ROOT / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in (
        "`official_source_ids`",
        "top-level artifact metadata and `provenance`",
        "curated RAG vendor documents",
        "not proof that a particular task succeeded",
        "docs/rag/vendor/fmriprep_official_outputs.md",
        "docs/rag/vendor/xcp_d_official_outputs.md",
        "docs/rag/vendor/qsiprep_official_container_usage_outputs.md",
        "docs/rag/vendor/qsirecon_official_container_usage_workflows.md",
        "docs/rag/vendor/fsl_official_fast_dti_tools.md",
        "docs/rag/vendor/mrtrix3_official_dti_toolbox.md",
    ):
        assert phrase in combined


def test_artifact_manifest_contract_is_documented_for_frontend_use():
    paths = [
        REPO_ROOT / "docs" / "rag" / "contracts" / "result-summary.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "contracts.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "task-events-and-results.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in (
        "`/tasks/{task_id}/artifact-manifest`",
        "`preview_kind`",
        "stable preview/download list",
        "do not expose backend absolute paths",
        "result-summary remains authoritative",
        "`/tasks/{task_id}/artifacts/{relative_path}`",
    ):
        assert phrase in combined


def test_deepprep_official_outputs_are_documented_for_agent_use():
    deepprep_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "vendor"
        / "deepprep_official_container_usage.md"
    ).read_text(encoding="utf-8")
    workflow_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "workflows"
        / "t1_deepprep_anat_report.md"
    ).read_text(encoding="utf-8")
    combined = deepprep_doc + "\n" + workflow_doc

    for phrase in (
        "deepprep_outputs",
        "Anatomical derivatives",
        "Functional derivatives",
        "visual reports",
        "HTML report",
        "outputs.reports",
        "outputs.figures",
        "container-native DeepPrep QC",
        "placeholder_outputs=true",
    ):
        assert phrase in combined


def test_freesurfer_official_outputs_are_documented_for_agent_use():
    freesurfer_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "vendor"
        / "freesurfer_official_container_reconall.md"
    ).read_text(encoding="utf-8")
    workflow_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "workflows"
        / "t1_deepprep_anat_report.md"
    ).read_text(encoding="utf-8")
    qc_contract = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "contracts"
        / "container-qc-artifacts.md"
    ).read_text(encoding="utf-8")
    combined = freesurfer_doc + "\n" + workflow_doc + "\n" + qc_contract

    for phrase in (
        "freesurfer_recon_all_outputs",
        "ReconAllOutputFiles",
        "mri/orig.mgz",
        "mri/aseg.mgz",
        "surf/lh.white",
        "surf/lh.pial",
        "label/lh.aparc.annot",
        "stats/aseg.stats",
        "stats/lh.aparc.stats",
        "scripts/recon-all.log",
        "outputs.tables",
        "outputs.maps",
        "outputs.logs",
        "container-native FreeSurfer QC",
    ):
        assert phrase in combined


def test_freesurfer_official_license_boundaries_are_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag"
    raw_manifest = json.loads((rag_root / "vendor" / "raw-sources" / "manifest.json").read_text(encoding="utf-8"))
    source_ids = {source["id"] for source in raw_manifest["sources"]}
    vendor_doc = (rag_root / "vendor" / "freesurfer_official_license.md").read_text(encoding="utf-8")
    troubleshooting = (rag_root / "troubleshooting" / "common-errors.md").read_text(encoding="utf-8")
    security_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "security-and-containers.md"
    ).read_text(encoding="utf-8")
    container_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "neuroimaging-workflow-runner"
        / "references"
        / "container-contracts.md"
    ).read_text(encoding="utf-8")
    combined = vendor_doc + "\n" + troubleshooting + "\n" + security_ref + "\n" + container_ref

    assert "freesurfer_license_registration" in source_ids
    for phrase in (
        "FreeSurfer license",
        "registration",
        "license key file",
        "FS_LICENSE",
        "$FREESURFER_HOME/license.txt",
        "--fs-license-file",
        "--fs_license_file",
        "/opt/freesurfer/license.txt:ro",
        "read-only support mount",
        "license file contents",
        "configuration blocker",
        "not data pathology",
    ):
        assert phrase in combined


def test_container_decomposition_policy_documents_mount_roles_and_gates():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "container-qc-artifacts.md").read_text(encoding="utf-8")
    security_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "security-and-containers.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "structured `mounts`",
        "`input_data`",
        "`output_data`",
        "`work_dir`",
        "`templateflow_cache`",
        "`license_file`",
        "input_mounts_are_read_only",
        "license_mount_is_read_only",
        "output_and_work_mounts_are_sandbox_scoped",
    ):
        assert phrase in rag_doc or phrase in security_ref


def test_incubation_validation_plan_policy_is_documented_for_agent_use():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "container-qc-artifacts.md").read_text(encoding="utf-8")
    security_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "security-and-containers.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + security_ref

    for phrase in (
        "`validation_plan`",
        "`minimum_passed_runs`",
        "`evidence_kind`",
        "`expected_evidence`",
        "at least two passed sandbox runs",
        "no production task side effects",
        "human approval",
    ):
        assert phrase in combined


def test_container_inspection_plan_policy_is_documented_for_agent_use():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "container-qc-artifacts.md").read_text(encoding="utf-8")
    security_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "security-and-containers.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + security_ref

    for phrase in (
        "`container_inspection_plan`",
        "backend local/runtime tools",
        "image digest",
        "entrypoint",
        "version probes",
        "native output path probes",
        "docker image inspect",
        "singularity inspect --json",
        "`container_image_inspected`",
        "`container_digest_recorded`",
        "`container_entrypoint_recorded`",
        "`container_versions_recorded`",
        "`container_native_output_paths_verified`",
        "`evidence_kind: container_inspection`",
    ):
        assert phrase in combined


def test_data_candidate_selection_policy_is_documented_for_agent_use():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "data-requirements" / "modalities-bids.md").read_text(encoding="utf-8")
    workflow_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "registry-and-preflight.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + workflow_ref

    for phrase in (
        "`list_data_candidates`",
        "`select_incubation_dataset`",
        "supported_for_processing",
        "BIDS-ready",
        "DWI requires `.json`, `.bval`, and `.bvec`",
        "DICOM archives",
        "raw image contents",
        "`production_task_created: false`",
        "explicit user confirmation",
    ):
        assert phrase in combined


def test_openai_responses_tool_contract_is_documented_for_agent_use():
    rag_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "vendor"
        / "openai_official_responses_function_tools.md"
    ).read_text(encoding="utf-8")
    developer_contract = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-developer"
        / "references"
        / "contracts.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + developer_contract

    for phrase in (
        "Responses API",
        "function_call_output",
        "tool_choice",
        "top-level Responses function tools",
        "function tool specs are strict",
        "`strict=true`",
        "`additionalProperties=false`",
        "dispatcher rejects unknown tool arguments",
        "dispatcher rejects missing required tool arguments",
        "OpenAI SDK",
        "official OpenAI Python SDK",
        "OpenAI client",
        "responses.create",
        "do not expose API keys",
        "server-side resume confirmation path",
    ):
        assert phrase in combined


def test_openai_responses_structured_output_contract_is_documented_for_agent_use():
    rag_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "vendor"
        / "openai_official_responses_function_tools.md"
    ).read_text(encoding="utf-8")
    developer_contract = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-developer"
        / "references"
        / "contracts.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + developer_contract

    for phrase in (
        "`json_schema`",
        "`text.format`",
        "`json_object`",
        "prefer `json_schema`",
        "compatibility fallback",
        "schema is available",
        "strict structured outputs",
        "reject malformed `structured_schema`",
        "before calling `responses.create`",
        "`additionalProperties=false`",
    ):
        assert phrase in combined


def test_openai_code_interpreter_container_boundary_is_documented_for_agent_use():
    rag_doc = (
        REPO_ROOT
        / "docs"
        / "rag"
        / "vendor"
        / "openai_official_responses_function_tools.md"
    ).read_text(encoding="utf-8")
    developer_contract = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-developer"
        / "references"
        / "contracts.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + developer_contract

    for phrase in (
        "OpenAI Code Interpreter container",
        "Image Agent workflow container",
        "Code Interpreter containers are model/tool execution sandboxes, not Image Agent production workflow containers",
        "do not expose Image Agent workflow containers, shell, Docker, or production task launch privileges directly to the model",
        "Image Agent workflow containers remain backend-orchestrated and server-side gated",
    ):
        assert phrase in combined


def test_openai_sdk_chat_gateway_is_current_in_skill_references():
    paths = [
        REPO_ROOT / "docs" / "skills" / "image-agent-architect" / "SKILL.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-operator" / "references" / "product-context.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-operator" / "references" / "examples-evals.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "implementation-guidance.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "repo-map.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "agent-roles.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "DeepSeek only" not in combined
    assert "DeepSeek orchestration" not in combined
    assert "DeepSeek operator behavior" not in combined
    for phrase in (
        "OpenAI SDK chat gateway",
        "Responses-native",
        "DeepSeek legacy fallback",
        "ModelGateway",
    ):
        assert phrase in combined


def test_dcm2niix_official_conversion_boundaries_are_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag"
    vendor_doc = (rag_root / "vendor" / "dcm2niix_official_conversion.md").read_text(encoding="utf-8")
    data_requirements = (rag_root / "data-requirements" / "modalities-bids.md").read_text(encoding="utf-8")
    troubleshooting = (rag_root / "troubleshooting" / "common-errors.md").read_text(encoding="utf-8")
    combined = vendor_doc + "\n" + data_requirements + "\n" + troubleshooting

    for phrase in (
        "dcm2niix_readme",
        "rordenlab/dcm2niix",
        "DICOM to NIfTI",
        "BIDS sidecar JSON",
        "converted NIfTI",
        "partial conversion failures",
        "DICOM archives are candidates for conversion",
        "not direct production workflow launch",
        "do not expose raw DICOM contents",
        "dcm2niix executable not found",
    ):
        assert phrase in combined


def test_bids_validator_official_cli_boundaries_are_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag"
    raw_manifest = json.loads((rag_root / "vendor" / "raw-sources" / "manifest.json").read_text(encoding="utf-8"))
    source_ids = {source["id"] for source in raw_manifest["sources"]}
    vendor_doc = (rag_root / "vendor" / "bids_validator_official_cli_docker.md").read_text(encoding="utf-8")
    data_requirements = (rag_root / "data-requirements" / "modalities-bids.md").read_text(encoding="utf-8")
    troubleshooting = (rag_root / "troubleshooting" / "common-errors.md").read_text(encoding="utf-8")
    combined = vendor_doc + "\n" + data_requirements + "\n" + troubleshooting

    assert {"bids_validator_cli", "bids_validator_docker"} <= source_ids
    for phrase in (
        "bids_validator_cli",
        "bids_validator_docker",
        "bids-validator <dataset>",
        "--json",
        "--format json",
        "--format json_pp",
        "--ignoreWarnings",
        "--ignoreNiftiHeaders",
        "--datasetTypes",
        "--recursive",
        ".bids-validator-config.json",
        "issues.errors",
        "issues.warnings",
        "summary",
        "machine-readable preflight evidence",
        "warnings remain reportable unless explicitly ignored",
    ):
        assert phrase in combined


def test_workflow_runner_skills_reference_bids_validator_preflight_boundaries():
    paths = [
        REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry-and-preflight.md",
        REPO_ROOT / "docs" / "skills" / "neuroimaging-workflow-runner" / "references" / "bids-inputs.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in (
        "bids_validator_official_cli_docker.md",
        "BIDS Validator",
        "--json",
        "--format json",
        "--ignoreWarnings",
        "--ignoreNiftiHeaders",
        "--datasetTypes",
        "--recursive",
        "machine-readable preflight evidence",
        "warnings remain reportable unless explicitly ignored",
    ):
        assert phrase in combined


def test_qsi_container_contracts_are_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag" / "vendor"
    qsiprep_doc = (rag_root / "qsiprep_official_container_usage_outputs.md").read_text(encoding="utf-8")
    qsirecon_doc = (rag_root / "qsirecon_official_container_usage_workflows.md").read_text(encoding="utf-8")
    workflow_doc = (REPO_ROOT / "docs" / "workflows" / "dwi-qsi-workflow.md").read_text(encoding="utf-8")
    skill_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "neuroimaging-workflow-runner"
        / "references"
        / "container-contracts.md"
    ).read_text(encoding="utf-8")
    combined = qsiprep_doc + "\n" + qsirecon_doc + "\n" + workflow_doc + "\n" + skill_ref

    for phrase in (
        "pennlinc/qsiprep:latest",
        "--eddy-config",
        "QSIPrep visual reports",
        "desc-image_qc.tsv",
        "pennlinc/qsirecon:latest",
        "--recon-spec",
        "dipy_dki",
        "mrtrix_multishell_msmt_noACT",
        "completed QSIPrep output",
        "container-native DWI QC",
        "qsirecon_custom_workflows",
        "Custom Reconstruction Workflows",
        "QSIRecon workflows are defined in YAML files",
        "Pipeline-level metadata",
        "root-level `name`, `anatomical`, and `nodes`",
        "A node in the QSIRecon `nodes` list represents a unit of processing",
        "All nodes must have a name element",
        "custom YAML spec",
        "not arbitrary user-supplied custom specs in production",
    ):
        assert phrase in combined
    assert "custom JSON spec" not in combined


def test_mriqc_dpabi_official_container_boundaries_are_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag"
    mriqc_doc = (rag_root / "vendor" / "mriqc_official_container_usage_outputs.md").read_text(encoding="utf-8")
    dpabi_doc = (rag_root / "vendor" / "dpabi_official_container_boundary.md").read_text(encoding="utf-8")
    rag_priority = (rag_root / "safety" / "rag-priority.md").read_text(encoding="utf-8")
    operator_boundaries = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-operator"
        / "references"
        / "failures-and-boundaries.md"
    ).read_text(encoding="utf-8")
    combined = mriqc_doc + "\n" + dpabi_doc + "\n" + rag_priority + "\n" + operator_boundaries

    for phrase in (
        "mriqc_usage",
        "mriqc_reports",
        "mriqc_installation",
        "nipreps_docker_guidelines",
        "nipreps_singularity_guidelines",
        "mriqc /data /out participant",
        "--no-sub",
        "individual visual reports",
        "group visual report",
        "IQMs",
        "not registered in WORKFLOW_REGISTRY",
        "not a production Image Agent workflow",
        "production_task_created=false unless a future backend workflow is added",
        "dpabi_standalone_docker",
        "dpabisurfslurm_hpc_singularity",
        "dpabi_dockerfile",
        "dpabi_docker_hub",
        "cgyan/dpabi",
        "DPABISurfSlurm",
        "external ecosystem boundary",
        "not a supported Image Agent workflow",
        "do not add DPABI to container-native QC accepted source ids",
    ):
        assert phrase in combined


def test_fast_dti_toolbox_contract_is_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag" / "vendor"
    workflow_doc = (REPO_ROOT / "docs" / "rag" / "workflows" / "dwi_fast_gpu_dti.md").read_text(encoding="utf-8")
    fsl_doc = (rag_root / "fsl_official_fast_dti_tools.md").read_text(encoding="utf-8")
    mrtrix_doc = (rag_root / "mrtrix3_official_dti_toolbox.md").read_text(encoding="utf-8")
    workflow_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "neuroimaging-workflow-runner"
        / "references"
        / "output-discovery.md"
    ).read_text(encoding="utf-8")
    combined = workflow_doc + "\n" + fsl_doc + "\n" + mrtrix_doc + "\n" + workflow_ref

    for phrase in (
        "dwi_fast_gpu_dti",
        "host FSL",
        "eddy_cuda",
        "dtifit",
        "flirt",
        "applywarp probe",
        "FNIRT/applywarp",
        "fslmaths",
        "FSL utilities",
        "mrinfo",
        "mrstats",
        "mrcalc",
        "dwi2mask",
        "mrconvert",
        "dwi2tensor",
        "tensor2metric",
        "FA/MD/AD/RD",
        "full_qsiprep_run: false",
        "full_qsirecon_run: false",
        "container-native DWI QC",
        "outputs.reports",
        "dwi_tensor_metrics.png",
        "dwi_atlas_region_means.png",
        "derived_presentation_asset",
        "generated_from_result_summary",
        "native_artifact: false",
        "replaces_native_qc: false",
        "not full QSIPrep",
    ):
        assert phrase in combined


def test_xcpd_remote_wrapper_flags_and_artifact_boundaries_are_documented_for_agent_use():
    rag_root = REPO_ROOT / "docs" / "rag"
    workflow_doc = (rag_root / "workflows" / "bold_fmriprep_xcpd_report.md").read_text(encoding="utf-8")
    xcpd_usage = (rag_root / "vendor" / "xcp_d_official_container_usage.md").read_text(encoding="utf-8")
    xcpd_outputs = (rag_root / "vendor" / "xcp_d_official_outputs.md").read_text(encoding="utf-8")
    troubleshooting = (rag_root / "troubleshooting" / "common-errors.md").read_text(encoding="utf-8")
    workflow_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "container-qc-artifacts.md"
    ).read_text(encoding="utf-8")
    preflight_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "registry-and-preflight.md"
    ).read_text(encoding="utf-8")
    combined = "\n".join([workflow_doc, xcpd_usage, xcpd_outputs, troubleshooting, workflow_ref, preflight_ref])

    for phrase in (
        "run_xcpd_deepprep_115.sh",
        "DeepPrep-derived fMRIPrep-compatible input",
        "`--mode linc`",
        "`--input-type fmriprep`",
        "`--file-format nifti`",
        "`--linc-qc y`",
        "`--abcc-qc y`",
        "`IMAGE_AGENT_TASK_XCPD_DIR`",
        "`IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR`",
        "TemplateFlow cache is a support mount",
        "source_stage: xcpd",
        "container-native XCP-D QC",
        "not raw BIDS",
    ):
        assert phrase in combined


def test_agent_run_ledger_contract_is_documented_for_agent_use():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "agent-run-ledger.md").read_text(encoding="utf-8")
    developer_contract = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-developer"
        / "references"
        / "contracts.md"
    ).read_text(encoding="utf-8")
    combined = rag_doc + "\n" + developer_contract

    for phrase in (
        "agent-run ledger",
        "durable agent-run trace",
        "agent_run_id",
        "agent_run_created",
        "agent_run_started",
        "agent_run_completed",
        "agent_run_failed",
        "agent_run_cancelled",
        "agent_run_skipped",
        "model_gateway_access",
        "tool_invocations",
        "backend task rows remain authoritative",
        "result-summary JSON remains authoritative for completed workflow outputs",
        "privacy-safe lifecycle traceability",
        "redacted user message summary",
        "do not store raw image contents",
        "do not expose patient identifiers",
        "do not expose full sensitive host paths",
        "do not expose API keys, bearer tokens, FreeSurfer license text, or raw DICOM contents",
        "production task creation remains gated outside the planner loop",
        "server-side resume confirmation path",
        "GET /agent/runs/{agent_run_id}",
        "unknown request fields return `request_contract_violation`",
        "nested confirmation fields are also strict",
        "ledger-only envelope",
        "safe_metadata",
        "retrieved_sources",
        "not the original agent result",
        "do not expose raw answer text",
        "GET /projects/{project_id}/agent-runs",
        "project-scoped agent-run history",
        "newest first",
        "event_count",
        "safe project run summary",
        "safe_metadata excludes free-form model text",
        "absolute host paths are not valid retrieved_sources",
        "redacted_error_summary",
        "expires_at",
        "pending confirmations are single-use",
        "expired confirmations return blocked",
        "lookup/list responses re-sanitize stored JSON",
        "retrieved_sources expose source ids only",
        "titles and snippets are not ledger fields",
        "safe_metadata uses an allowlist",
    ):
        assert phrase in combined


def test_agent_run_ledger_trace_fields_do_not_allow_model_free_text():
    rag_doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "agent-run-ledger.md").read_text(encoding="utf-8")
    trace_fields = rag_doc.split("## Trace Fields", 1)[1].split("Production task creation remains", 1)[0]

    for field in ("recommended_next_step", "tool_chain_hint"):
        assert f"`{field}`" not in trace_fields


def test_remote_smoke_acceptance_gate_is_documented_for_agent_use():
    production_doc = (REPO_ROOT / "docs" / "deployment" / "remote-agent-production.md").read_text(encoding="utf-8")

    for phrase in (
        "strict remote acceptance gate",
        "`--require-model`",
        "`--min-documents`",
        "`--min-chunks`",
        "`--require-raw-source-policy`",
        "`--require-vendor-pointer-integrity`",
        "`--require-real-evidence-ids`",
        "`--require-launchability-matrix`",
        "`--require-container-native-qc`",
        "`--min-native-qc-images`",
        "`--require-scientific-report-artifacts`",
        "`--min-scientific-report-images`",
        "`--project-id`",
        "`--task-id`",
        "`--upload-session-id`",
        "`workflow_eligibility`",
        "`/projects/{project_id}/datasets/{upload_session_id}/inventory`",
        "`/tasks/{task_id}/artifact-manifest`",
        "`task_artifact_manifest_status=passed`",
        "`upload_inventory_contract_status=passed`",
        "`remote_evidence_ids_status=passed`",
        "`rag_vendor_pointer_integrity_status=passed`",
        "`rag_vendor_pointer_integrity_referenced_vendor_docs`",
        "`rag_vendor_coverage_catalog_status=complete`",
        "`rag_vendor_coverage_catalog_vendor_doc_count`",
        "`rag_vendor_coverage_catalog_complete_vendor_doc_count`",
        "`vendor_coverage_catalog.vendors`",
        "`rag_raw_sources.curated_sources`",
        "must exactly match",
        "no missing or extra vendor docs",
        "`rag_launchability_matrix_status=passed`",
        "`rag_launchability_matrix_source`",
        "`rag_launchability_query_status=passed`",
        "`rag_launchability_query_source`",
        "`container_native_qc_status=passed`",
        "`container_native_qc_served_urls`",
        "`container_native_qc_artifacts`",
        "`container_native_qc_official_source_ids`",
        "container-native QC artifact `relative_path` is slash-relative and safe",
        "container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`",
        "container-native QC artifact `content_type` matches `preview_kind`",
        "`scientific_report_artifacts_status=passed`",
        "`scientific_report_artifacts`",
        "`scientific_report_relative_paths`",
        "`scientific_report_served_urls`",
        "scientific report artifact `download_url` is served with non-empty bytes",
        "scientific report artifact `content_type` matches `preview_kind`",
        "`reports/index.html`",
        "`reports/report_manifest.json`",
        "`source_stage=scientific_report`",
        "`artifact_role=derived_presentation_asset`",
        "`artifact_origin=generated_from_result_summary`",
        "`native_artifact=false`",
        "`provenance.replaces_native_qc=false`",
        "`/agent/rag/query`",
        "`curated_provenance_ok=true`",
        "`curated_provenance_issues=[]`",
        "`manifest_schema_version`",
        "`source_count`",
        "`vendor_doc_count`",
        "`manifest_backed=true`",
        "`source_url_backed=true`",
        "non-empty `source_types`",
        "`/health`",
        "`app=image_agent`",
        "configured `/agent/runs` must return `status=answered`",
        "`model_smoke_status=passed`",
        "`agent_run_id`",
        "`semantic_index=true`",
        "missing model gateway is a skip only when `--require-model` is omitted",
        "`--output-json`",
        "strict smoke acceptance JSON",
    ):
        assert phrase in production_doc


def test_remote_acceptance_evidence_template_requires_strict_model_and_restart_evidence():
    template = (REPO_ROOT / "docs" / "deployment" / "remote-agent-acceptance-template.md").read_text(encoding="utf-8")

    for phrase in (
        "remote git branch/status",
        "deployed file hashes",
        "`/agent/model/status` reports `configured=true`",
        "`model_smoke_status=passed`",
        "`skipped_missing_model_config` is not production acceptance",
        "`agent_run_id`",
        "`intent`",
        "`selected_skill`",
        "`project_contract_status=passed`",
        "`upload_inventory_contract_status=passed`",
        "`task_artifact_manifest_status=passed`",
        "`remote_evidence_ids_status=passed`",
        "`rag_vendor_pointer_integrity_status=passed`",
        "`rag_vendor_pointer_integrity_referenced_vendor_docs`",
        "`rag_vendor_coverage_catalog_status=complete`",
        "`rag_vendor_coverage_catalog_vendor_doc_count`",
        "`vendor_coverage_catalog`",
        "`vendor_coverage_catalog.vendors`",
        "`rag_raw_sources.curated_sources`",
        "must exactly match",
        "no missing or extra vendor docs",
        "`rag_launchability_matrix_status=passed`",
        "`rag_launchability_matrix_source`",
        "`rag_launchability_query_status=passed`",
        "`rag_launchability_query_intent`",
        "`rag_launchability_query_source`",
        "`container_native_qc_status=passed`",
        "`container_native_qc_artifact_count`",
        "`container_native_qc_image_count`",
        "`container_native_qc_relative_paths`",
        "`container_native_qc_served_urls`",
        "`container_native_qc_artifacts`",
        "`container_native_qc_official_source_ids`",
        "container-native QC artifact `relative_path` is slash-relative and safe",
        "container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`",
        "container-native QC artifact `content_type` matches `preview_kind`",
        "`scientific_report_artifacts_status=passed`",
        "`scientific_report_artifact_count`",
        "`scientific_report_image_count`",
        "`scientific_report_relative_paths`",
        "`scientific_report_served_urls`",
        "`scientific_report_artifacts`",
        "`upload_inventory_series_with_workflow_eligibility`",
        "`artifact_manifest_preview_kinds`",
        "`curated_sources`",
        "`raw_source_ids`",
        "`source_urls`",
        "`raw_files`",
        "`manifest_schema_version`",
        "`source_count`",
        "`vendor_doc_count`",
        "`manifest_backed=true`",
        "`source_url_backed=true`",
        "non-empty `source_types`",
        "`complete=true`",
        "`active_task_drain:ok`",
        "`port_owner:image_agent`",
        "`health:ok app=image_agent`",
        "strict smoke acceptance JSON",
        "restart drain evidence",
        "`curated_provenance_ok=true`",
        "`curated_provenance_issues=[]`",
    ):
        assert phrase in template


def test_remote_smoke_acceptance_json_verifier_is_documented():
    paths = [
        REPO_ROOT / "docs" / "deployment" / "remote-agent-production.md",
        REPO_ROOT / "docs" / "deployment" / "remote-agent-acceptance-template.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "testing-matrix.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in (
        "`apps/api/scripts/verify_remote_smoke_acceptance.py`",
        "offline strict smoke acceptance JSON verifier",
        "`python scripts/verify_remote_smoke_acceptance.py`",
        "`status=passed`",
        "does not replace running `smoke_remote_agent.py` on the remote server",
        "`model_smoke_status=passed`",
        "`remote_evidence_ids_status=passed`",
        "`rag_vendor_pointer_integrity_status=passed`",
        "`require_vendor_pointer_integrity`",
        "`rag_vendor_pointer_integrity_referenced_vendor_docs`",
        "`rag_vendor_coverage_catalog_status=complete`",
        "`vendor_coverage_catalog`",
        "`vendor_coverage_catalog.vendors`",
        "`rag_raw_sources.curated_sources`",
        "must exactly match",
        "no missing or extra vendor docs",
        "`rag_raw_sources.manifest_schema_version`",
        "`rag_raw_sources.source_count`",
        "`rag_raw_sources.vendor_doc_count`",
        "must not expose `manifest_path`, `persist_dir`, `raw_snapshots`, `raw_files`, or `sha256`",
        "`rag_launchability_query_status=passed`",
        "`container_native_qc_status=passed`",
        "`container_native_qc_served_urls`",
        "`container_native_qc_artifacts`",
        "`container_native_qc_official_source_ids`",
        "container-native QC artifact `relative_path` is slash-relative and safe",
        "container-native QC artifact `download_url` is recomputed from `task_id` and `relative_path`",
        "container-native QC artifact `content_type` matches `preview_kind`",
        "`scientific_report_artifacts_status=passed`",
        "`scientific_report_artifacts`",
    ):
        assert phrase in combined


def test_developer_testing_matrix_requires_deployment_identity_for_strict_smoke():
    matrix = (
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "testing-matrix.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "`--require-deployment-identity`",
        "`--deployment-id`",
        "`deployment_identity_status=passed`",
        "`deployment_identity.deployment_id`",
        "`deployment_identity.health_version`",
        "`smoke_gate.deployment_id`",
        "privacy-safe",
        "`python scripts/verify_remote_smoke_acceptance.py --max-age-hours 24 <remote-smoke-acceptance.json>`",
    ):
        assert phrase in matrix


def test_developer_testing_matrix_requires_stale_task_gate_before_strict_acceptance():
    matrix = (
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "testing-matrix.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "approved stale-task reconciliation",
        "`verify_stale_task_approval.py`",
        "`verify_stale_task_resolution.py`",
        "`--approval-json`",
        "`--require-empty-active`",
        "`approval_fingerprint`",
        "`out_of_scope_stale_task_ids=[]`",
        "`running_container_task_ids=[]`",
        "`blocked_task_ids=[]`",
        "reject `log_path`",
        "reject backend absolute paths",
        "stale-task evidence must pass a `max_age_hours` freshness limit",
        "timezone-aware `generated_at`",
        "resolution `generated_at` must be after or equal to apply `generated_at`",
        "normal restart without `IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`",
    ):
        assert phrase in matrix


def test_remote_script_timeout_and_log_safety_are_documented_for_agent_use():
    paths = [
        REPO_ROOT / "docs" / "deployment" / "remote-agent-production.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "security-and-containers.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "registry-and-preflight.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-workflow-runner" / "references" / "task-events-and-results.md",
        REPO_ROOT / "docs" / "rag" / "workflows" / "bold_fmriprep_xcpd_report.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in (
        "IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC",
        "remote script timed out",
        "redacted log tail",
        "safe child environment allowlist",
        "do not pass `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `IMAGE_AGENT_SUDO_PASSWORD`",
        "TimeoutExpired",
        "script stdout/stderr must be redacted",
        "partial stdout retention",
        "script paths must be regular files, not directories",
        "raised wrapper errors should use path-safe script labels",
        "success summaries use path-safe script labels",
        "public preflight check summaries use path-safe labels",
    ):
        assert phrase in combined


def test_rag_curator_documents_machine_readable_curated_source_coverage():
    reference = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-rag-curator"
        / "references"
        / "source-metadata-and-priority.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "`vendor_raw_sources.curated_sources`",
        "`vendor_coverage_catalog`",
        "`policy`",
        "`complete_vendor_doc_count`",
        "`incomplete_vendor_doc_count`",
        "`pointer_integrity_ok`",
        "`referenced_by`",
        "`source_url`",
        "`raw_source_ids`",
        "`raw_files`",
        "`manifest_backed`",
        "`source_url_backed`",
        "`complete`",
        "`manifest_schema_version`",
        "`source_count`",
        "`vendor_doc_count`",
        "provenance pointer integrity gate",
        "`raw_source_ids` are manifest ids, not `official_source_ids`",
        "Curated vendor summaries are answer sources; raw snapshots are provenance evidence only",
        "`curated_provenance_ok=true`",
        "`curated_provenance_issues=[]`",
        "`curated_sources[*].complete=true`",
        "does not include raw HTML or raw snapshot text",
        "must not be indexed wholesale",
    ):
        assert phrase in reference


def test_rag_workflow_and_contract_vendor_pointers_have_raw_source_provenance():
    from app.agent.rag_index import rag_vendor_pointer_integrity

    status = rag_vendor_pointer_integrity(root=REPO_ROOT)

    assert status["ok"] is True
    assert status["raw_source_manifest_exists"] is True
    assert status["curated_provenance_ok"] is True
    assert status["issue_count"] == 0
    assert status["pointer_count"] >= 30
    for source_doc in (
        "docs/rag/contracts/container-qc-artifacts.md",
        "docs/rag/workflows/bold_fmriprep_xcpd_report.md",
        "docs/rag/workflows/dwi_fast_gpu_dti.md",
        "docs/rag/workflows/workflow_launchability_matrix.md",
    ):
        assert source_doc in status["pointers_by_doc"]


def test_workflow_launchability_matrix_documents_supported_and_external_boundaries():
    matrix = (
        REPO_ROOT / "docs" / "rag" / "workflows" / "workflow_launchability_matrix.md"
    ).read_text(encoding="utf-8")
    rag_curator_ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-rag-curator"
        / "references"
        / "source-metadata-and-priority.md"
    ).read_text(encoding="utf-8")
    rag_curator_skill = (
        REPO_ROOT / "docs" / "skills" / "image-agent-rag-curator" / "SKILL.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "source_type: rag_workflow",
        "workflow_type: workflow_launchability_matrix",
        "`production_supported`",
        "`incubation_reference`",
        "`external_reference_only`",
        "`unsupported_external`",
        "`t1_deepprep`",
        "`bold_deepprep`",
        "`bold_second_level`",
        "`bold_fmriprep_xcpd_report`",
        "`IMAGE_AGENT_TASK_*`",
        "Do not call it production-ready unless wrapper and real task evidence exist",
        "`dwi_fast_gpu_dti`",
        "`dwi_qsiprep`",
        "`dwi_qsirecon`",
        "`dwi_qsi_full`",
        "`mriqc`",
        "`dpabi`",
        "Do not create production tasks from this matrix",
        "`workflow_eligibility` remains authoritative for launchability",
        "`/tasks/{task_id}/result-summary` remains authoritative for completed outputs",
        "Remote promotion requires real task ids",
        "container-native QC source ids",
        "docs/rag/vendor/mriqc_official_container_usage_outputs.md",
        "docs/rag/vendor/dpabi_official_container_boundary.md",
        "docs/rag/vendor/qsiprep_official_container_usage_outputs.md",
        "docs/rag/vendor/qsirecon_official_container_usage_workflows.md",
    ):
        assert phrase in matrix

    assert "workflow_launchability_matrix.md" in rag_curator_ref
    assert "workflow maturity / launchability matrix" in rag_curator_ref
    assert "../../rag/workflows/workflow_launchability_matrix.md" in rag_curator_skill
    assert "workflow support, maturity, or launchability" in rag_curator_skill
    assert "RAG status/index presence alone is not sufficient" in rag_curator_skill


def test_image_agent_skill_references_document_backend_readiness_contracts():
    developer_contracts = (
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "contracts.md"
    ).read_text(encoding="utf-8")
    testing_matrix = (
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "testing-matrix.md"
    ).read_text(encoding="utf-8")
    runner_results = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "task-events-and-results.md"
    ).read_text(encoding="utf-8")
    artifact_review = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-result-reviewer"
        / "references"
        / "artifact-review.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "`workflow_eligibility`",
        "`policy_version=workflow_eligibility_v1`",
        "`production_task_created=false`",
        "`runnable_workflows`",
        "`blocked_workflows`",
        "`primary_recommendation`",
        "`/projects/{project_id}/datasets/{upload_session_id}/inventory`",
        "side-effect-free",
    ):
        assert phrase in developer_contracts

    for phrase in (
        "`--project-id`",
        "`--upload-session-id`",
        "`--task-id`",
        "`--require-real-evidence-ids`",
        "`--require-launchability-matrix`",
        "`--require-container-native-qc`",
        "`--min-native-qc-images`",
        "`--require-scientific-report-artifacts`",
        "`--min-scientific-report-images`",
        "`project_contract_status=passed`",
        "`upload_inventory_contract_status=passed`",
        "`task_artifact_manifest_status=passed`",
        "`remote_evidence_ids_status=passed`",
        "`rag_launchability_matrix_status=passed`",
        "`rag_launchability_query_status=passed`",
        "`rag_launchability_query_source`",
        "`container_native_qc_status=passed`",
        "`container_native_qc_served_urls`",
        "`container_native_qc_artifacts`",
        "`container_native_qc_official_source_ids`",
        "`scientific_report_artifacts_status=passed`",
        "`scientific_report_artifacts`",
        "`scientific_report_relative_paths`",
        "`scientific_report_served_urls`",
        "`vendor_coverage_catalog.vendors`",
        "`rag_raw_sources.curated_sources`",
        "must exactly match",
        "no missing or extra vendor docs",
        "unsafe artifact-manifest paths",
        "malformed `workflow_eligibility`",
        "RAG launchability matrix query citation missing",
    ):
        assert phrase in testing_matrix

    for phrase in (
        "`contract_version=artifact_manifest_v1`",
        "matching `task_id`",
        "`preview_kind`",
        "`relative_path`",
        "`download_url`",
        "`content_type`",
        "`size_bytes`",
        "no backend `path` leakage",
    ):
        assert phrase in runner_results

    for phrase in (
        "`/tasks/{task_id}/artifact-manifest`",
        "preferred frontend-readiness source",
        "manifest envelope uses `contract_version=artifact_manifest_v1`",
        "artifact items carry",
        "no backend `path` leakage",
    ):
        assert phrase in artifact_review


def test_scientific_report_verifier_requires_native_qc_gate_in_docs():
    paths = [
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "contracts.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "testing-matrix.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "skill-maintenance.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-result-reviewer" / "references" / "container-qc-artifacts.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for phrase in (
        "`python apps/api/scripts/verify_scientific_reports.py`",
        "`--require-container-native-qc`",
        "`--min-native-qc-images 1`",
        "derived presentation",
        "container-native QC",
        "does not replace native QC",
    ):
        assert phrase in combined


def test_remote_wrapper_sudo_docs_distinguish_backend_helpers_from_child_scripts():
    doc = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "security-and-containers.md"
    ).read_text(encoding="utf-8")

    assert "backend-owned sudo helper" in doc
    assert "child workflow scripts must not receive `IMAGE_AGENT_SUDO_PASSWORD`" in doc


def test_registry_preflight_reference_documents_remote_wrapper_hardening():
    doc = (
        REPO_ROOT
        / "docs"
        / "skills"
        / "image-agent-workflow-runner"
        / "references"
        / "registry-and-preflight.md"
    ).read_text(encoding="utf-8")

    for phrase in (
        "IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC",
        "script paths must be regular files, not directories",
        "public preflight check summaries use path-safe labels",
        "raised wrapper errors should use path-safe script labels",
        "script stdout/stderr must be redacted",
    ):
        assert phrase in doc


def test_task_event_rag_contract_documents_remote_wrapper_public_surfaces():
    doc = (REPO_ROOT / "docs" / "rag" / "contracts" / "task-events.md").read_text(encoding="utf-8")

    for phrase in (
        "remote script timed out",
        "redacted log tail",
        "script stdout/stderr must be redacted",
        "script paths must be regular files, not directories",
        "raised wrapper errors should use path-safe script labels",
        "success summaries use path-safe script labels",
    ):
        assert phrase in doc


def test_production_dwi_real_run_evidence_is_current_in_skills():
    paths = [
        REPO_ROOT / "docs" / "skills" / "neuroimaging-workflow-runner" / "SKILL.md",
        REPO_ROOT / "docs" / "skills" / "neuroimaging-workflow-runner" / "references" / "container-contracts.md",
        REPO_ROOT / "docs" / "skills" / "neuroimaging-workflow-runner" / "references" / "output-discovery.md",
        REPO_ROOT / "docs" / "skills" / "image-agent-developer" / "references" / "skill-maintenance.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "final release still needs another real sample" not in combined
    assert "still require another sample or mixed project" not in combined
    for phrase in (
        "task `107`",
        "runtime_sec=1156",
        "task `112`",
        "runtime_sec=1042",
        "task `114`",
        "runtime_sec=1021",
        "mixed project",
        "validation_only=false",
    ):
        assert phrase in combined


def test_vendor_doc_fetcher_can_refresh_manifest_with_hashes(tmp_path):
    script_path = REPO_ROOT / "apps" / "api" / "scripts" / "fetch_vendor_docs.py"
    spec = importlib.util.spec_from_file_location("fetch_vendor_docs", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    sources = [
        {
            "id": "demo_source",
            "vendor_doc": "demo_vendor.md",
            "url": "https://example.org/demo",
            "file": "demo.html",
            "source_type": "official_docs",
        }
    ]

    manifest = module.download_vendor_sources(
        raw_root=tmp_path,
        sources=sources,
        fetch_bytes=lambda url: b"<html>official docs</html>",
        generated_at="2026-06-07T00:00:00Z",
        retrieved_at="2026-06-07T00:00:01Z",
    )

    raw_file = tmp_path / "demo.html"
    assert raw_file.exists()
    assert manifest["schema_version"] == 1
    assert manifest["generated_at"] == "2026-06-07T00:00:00Z"
    assert manifest["sources"][0]["sha256"] == hashlib.sha256(raw_file.read_bytes()).hexdigest()
    assert manifest["sources"][0]["bytes"] == raw_file.stat().st_size
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8")) == manifest


def test_vendor_doc_fetcher_retries_transient_download_errors(tmp_path):
    script_path = REPO_ROOT / "apps" / "api" / "scripts" / "fetch_vendor_docs.py"
    spec = importlib.util.spec_from_file_location("fetch_vendor_docs", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    sources = [
        {
            "id": "retry_source",
            "vendor_doc": "retry_vendor.md",
            "url": "https://example.org/retry",
            "file": "retry.html",
            "source_type": "official_docs",
        }
    ]
    attempts = {"count": 0}

    def flaky_fetch(url: str) -> bytes:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError("transient SSL handshake timeout")
        return b"<html>official docs after retry</html>"

    manifest = module.download_vendor_sources(
        raw_root=tmp_path,
        sources=sources,
        fetch_bytes=flaky_fetch,
        retry_attempts=2,
        generated_at="2026-06-07T00:00:00Z",
        retrieved_at="2026-06-07T00:00:01Z",
    )

    assert attempts["count"] == 2
    assert (tmp_path / "retry.html").read_bytes() == b"<html>official docs after retry</html>"
    assert manifest["sources"][0]["id"] == "retry_source"
    assert manifest["sources"][0]["status"] == "downloaded"


def test_vendor_doc_fetcher_can_use_existing_snapshot_after_retries_fail(tmp_path):
    script_path = REPO_ROOT / "apps" / "api" / "scripts" / "fetch_vendor_docs.py"
    spec = importlib.util.spec_from_file_location("fetch_vendor_docs", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    sources = [
        {
            "id": "cached_source",
            "vendor_doc": "cached_vendor.md",
            "url": "https://example.org/cached",
            "file": "cached.html",
            "source_type": "official_docs",
        }
    ]
    cached = tmp_path / "cached.html"
    cached.write_bytes(b"<html>previously downloaded official docs</html>")
    attempts = {"count": 0}

    def unavailable_fetch(url: str) -> bytes:
        attempts["count"] += 1
        raise TimeoutError("remote host cannot reach official source")

    manifest = module.download_vendor_sources(
        raw_root=tmp_path,
        sources=sources,
        fetch_bytes=unavailable_fetch,
        retry_attempts=2,
        retry_delay_seconds=0,
        use_existing_on_failure=True,
        generated_at="2026-06-07T00:00:00Z",
        retrieved_at="2026-06-07T00:00:01Z",
    )

    assert attempts["count"] == 2
    assert cached.read_bytes() == b"<html>previously downloaded official docs</html>"
    assert manifest["sources"][0]["status"] == "downloaded"
    assert manifest["sources"][0]["download_mode"] == "existing_snapshot_after_fetch_error"
    assert "remote host cannot reach official source" in manifest["sources"][0]["fetch_error"]


def test_vendor_doc_fetcher_passes_configured_timeout_to_default_fetcher(tmp_path):
    script_path = REPO_ROOT / "apps" / "api" / "scripts" / "fetch_vendor_docs.py"
    spec = importlib.util.spec_from_file_location("fetch_vendor_docs", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    sources = [
        {
            "id": "timeout_source",
            "vendor_doc": "timeout_vendor.md",
            "url": "https://example.org/timeout",
            "file": "timeout.html",
            "source_type": "official_docs",
        }
    ]
    observed = {}

    def fake_fetch_url(url: str, *, timeout: int = 60) -> bytes:
        observed["url"] = url
        observed["timeout"] = timeout
        return b"<html>official docs with custom timeout</html>"

    module.fetch_url = fake_fetch_url
    module.download_vendor_sources(
        raw_root=tmp_path,
        sources=sources,
        fetch_timeout_seconds=7,
        generated_at="2026-06-07T00:00:00Z",
        retrieved_at="2026-06-07T00:00:01Z",
    )

    assert observed == {"url": "https://example.org/timeout", "timeout": 7}


def test_vendor_doc_fetcher_can_merge_new_sources_into_existing_manifest(tmp_path):
    script_path = REPO_ROOT / "apps" / "api" / "scripts" / "fetch_vendor_docs.py"
    spec = importlib.util.spec_from_file_location("fetch_vendor_docs", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    existing_file = tmp_path / "existing.html"
    existing_file.write_bytes(b"<html>existing official docs</html>")
    existing_source = {
        "id": "existing_source",
        "vendor_doc": "existing_vendor.md",
        "url": "https://example.org/existing",
        "file": "existing.html",
        "source_type": "official_docs",
        "retrieved_at": "2026-06-07T00:00:00Z",
        "sha256": hashlib.sha256(existing_file.read_bytes()).hexdigest(),
        "bytes": existing_file.stat().st_size,
        "status": "downloaded",
        "download_mode": "fresh_download",
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-06-07T00:00:00Z",
                "note": "Raw official source snapshots for curated vendor RAG summaries. Do not index wholesale; use as traceable source evidence.",
                "sources": [existing_source],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    new_sources = [
        {
            "id": "new_source",
            "vendor_doc": "new_vendor.md",
            "url": "https://example.org/new",
            "file": "new.html",
            "source_type": "official_docs",
        }
    ]

    manifest = module.download_vendor_sources(
        raw_root=tmp_path,
        sources=new_sources,
        fetch_bytes=lambda url: b"<html>new official docs</html>",
        generated_at="2026-06-08T00:00:00Z",
        retrieved_at="2026-06-08T00:00:01Z",
        merge_existing_manifest=True,
    )

    sources_by_id = {source["id"]: source for source in manifest["sources"]}
    assert sources_by_id["existing_source"] == existing_source
    assert sources_by_id["new_source"]["sha256"] == hashlib.sha256((tmp_path / "new.html").read_bytes()).hexdigest()
    assert [source["id"] for source in manifest["sources"]] == ["existing_source", "new_source"]


def test_product_readiness_gate_blocks_frontend_until_agent_contracts_are_verified():
    gate = (REPO_ROOT / "docs" / "product-readiness.md").read_text(encoding="utf-8")

    for phrase in (
        "Frontend Design Freeze Gate",
        "Do not start frontend page design",
        "OpenAI SDK Responses-style",
        "durable run/thread state",
        "official-source RAG",
        "raw-source manifest",
        "container-native QC",
        "Docker/container-native",
        "skill-creator-style",
        "strict remote acceptance",
        "verify_remote_smoke_acceptance.py",
        "stale-task evidence must pass a `max_age_hours` freshness limit",
        "verify_stale_task_resolution.py",
        "model_smoke_status=passed",
        "container_native_qc_status=passed",
        "scientific_report_artifacts_status=passed",
        "remote server",
    ):
        assert phrase in gate

    assert "skipped_missing_model_config" in gate
    assert "is not production acceptance" in gate
