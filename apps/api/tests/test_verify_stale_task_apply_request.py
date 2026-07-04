import importlib.util
import ast
import json
from pathlib import Path

import pytest

from tests.test_build_stale_task_apply_request import load_module as load_builder
from tests.test_verify_stale_task_approval import _approval_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_stale_task_apply_request.py"
RELEASE_GATE_VERIFIER_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_release_gate_command_plan.py"
REMOTE_LIVE_ROOT_SNIPPET = "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent"
PRODUCTION_CORS_ORIGINS = "https://console.image-agent.example.com"
PRODUCTION_PUBLIC_BASE_URL = "https://api.image-agent.example.com"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_stale_task_apply_request", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _request_payload(tmp_path):
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")
    builder = load_builder()
    return builder.build_apply_request(
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:00:00Z",
        output_timestamp="20260612T050000Z",
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        remote_nifti_file="/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
        workflow_type="t1_deepprep_anat_report",
        project_id=13,
        upload_session_id=77,
        production_cors_origins=PRODUCTION_CORS_ORIGINS,
        production_public_base_url=PRODUCTION_PUBLIC_BASE_URL,
    )


def _release_gate_required_strict_expected_success() -> tuple[set[str], set[str]]:
    tree = ast.parse(RELEASE_GATE_VERIFIER_PATH.read_text(encoding="utf-8"))
    smoke_required: set[str] = set()
    verifier_required: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (
                isinstance(target, ast.Name)
                and target.id.startswith("required_")
                and target.id.endswith("_expected_success")
            ):
                continue
            expected_map = ast.literal_eval(node.value)
            if isinstance(expected_map, dict):
                smoke_required.update(expected_map.keys())
                verifier_required.update(expected_map.values())
    assert "launched_task.launch_source=agent_workflow_resume" in smoke_required
    assert "checked.launched_task_launch_source=agent_workflow_resume" in verifier_required
    return smoke_required, verifier_required


def _release_gate_required_elasticsearch_prereq_expected_success() -> set[str]:
    tree = ast.parse(RELEASE_GATE_VERIFIER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and node.target.id == "required_success"
        ):
            continue
        try:
            expected_values = ast.literal_eval(node.iter)
        except ValueError:
            continue
        if "rag_status_engine=elasticsearch_hybrid" in expected_values:
            return set(expected_values)
    raise AssertionError("release gate ES hybrid prerequisite expected_success list not found")


def _release_gate_static_strict_smoke_flags() -> set[str]:
    tree = ast.parse(RELEASE_GATE_VERIFIER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "static_strict_smoke_flags":
                flags = ast.literal_eval(node.value)
                assert "--require-elasticsearch-hybrid-rag" in flags
                assert "--require-observe-repair" in flags
                return set(flags)
    raise AssertionError("release gate strict smoke static flags not found")


def test_verify_stale_task_apply_request_accepts_complete_request(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)

    report = verifier.verify_apply_request(
        request,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:30:00Z",
    )

    assert report["status"] == "passed"
    assert report["checked"]["request_type"] == "stale_task_apply_approval"
    assert report["checked"]["authorization_required"] is True
    assert report["checked"]["target_task_ids"] == [83, 84]
    assert report["checked"]["approval_fingerprint"] == request["approval_fingerprint"]
    assert report["checked"]["expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
    assert report["checked"]["followup_step_ids"] == [
        "collect_post_apply_clean_dry_run",
        "verify_post_apply_clean_resolution",
        "verify_docker_host_policy_dry_run",
        "verify_rawchat_direct_connectivity",
        "apply_production_readiness_env",
        "restart_api_preflight_only",
        "restart_api_normally",
        "verify_elasticsearch_hybrid_prerequisites",
        "run_strict_remote_smoke_acceptance",
        "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
        "emit_fast_launch_acceptance_env_after_strict_verify",
        "restart_api_after_fast_launch_acceptance_env",
        "verify_final_fast_launch_readiness",
    ]


def test_verify_stale_task_apply_request_accepts_existing_uploaded_series_smoke_source(tmp_path):
    verifier = load_verifier()
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")
    builder = load_builder()
    request = builder.build_apply_request(
        approval_json=approval_json,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:00:00Z",
        output_timestamp="20260612T050000Z",
        deployment_id="codex-gate-verifiers-efca895b",
        expected_health_version="0.2.0-efca895b",
        uploaded_series_id=49,
        workflow_type="t1_deepprep_anat_report",
        project_id=27,
        upload_session_id=10,
        production_cors_origins=PRODUCTION_CORS_ORIGINS,
        production_public_base_url=PRODUCTION_PUBLIC_BASE_URL,
    )

    report = verifier.verify_apply_request(
        request,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-12T05:30:00Z",
    )

    strict_smoke = next(
        step for step in request["required_followup_steps"] if step["id"] == "run_strict_remote_smoke_acceptance"
    )
    assert report["status"] == "passed"
    assert "--uploaded-series-id 49" in strict_smoke["command"]
    assert "--upload-nifti-file" not in strict_smoke["command"]


def test_verify_stale_task_apply_request_rejects_production_origin_placeholders(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    production_env = next(
        step for step in request["required_followup_steps"] if step["id"] == "apply_production_readiness_env"
    )
    production_env["command"] = production_env["command"].replace(
        PRODUCTION_CORS_ORIGINS,
        "https://<console-hostname>",
    ).replace(PRODUCTION_PUBLIC_BASE_URL, "https://<api-hostname>")
    production_env["expected_success"] = [
        "IMAGE_AGENT_ENV=production",
        "IMAGE_AGENT_CORS_ORIGINS=https://<console-hostname>",
        "IMAGE_AGENT_PUBLIC_BASE_URL=https://<api-hostname>",
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "apply_production_readiness_env command must be materialized without placeholders" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_rawchat_direct_bootstrap_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    production_env = next(
        step for step in request["required_followup_steps"] if step["id"] == "apply_production_readiness_env"
    )
    production_env["expected_success"] = [
        item for item in production_env["expected_success"] if item != "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "production readiness env expected_success must include IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_docker_command_verification(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    production_env = next(
        step for step in request["required_followup_steps"] if step["id"] == "apply_production_readiness_env"
    )
    production_env["command"] = production_env["command"].replace(" --verify-docker-command", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "production readiness env command must include --verify-docker-command" in str(exc.value)


def test_verify_stale_task_apply_request_requires_docker_host_policy_dry_run(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    request["required_followup_steps"] = [
        step for step in request["required_followup_steps"] if step["id"] != "verify_docker_host_policy_dry_run"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "required follow-up step ids mismatch" in str(exc.value)


def test_verify_stale_task_apply_request_requires_rawchat_direct_connectivity(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    request["required_followup_steps"] = [
        step for step in request["required_followup_steps"] if step["id"] != "verify_rawchat_direct_connectivity"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "required follow-up step ids mismatch" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_docker_host_policy_apply(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    docker_policy = next(
        step for step in request["required_followup_steps"] if step["id"] == "verify_docker_host_policy_dry_run"
    )
    docker_policy["command"] = docker_policy["command"] + " --apply"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "docker host policy dry-run command must not include --apply" in str(exc.value)


def test_stale_task_apply_expected_success_covers_release_gate_strict_evidence():
    builder = load_builder()
    verifier = load_verifier()
    smoke_required, verifier_required = _release_gate_required_strict_expected_success()

    assert smoke_required <= set(builder.STRICT_SMOKE_EXPECTED_SUCCESS)
    assert verifier_required <= set(builder.STRICT_SMOKE_VERIFIER_EXPECTED_SUCCESS)
    assert smoke_required <= set(verifier.STRICT_SMOKE_EXPECTED_SUCCESS)
    assert verifier_required <= set(verifier.STRICT_SMOKE_VERIFIER_EXPECTED_SUCCESS)


def test_stale_task_apply_elasticsearch_prereq_expected_success_covers_release_gate():
    builder = load_builder()
    verifier = load_verifier()
    required = _release_gate_required_elasticsearch_prereq_expected_success()

    assert required <= set(builder.ELASTICSEARCH_HYBRID_PREREQ_EXPECTED_SUCCESS)
    assert required <= set(verifier.ELASTICSEARCH_HYBRID_PREREQ_EXPECTED_SUCCESS)


def test_stale_task_apply_strict_smoke_command_covers_release_gate_flags(tmp_path):
    request = _request_payload(tmp_path)
    strict_smoke = next(
        step for step in request["required_followup_steps"] if step["id"] == "run_strict_remote_smoke_acceptance"
    )
    command = strict_smoke["command"]

    for required_flag in sorted(_release_gate_static_strict_smoke_flags()):
        assert required_flag in command


def test_verify_stale_task_apply_request_accepts_exact_freshness_boundary(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)

    report = verifier.verify_apply_request(
        request,
        expected_task_ids=[83, 84],
        max_age_hours=24,
        now_utc="2026-06-13T04:14:24.156875Z",
    )

    assert report["status"] == "passed"
    assert report["checked"]["expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"


def test_verify_stale_task_apply_request_rejects_after_freshness_boundary(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-13T04:14:25Z",
        )

    assert "verified approval generated_at_utc is older than max_age_hours" in str(exc.value)


def test_verify_stale_task_apply_request_requires_full_main_flow_strict_smoke(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace(" --require-agent-workflow-confirmation", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke command must include --require-agent-workflow-confirmation" in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["apply_step"].update(
                {"command": request["apply_step"]["command"].replace(f"{REMOTE_LIVE_ROOT_SNIPPET} ", "")}
            ),
            "apply_step command must include IMAGE_AGENT_ROOT=/home/yyf/project/image_agent",
        ),
        (
            lambda request: next(
                step
                for step in request["required_followup_steps"]
                if step["id"] == "collect_post_apply_clean_dry_run"
            ).update(
                {
                    "command": next(
                        step
                        for step in request["required_followup_steps"]
                        if step["id"] == "collect_post_apply_clean_dry_run"
                    )["command"].replace(f"{REMOTE_LIVE_ROOT_SNIPPET} ", "")
                }
            ),
            "post-apply dry-run must set IMAGE_AGENT_ROOT=/home/yyf/project/image_agent",
        ),
    ],
)
def test_verify_stale_task_apply_request_requires_live_root_for_stale_task_db_access(
    tmp_path,
    mutate,
    message,
):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    mutate(request)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert message in str(exc.value)


@pytest.mark.parametrize(
    "required_flag",
    [
        "--require-deployment-identity",
        "--require-agent-workflow-confirmation",
        "--require-agent-workflow-resume",
        "--require-agent-workflow-fingerprint-negative",
        "--require-unknown-workflow-incubation",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--require-production-readiness",
        "--require-runtime-toolchain",
        "--deployment-id",
        "--min-documents 60",
        "--min-chunks 200",
        "--require-raw-source-policy",
        "--require-vendor-pointer-integrity",
        "--require-elasticsearch-hybrid-rag",
        "--require-uploaded-series",
        "--upload-nifti-file",
        "--require-completed-task",
        "--require-task-events",
        "--require-observe-repair",
        "--require-launched-task",
        "--require-launchability-matrix",
        "--min-native-qc-images 1",
        "--min-scientific-report-images 1",
        "--project-id",
        "--upload-session-id",
    ],
)
def test_verify_stale_task_apply_request_requires_complete_readiness_smoke_flags(tmp_path, required_flag):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace(f" {required_flag}", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    if required_flag == "--upload-nifti-file":
        assert "strict smoke command must choose either --uploaded-series-id or --upload-nifti-file" in str(exc.value)
    elif required_flag in {"--deployment-id", "--project-id", "--upload-session-id"}:
        assert f"run_strict_remote_smoke_acceptance command must include {required_flag}" in str(exc.value)
    else:
        assert f"strict smoke command must include {required_flag}" in str(exc.value)


def test_verify_stale_task_apply_request_requires_elasticsearch_hybrid_prerequisite_step(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    request["required_followup_steps"] = [
        step for step in request["required_followup_steps"]
        if step["id"] != "verify_elasticsearch_hybrid_prerequisites"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "required follow-up step ids mismatch" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_status_only_elasticsearch_prereq_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "verify_elasticsearch_hybrid_prerequisites":
            step["expected_success"] = "status=passed"
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "ES hybrid prerequisite verifier expected_success must include detailed checked fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_es_runtime_probe_without_deployment_env(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "verify_elasticsearch_hybrid_prerequisites":
            step["command"] = step["command"].replace(
                "set -a; . /home/yyf/project/image_agent/.env; set +a; ",
                "",
            )
            step["command"] = step["command"].replace(
                "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env ",
                "",
            )
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "ES prerequisite runtime probe must load deployment env" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_strict_smoke_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step.pop("expected_success", None)
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_runtime_workflow_alias_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item
                for item in step["expected_success"]
                if item != "agent_workflow_resume.runtime_workflow_type matches launched_task.runtime_workflow_type"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_launch_source_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item for item in step["expected_success"] if item != "launched_task.launch_source=agent_workflow_resume"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_confirmation_runtime_alias_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item
                for item in step["expected_success"]
                if item
                != "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type matches launched_task.runtime_workflow_type"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_fingerprint_negative_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item for item in step["expected_success"] if item != "agent_workflow_fingerprint_negative_status=passed"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_unknown_workflow_incubation_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item for item in step["expected_success"] if item != "unknown_workflow_incubation.action_lane=toolchain_incubation"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_observe_repair_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item for item in step["expected_success"] if item != "observe_repair.policy=read_only_observe_repair"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_runtime_toolchain_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item for item in step["expected_success"] if item != "runtime_toolchain_status=passed"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_task_events_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item for item in step["expected_success"] if item != "task_events_remote_log_count>0"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_elasticsearch_hybrid_query_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [
                item
                for item in step["expected_success"]
                if item != "rag_elasticsearch_hybrid_query_embedding_transport matches status"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke expected_success must include strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_missing_elasticsearch_hybrid_verifier_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "verify_strict_remote_smoke_acceptance_json_after_normal_restart":
            step["expected_success"] = [
                item
                for item in step["expected_success"]
                if item != "checked.rag_elasticsearch_hybrid_query_embedding_transport matches status"
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke verifier expected_success must include checked strict acceptance evidence fields" in str(
        exc.value
    )


def test_verify_stale_task_apply_request_rejects_missing_strict_verifier_expected_success(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "verify_strict_remote_smoke_acceptance_json_after_normal_restart":
            step["expected_success"] = "status=passed"
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke verifier expected_success must include checked strict acceptance evidence fields" in str(exc.value)


def test_verify_stale_task_apply_request_rejects_operator_placeholder_commands(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace("codex-gate-verifiers-efca895b", "<accepted_release_or_commit>", 1)
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "run_strict_remote_smoke_acceptance command must be materialized without placeholders" in str(exc.value)


def test_verify_stale_task_apply_request_requires_strict_smoke_marked_mutating(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["mutates_remote_state"] = False
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "strict smoke step must be marked as mutating remote state" in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: next(
                step for step in request["required_followup_steps"] if step["id"] == "run_strict_remote_smoke_acceptance"
            ).update({"expected_output_json": "/tmp/other-smoke.json"}),
            "strict smoke expected_output_json must match --output-json",
        ),
        (
            lambda request: next(
                step
                for step in request["required_followup_steps"]
                if step["id"] == "verify_strict_remote_smoke_acceptance_json_after_normal_restart"
            ).update(
                {
                    "command": next(
                        step
                        for step in request["required_followup_steps"]
                        if step["id"] == "verify_strict_remote_smoke_acceptance_json_after_normal_restart"
                    )["command"].replace("/tmp/image_agent_remote_smoke_acceptance_20260612T050000Z.json", "/tmp/other-smoke.json")
                }
            ),
            "strict smoke verifier command must verify the smoke output JSON",
        ),
        (
            lambda request: next(
                step
                for step in request["required_followup_steps"]
                if step["id"] == "emit_fast_launch_acceptance_env_after_strict_verify"
            ).update(
                {
                    "command": next(
                        step
                        for step in request["required_followup_steps"]
                        if step["id"] == "emit_fast_launch_acceptance_env_after_strict_verify"
                    )["command"].replace("/tmp/image_agent_remote_smoke_acceptance_20260612T050000Z.json", "/tmp/other-smoke.json")
                }
            ),
            "fast-launch env apply command must verify the smoke output JSON",
        ),
    ],
)
def test_verify_stale_task_apply_request_requires_single_strict_smoke_json_path(tmp_path, mutate, message):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    mutate(request)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert message in str(exc.value)


def test_verify_stale_task_apply_request_requires_final_production_deployment_required_and_ready(tmp_path):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    for step in request["required_followup_steps"]:
        if step["id"] == "verify_final_fast_launch_readiness":
            step["expected_success"] = [
                item
                for item in step["expected_success"]
                if item
                not in {
                    "fast_launch_readiness.checks.production_deployment.required=true",
                    "fast_launch_readiness.checks.production_deployment.ready=true",
                }
            ]
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert "final fast-launch readiness expected_success mismatch" in str(exc.value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda request: request["apply_step"].update({"command": request["apply_step"]["command"] + " IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1"}),
            "must not use active-task restart override",
        ),
        (
            lambda request: request.update({"authorization_required": False}),
            "authorization_required must be true",
        ),
        (
            lambda request: request["required_followup_steps"].pop(3),
            "required follow-up step ids mismatch",
        ),
        (
            lambda request: request.update({"approval_expires_at_utc": "2026-06-13T04:14:25+00:00"}),
            "approval_expires_at_utc mismatch",
        ),
    ],
)
def test_verify_stale_task_apply_request_rejects_unsafe_request(tmp_path, mutate, message):
    verifier = load_verifier()
    request = _request_payload(tmp_path)
    mutate(request)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_apply_request(
            request,
            expected_task_ids=[83, 84],
            max_age_hours=24,
            now_utc="2026-06-12T05:30:00Z",
        )

    assert message in str(exc.value)


def test_verify_stale_task_apply_request_cli_prints_passed_report(tmp_path, capsys):
    verifier = load_verifier()
    request_path = tmp_path / "apply-request.json"
    request_path.write_text(json.dumps(_request_payload(tmp_path)), encoding="utf-8")

    verifier.main(
        [
            str(request_path),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-12T05:30:00Z",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["source_json"] == str(request_path)
    assert report["checked"]["expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
