from __future__ import annotations

import argparse
import ipaddress
import importlib.util
import json
import re
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path


REMOTE_OVERLAY_ROOT = "/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z"
REMOTE_API_DIR = f"{REMOTE_OVERLAY_ROOT}/apps/api"
REMOTE_SHARED_PYTHON = "/home/yyf/project/image_agent/apps/api/.venv/bin/python"
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
REMOTE_LIVE_ROOT_SNIPPET = "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent"
APPLY_REASON = "operator confirmed no matching running Image Agent container"
ELASTICSEARCH_HYBRID_PREREQ_EXPECTED_SUCCESS = [
    "status=passed",
    "elasticsearch_url_configured=true",
    "rag_embedding_provider_configured=true",
    "rag_embedding_provider_production_configured=true",
    "rag_embedding_model_configured=true",
    "rag_embedding_endpoint_configured=true",
    "secrets_redacted=true",
    "rag_status_engine=elasticsearch_hybrid",
    "rag_status_hybrid_engine=elasticsearch",
    "rag_status_hybrid_configured=true",
    "rag_status_hybrid_mode=connected",
    "rag_status_hybrid_persisted=true",
    "rag_status_hybrid_index privacy-safe",
    "rag_status_hybrid_index_matches_env=true",
    "rag_status_hybrid_indexed_chunk_count>0",
    "rag_status_hybrid_lexical_retriever=standard",
    "rag_status_hybrid_vector_retriever=knn",
    "rag_status_hybrid_dense_vector_field=embedding",
    "rag_status_hybrid_dense_vector_dims>0",
    "rag_status_hybrid_fusion=rrf",
    "rag_status_hybrid_official_rrf_source_present=true",
    "rag_status_hybrid_error_absent=true",
    "rag_status_hybrid_embedding_error_absent=true",
    "rag_status_hybrid_embedding_provider production configured",
    "rag_status_hybrid_embedding_provider_matches_env=true",
    "rag_status_hybrid_embedding_model present",
    "rag_status_hybrid_embedding_model_matches_env=true",
    "rag_status_hybrid_embedding_transport production-safe",
    "rag_status_hybrid_embedding_endpoint_configured=true",
    "rag_status_hybrid_embedding_production_ready=true",
    "runtime_probe_machine_binding=runtime_discovered",
    "runtime_probe_workflow_tool_execution=deployment_server_local",
    "runtime_probe_docker_runtime_host=api_server",
    "runtime_probe_docker_accessible=true",
    "runtime_probe_docker_requires_sudo=false",
    "runtime_probe_elasticsearch_discovery_status=available",
    "runtime_probe_elasticsearch_container_running=true",
    "runtime_probe_elasticsearch_candidate_endpoint loopback",
]
STRICT_SMOKE_EXPECTED_SUCCESS = [
    "model_status.trust_env_proxy=false",
    "model_status.deployment.model_gateway_access=direct",
    "launched_task.launch_source=agent_workflow_resume",
    "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type matches launched_task.runtime_workflow_type",
    "agent_workflow_confirmation.workflow_metadata.agent_selectable=true",
    "launched_task.runtime_workflow_type present",
    "agent_workflow_resume.runtime_workflow_type matches launched_task.runtime_workflow_type",
    "task_status.runtime_workflow_type matches launched_task.runtime_workflow_type",
    "task_result_summary.workflow_metadata.workflow_type matches task workflow_type",
    "task_result_summary.workflow_metadata.runtime_workflow_type matches task_status.runtime_workflow_type",
    "task_result_summary.workflow_metadata.agent_selectable=true",
    "task_result_summary.workflow_metadata.is_report_only=false",
    "project_workflow_eligibility_metadata_status=passed",
    "project_workflow_eligibility_metadata_workflow_types include task workflow_type",
    "project_workflow_eligibility_metadata_item_count>0",
    "upload_inventory_workflow_eligibility_metadata_status=passed",
    "upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
    "upload_inventory_workflow_eligibility_metadata_item_count>0",
    "agent_workflow_fingerprint_negative_status=passed",
    "agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch",
    "agent_workflow_fingerprint_negative.production_task_created=false",
    "agent_workflow_fingerprint_negative.task_created=false",
    "unknown_workflow_incubation_status=passed",
    "unknown_workflow_incubation.action_lane=toolchain_incubation",
    "unknown_workflow_incubation.task_created=false",
    "unknown_workflow_incubation.confirmation_created=false",
    "unknown_workflow_incubation.task_creation_allowed=false",
    "unknown_workflow_incubation.forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch",
    "unknown_workflow_incubation.production_task_created=false",
    "unknown_workflow_incubation.proposal_production_task_created=false",
    "runtime_toolchain_status=passed",
    "runtime_toolchain.workflow_tool_execution=deployment_server_local",
    "runtime_toolchain.docker_runtime_host=api_server",
    "runtime_toolchain.required_workflow_available=true",
    "task_events_status=passed",
    "task_events_event_types includes task.remote_log",
    "task_events_remote_log_count>0",
    "fast_launch_readiness.checks.production_deployment.status=passed",
    "fast_launch_readiness.checks.production_deployment.required=true",
    "fast_launch_readiness.checks.production_deployment.ready=true",
    "rag_elasticsearch_hybrid.embedding_transport production-safe",
    "rag_elasticsearch_hybrid.embedding_endpoint_configured boolean",
    "rag_elasticsearch_hybrid.official_rrf_source_present=true",
    "rag_rebuild_elasticsearch_hybrid.lexical_retriever matches status",
    "rag_rebuild_elasticsearch_hybrid.vector_retriever matches status",
    "rag_rebuild_elasticsearch_hybrid.dense_vector_field matches status",
    "rag_rebuild_elasticsearch_hybrid.fusion matches status",
    "rag_rebuild_elasticsearch_hybrid.embedding_transport matches status",
    "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured matches status",
    "rag_elasticsearch_hybrid_query_index matches status",
    "rag_elasticsearch_hybrid_query_lexical_retriever=standard",
    "rag_elasticsearch_hybrid_query_vector_retriever=knn",
    "rag_elasticsearch_hybrid_query_dense_vector_field=embedding",
    "rag_elasticsearch_hybrid_query_fusion=rrf",
    "rag_elasticsearch_hybrid_query_dense_vector_dims matches status",
    "rag_elasticsearch_hybrid_query_embedding_provider matches status",
    "rag_elasticsearch_hybrid_query_embedding_model matches status",
    "rag_elasticsearch_hybrid_query_embedding_transport matches status",
    "rag_elasticsearch_hybrid_query_embedding_endpoint_configured matches status",
    "rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true",
    "rag_elasticsearch_hybrid_query_embedding_production_ready matches status",
    "rag_elasticsearch_hybrid_query_embedding_production_ready=true",
    "observe_repair_status=passed",
    "observe_repair.policy=read_only_observe_repair",
    "observe_repair.auto_rerun_allowed=false",
    "observe_repair.task_creation_allowed=false",
    "observe_repair.forbidden_actions include auto_retry,auto_rerun,task_creation",
    "observe_repair.production_task_created=false",
    "observe_repair.requires_preflight_before_retry=true",
    "observe_repair.requires_human_confirmation_before_retry=true",
]
STRICT_SMOKE_VERIFIER_EXPECTED_SUCCESS = [
    "checked.model_trust_env_proxy=false",
    "checked.model_gateway_access=direct",
    "checked.launched_task_launch_source=agent_workflow_resume",
    "checked.agent_workflow_confirmation_metadata_runtime_workflow_type matches launched_task_runtime_workflow_type",
    "checked.agent_workflow_confirmation_metadata_agent_selectable=true",
    "checked.task_result_summary_metadata_workflow_type matches task workflow_type",
    "checked.task_result_summary_metadata_runtime_workflow_type matches task_status_runtime_workflow_type",
    "checked.task_result_summary_metadata_agent_selectable=true",
    "checked.task_result_summary_metadata_is_report_only=false",
    "checked.project_workflow_eligibility_metadata_status=passed",
    "checked.project_workflow_eligibility_metadata_workflow_types include task workflow_type",
    "checked.project_workflow_eligibility_metadata_task_workflow_type_included=true",
    "checked.project_workflow_eligibility_metadata_item_count>0",
    "checked.upload_inventory_workflow_eligibility_metadata_status=passed",
    "checked.upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
    "checked.upload_inventory_workflow_eligibility_metadata_task_workflow_type_included=true",
    "checked.upload_inventory_workflow_eligibility_metadata_item_count>0",
    "checked.launched_task_runtime_workflow_type present",
    "checked.agent_workflow_resume_runtime_workflow_type matches launched_task_runtime_workflow_type",
    "checked.task_status_runtime_workflow_type matches launched_task_runtime_workflow_type",
    "checked.agent_workflow_fingerprint_negative_status=passed",
    "checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch",
    "checked.agent_workflow_fingerprint_negative_production_task_created=false",
    "checked.agent_workflow_fingerprint_negative_task_created=false",
    "checked.unknown_workflow_incubation_status=passed",
    "checked.unknown_workflow_incubation_action_lane=toolchain_incubation",
    "checked.unknown_workflow_incubation_task_created=false",
    "checked.unknown_workflow_incubation_confirmation_created=false",
    "checked.unknown_workflow_incubation_task_creation_allowed=false",
    "checked.unknown_workflow_incubation_forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch",
    "checked.unknown_workflow_incubation_production_task_created=false",
    "checked.unknown_workflow_incubation_proposal_production_task_created=false",
    "checked.runtime_toolchain_status=passed",
    "checked.runtime_toolchain_workflow_tool_execution=deployment_server_local",
    "checked.runtime_toolchain_docker_runtime_host=api_server",
    "checked.runtime_toolchain_required_workflow_available=true",
    "checked.task_events_status=passed",
    "checked.task_events_remote_log_count>0",
    "checked.fast_launch_production_deployment_status=passed",
    "checked.fast_launch_production_deployment_required=true",
    "checked.fast_launch_production_deployment_ready=true",
    "checked.rag_elasticsearch_hybrid_embedding_transport production-safe",
    "checked.rag_elasticsearch_hybrid_embedding_endpoint_configured boolean",
    "checked.rag_elasticsearch_hybrid_official_rrf_source_present=true",
    "checked.rag_rebuild_elasticsearch_hybrid_lexical_retriever matches status",
    "checked.rag_rebuild_elasticsearch_hybrid_vector_retriever matches status",
    "checked.rag_rebuild_elasticsearch_hybrid_dense_vector_field matches status",
    "checked.rag_rebuild_elasticsearch_hybrid_fusion matches status",
    "checked.rag_rebuild_elasticsearch_hybrid_embedding_transport matches status",
    "checked.rag_rebuild_elasticsearch_hybrid_embedding_endpoint_configured matches status",
    "checked.rag_elasticsearch_hybrid_query_index matches status",
    "checked.rag_elasticsearch_hybrid_query_lexical_retriever=standard",
    "checked.rag_elasticsearch_hybrid_query_vector_retriever=knn",
    "checked.rag_elasticsearch_hybrid_query_dense_vector_field=embedding",
    "checked.rag_elasticsearch_hybrid_query_fusion=rrf",
    "checked.rag_elasticsearch_hybrid_query_dense_vector_dims matches status",
    "checked.rag_elasticsearch_hybrid_query_embedding_provider matches status",
    "checked.rag_elasticsearch_hybrid_query_embedding_model matches status",
    "checked.rag_elasticsearch_hybrid_query_embedding_transport matches status",
    "checked.rag_elasticsearch_hybrid_query_embedding_endpoint_configured matches status",
    "checked.rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true",
    "checked.rag_elasticsearch_hybrid_query_embedding_production_ready matches status",
    "checked.rag_elasticsearch_hybrid_query_embedding_production_ready=true",
    "checked.observe_repair_status=passed",
    "checked.observe_repair_policy=read_only_observe_repair",
    "checked.observe_repair_auto_rerun_allowed=false",
    "checked.observe_repair_task_creation_allowed=false",
    "checked.observe_repair_forbidden_actions include auto_retry,auto_rerun,task_creation",
    "checked.observe_repair_production_task_created=false",
    "checked.observe_repair_requires_preflight_before_retry=true",
    "checked.observe_repair_requires_human_confirmation_before_retry=true",
]


def _load_approval_verifier():
    script = Path(__file__).resolve().with_name("verify_stale_task_approval.py")
    spec = importlib.util.spec_from_file_location("verify_stale_task_approval", script)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("could not load verify_stale_task_approval.py")
    spec.loader.exec_module(module)
    return module


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemExit("now_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp_for_paths(value: str | None) -> str:
    if value:
        return value
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _task_flags(task_ids: Sequence[int]) -> str:
    return " ".join(f"--task-id {int(task_id)}" for task_id in task_ids)


def _required_text(value: str | None, *, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{key} is required")
    return value.strip()


def _required_privacy_safe_release_symbol(value: str | None, *, key: str) -> str:
    text = _required_text(value, key=key)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,80}", text):
        raise SystemExit(f"{key} must be a privacy-safe release symbol")
    return text


def _required_remote_nifti_file(value: str | None) -> str:
    text = _required_text(value, key="remote_nifti_file").replace("\\", "/")
    if not (text.startswith("/") and (text.endswith(".nii") or text.endswith(".nii.gz"))):
        raise SystemExit("remote_nifti_file must be a remote .nii or .nii.gz path")
    return text


def _required_workflow_type(value: str | None) -> str:
    text = _required_text(value, key="workflow_type")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,80}", text) or text.endswith("_mock"):
        raise SystemExit("workflow_type must be a concrete registered workflow type")
    return text


def _required_production_https_origin(value: str | None, *, key: str) -> str:
    text = _required_text(value, key=key)
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", text):
        raise SystemExit(f"{key} must be a public HTTPS origin")
    host = text.removeprefix("https://").split(":", 1)[0].lower()
    if not _is_public_deployment_host(host):
        raise SystemExit(f"{key} must be a public HTTPS origin")
    return text


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _required_positive_int(value: int | None, *, key: str) -> int:
    if isinstance(value, bool) or value is None or int(value) <= 0:
        raise SystemExit(f"{key} must be a positive integer")
    return int(value)


def _strict_smoke_upload_source(*, remote_nifti_file: str | None, uploaded_series_id: int | None) -> str:
    if uploaded_series_id is not None:
        uploaded_series_id_value = _required_positive_int(uploaded_series_id, key="uploaded_series_id")
        return f"--uploaded-series-id {uploaded_series_id_value}"
    return f"--upload-nifti-file {_required_remote_nifti_file(remote_nifti_file)}"


def _api_command(command: str, *, load_env: bool = False, live_root: bool = False) -> str:
    env = f"{REMOTE_ENV_LOAD_SNIPPET} " if load_env else ""
    root = f"{REMOTE_LIVE_ROOT_SNIPPET} " if live_root else ""
    return f"cd {REMOTE_API_DIR} && {env}{root}PYTHONPATH=. {REMOTE_SHARED_PYTHON} {command}"


def build_apply_request(
    *,
    approval_json: Path,
    expected_task_ids: Sequence[int],
    max_age_hours: float,
    now_utc: str | None = None,
    output_timestamp: str | None = None,
    deployment_id: str | None = None,
    expected_health_version: str | None = None,
    remote_nifti_file: str | None = None,
    uploaded_series_id: int | None = None,
    workflow_type: str | None = None,
    project_id: int | None = None,
    upload_session_id: int | None = None,
    production_cors_origins: str | None = None,
    production_public_base_url: str | None = None,
) -> dict:
    verifier = _load_approval_verifier()
    payload = json.loads(approval_json.read_text(encoding="utf-8"))
    now = _parse_utc_timestamp(now_utc)
    verified = verifier.verify_approval_payload(
        payload,
        expected_task_ids=expected_task_ids,
        now=now,
        max_age_hours=max_age_hours,
    )
    task_ids = verified["checked"]["target_task_ids"]
    task_flags = _task_flags(task_ids)
    approval_generated_at = _parse_utc_timestamp(verified["checked"]["generated_at_utc"])
    if approval_generated_at is None:
        raise SystemExit("verified approval generated_at_utc is required")
    approval_expires_at = approval_generated_at + timedelta(hours=max_age_hours)
    stamp = _timestamp_for_paths(output_timestamp)
    apply_json = f"/tmp/image_agent_stale_tasks_83_84_apply_{stamp}.json"
    resolution_json = f"/tmp/image_agent_stale_tasks_83_84_resolved_dry_run_{stamp}.json"
    docker_policy_json = f"/tmp/image_agent_docker_access_policy_dry_run_{stamp}.json"
    rawchat_direct_json = f"/tmp/image_agent_rawchat_direct_connectivity_{stamp}.json"
    strict_smoke_json = f"/tmp/image_agent_remote_smoke_acceptance_{stamp}.json"
    approval_json_text = str(approval_json)
    deployment_id_text = _required_privacy_safe_release_symbol(deployment_id, key="deployment_id")
    expected_health_version_text = _required_privacy_safe_release_symbol(
        expected_health_version,
        key="expected_health_version",
    )
    upload_source_flag = _strict_smoke_upload_source(
        remote_nifti_file=remote_nifti_file,
        uploaded_series_id=uploaded_series_id,
    )
    workflow_type_text = _required_workflow_type(workflow_type)
    project_id_value = _required_positive_int(project_id, key="project_id")
    upload_session_id_value = _required_positive_int(upload_session_id, key="upload_session_id")
    production_cors_origins_text = _required_production_https_origin(
        production_cors_origins,
        key="production_cors_origins",
    )
    production_public_base_url_text = _required_production_https_origin(
        production_public_base_url,
        key="production_public_base_url",
    )

    apply_command = _api_command(
        (
            f"scripts/reconcile_stale_tasks.py --apply --max-age-hours {max_age_hours:g} "
            f"{task_flags} --approval-json {approval_json_text} "
            f"--reason \"{APPLY_REASON}\" > {apply_json}"
        ),
        load_env=True,
        live_root=True,
    )
    post_apply_dry_run = _api_command(
        (
            f"scripts/reconcile_stale_tasks.py --max-age-hours {max_age_hours:g} "
            f"--check-containers {task_flags} > {resolution_json}"
        ),
        load_env=True,
        live_root=True,
    )
    verify_resolution = _api_command(
        (
            f"scripts/verify_stale_task_resolution.py --apply-json {apply_json} "
            f"--resolution-json {resolution_json} {task_flags} "
            f"--require-empty-active --max-age-hours {max_age_hours:g}"
        )
    )
    docker_host_policy_dry_run = (
        f"cd {REMOTE_OVERLAY_ROOT} && {REMOTE_SHARED_PYTHON} scripts/configure_docker_access.py "
        f"--user yyf --docker-bin /usr/bin/docker --output-json {docker_policy_json} && "
        f"{REMOTE_SHARED_PYTHON} -c 'import json; p=\"{docker_policy_json}\"; "
        "d=json.load(open(p, encoding=\"utf-8\")); "
        "assert d[\"plan_id\"] == \"image_agent_docker_access_policy_v1\"; "
        "assert d[\"mode\"] == \"dry_run\"; "
        "assert d[\"sudoers_file\"] == \"/etc/sudoers.d/image-agent-docker\"; "
        "assert d[\"verification_command\"][:4] == [\"sudo\", \"-n\", \"docker\", \"version\"]; "
        "print(\"plan_id=image_agent_docker_access_policy_v1\"); "
        "print(\"mode=dry_run\"); "
        "print(\"sudoers_file=/etc/sudoers.d/image-agent-docker\"); "
        "print(\"verification_command=sudo -n docker version\")'"
    )
    rawchat_direct_connectivity = (
        f"cd {REMOTE_OVERLAY_ROOT} && {REMOTE_SHARED_PYTHON} scripts/verify_rawchat_direct_connectivity.py "
        f"--url https://rawchat.cn/codex --output-json {rawchat_direct_json}"
    )
    production_env_apply = (
        f"cd {REMOTE_OVERLAY_ROOT} && {REMOTE_SHARED_PYTHON} scripts/bootstrap_image_agent.py "
        f"--repo-root {REMOTE_OVERLAY_ROOT} "
        "--image-agent-root /home/yyf/project/image_agent "
        "--env-file /home/yyf/project/image_agent/.env "
        f"--production --production-cors-origins {production_cors_origins_text} "
        f"--production-public-base-url {production_public_base_url_text} "
        "--model-provider rawchat --model-name gpt-5.5 --model-review-name gpt-5.5 "
        "--model-base-url https://rawchat.cn/codex --model-wire-api responses "
        '--docker-command "sudo -n docker" --verify-docker-command '
        "--skip-elasticsearch-hybrid --skip-workflow-images --config-only --apply"
    )
    restart_preflight = (
        f"cd {REMOTE_OVERLAY_ROOT} && "
        "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
        f"IMAGE_AGENT_RELEASE_ROOT={REMOTE_OVERLAY_ROOT} "
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env "
        "IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin "
        "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1 "
        "bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env"
    )
    restart_normal = (
        f"cd {REMOTE_OVERLAY_ROOT} && "
        "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
        f"IMAGE_AGENT_RELEASE_ROOT={REMOTE_OVERLAY_ROOT} "
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env "
        "IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin "
        "bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env"
    )
    runtime_probe_json = f"/tmp/image_agent_runtime_probe_{REMOTE_OVERLAY_ROOT.rsplit('/', 1)[-1]}.json"
    es_prereq = (
        f"cd {REMOTE_API_DIR} && "
        f"{REMOTE_ENV_LOAD_SNIPPET} "
        "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env "
        f"PYTHONPATH=. {REMOTE_SHARED_PYTHON} -m app.scripts.probe_runtime_environment --json > {runtime_probe_json} && "
        f"PYTHONPATH=. {REMOTE_SHARED_PYTHON} scripts/verify_elasticsearch_hybrid_prerequisites.py "
        "--env-file /home/yyf/project/image_agent/.env "
        "--rag-status-url http://127.0.0.1:8000/agent/rag/status "
        f"--runtime-probe-json {runtime_probe_json}"
    )
    strict_smoke = _api_command(
        (
            "scripts/smoke_remote_agent.py --api-base http://127.0.0.1:8000 "
            "--require-model --expected-model-wire-api responses "
            "--expected-model-provider-profile rawchat --require-model-tool-loop "
            "--require-project-agent-context --require-agent-workflow-confirmation "
            "--require-agent-workflow-resume --require-agent-workflow-fingerprint-negative "
            "--require-unknown-workflow-incubation "
            "--require-deployment-identity --require-production-readiness "
            "--require-runtime-toolchain "
            f"--deployment-id {deployment_id_text} "
            f"--expected-health-version {expected_health_version_text} "
            "--min-documents 60 --min-chunks 200 --require-raw-source-policy "
            "--require-vendor-pointer-integrity --require-elasticsearch-hybrid-rag "
            "--require-real-evidence-ids "
            "--require-completed-upload --require-uploaded-series "
            f"{upload_source_flag} "
            "--require-completed-task --require-task-events --require-observe-repair --require-launched-task "
            f"--launch-workflow-type {workflow_type_text} "
            "--wait-task-completion-timeout-seconds 21600 --wait-task-completion-poll-seconds 30 "
            "--require-launchability-matrix --require-container-native-qc --min-native-qc-images 1 "
            "--require-scientific-report-artifacts --min-scientific-report-images 1 "
            f"--project-id {project_id_value} --upload-session-id {upload_session_id_value} "
            f"--output-json {strict_smoke_json}"
        )
    )
    strict_smoke_verify = _api_command(
        f"scripts/verify_remote_smoke_acceptance.py {strict_smoke_json} --max-age-hours {max_age_hours:g}"
    )
    strict_smoke_env_export = (
        f"cd {REMOTE_OVERLAY_ROOT} && {REMOTE_SHARED_PYTHON} scripts/bootstrap_image_agent.py "
        f"--repo-root {REMOTE_OVERLAY_ROOT} "
        "--image-agent-root /home/yyf/project/image_agent "
        "--env-file /home/yyf/project/image_agent/.env "
        "--skip-elasticsearch-hybrid --skip-workflow-images --config-only "
        f"--strict-acceptance-json {strict_smoke_json} "
        f"--strict-acceptance-max-age-hours {max_age_hours:g} --apply"
    )
    restart_after_fast_launch_env = (
        f"cd {REMOTE_OVERLAY_ROOT} && "
        "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
        f"IMAGE_AGENT_RELEASE_ROOT={REMOTE_OVERLAY_ROOT} "
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env "
        "IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin "
        "bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env"
    )
    verify_final_fast_launch = (
        f"cd {REMOTE_OVERLAY_ROOT} && {REMOTE_SHARED_PYTHON} -c "
        "'import json, urllib.request; "
        "d=json.loads(urllib.request.urlopen(\"http://127.0.0.1:8000/deployment\", timeout=30).read().decode()); "
        "r=d.get(\"fast_launch_readiness\", {}); "
        "checks=r.get(\"checks\") or {}; "
        "c=checks.get(\"strict_remote_acceptance\", {}); "
        "p=checks.get(\"production_deployment\", {}); "
        "assert r.get(\"ready\") is True and r.get(\"status\") == \"ready\"; "
        "assert c.get(\"status\") == \"passed\"; "
        "assert p.get(\"status\") == \"passed\"; "
        "assert p.get(\"required\") is True; "
        "assert p.get(\"ready\") is True; "
        "print(\"fast_launch_readiness.status=ready\"); "
        "print(\"fast_launch_readiness.checks.strict_remote_acceptance.status=passed\"); "
        "print(\"fast_launch_readiness.checks.production_deployment.status=passed\"); "
        "print(\"fast_launch_readiness.checks.production_deployment.required=true\"); "
        "print(\"fast_launch_readiness.checks.production_deployment.ready=true\")'"
    )

    return {
        "status": "operator_authorization_required",
        "request_type": "stale_task_apply_approval",
        "authorization_required": True,
        "must_not_run_until": "operator explicitly approves stale-task apply",
        "approval_json": approval_json_text,
        "approval_fingerprint": verified["checked"]["approval_fingerprint"],
        "approval_expires_at_utc": approval_expires_at.isoformat(),
        "target_task_ids": task_ids,
        "verified_approval": verified,
        "apply_step": {
            "id": "apply_approved_stale_task_resolution",
            "requires_operator_authorization": True,
            "mutates_remote_state": True,
            "command": apply_command,
            "expected_output_json": apply_json,
        },
        "required_followup_steps": [
            {
                "id": "collect_post_apply_clean_dry_run",
                "mutates_remote_state": False,
                "command": post_apply_dry_run,
                "expected_output_json": resolution_json,
            },
            {
                "id": "verify_post_apply_clean_resolution",
                "mutates_remote_state": False,
                "command": verify_resolution,
                "expected_success": "status=passed",
            },
            {
                "id": "verify_docker_host_policy_dry_run",
                "mutates_remote_state": False,
                "requires_operator_authorization": False,
                "command": docker_host_policy_dry_run,
                "expected_success": [
                    "plan_id=image_agent_docker_access_policy_v1",
                    "mode=dry_run",
                    "sudoers_file=/etc/sudoers.d/image-agent-docker",
                    "verification_command=sudo -n docker version",
                ],
            },
            {
                "id": "verify_rawchat_direct_connectivity",
                "mutates_remote_state": False,
                "requires_operator_authorization": False,
                "command": rawchat_direct_connectivity,
                "expected_success": [
                    "rawchat_direct_connectivity_status=passed",
                    "rawchat_direct_proxy_env_trusted=false",
                    "rawchat_direct_transport=direct",
                ],
            },
            {
                "id": "apply_production_readiness_env",
                "mutates_remote_state": True,
                "requires_operator_authorization": True,
                "command": production_env_apply,
                "expected_success": [
                    "IMAGE_AGENT_ENV=production",
                    f"IMAGE_AGENT_CORS_ORIGINS={production_cors_origins_text}",
                    f"IMAGE_AGENT_PUBLIC_BASE_URL={production_public_base_url_text}",
                    "IMAGE_AGENT_MODEL_PROVIDER=rawchat",
                    "IMAGE_AGENT_MODEL_NAME=gpt-5.5",
                    "IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5",
                    "IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex",
                    "IMAGE_AGENT_MODEL_WIRE_API=responses",
                    "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0",
                    "IMAGE_AGENT_DOCKER_COMMAND=sudo -n docker",
                    "verify_docker_command completed",
                ],
            },
            {
                "id": "restart_api_preflight_only",
                "mutates_remote_state": False,
                "command": restart_preflight,
                "expected_success": "restart_preflight:ok",
            },
            {
                "id": "restart_api_normally",
                "mutates_remote_state": True,
                "command": restart_normal,
                "expected_success": "health.app=image_agent",
            },
            {
                "id": "verify_elasticsearch_hybrid_prerequisites",
                "mutates_remote_state": False,
                "command": es_prereq,
                "expected_success": ELASTICSEARCH_HYBRID_PREREQ_EXPECTED_SUCCESS,
            },
            {
                "id": "run_strict_remote_smoke_acceptance",
                "mutates_remote_state": True,
                "command": strict_smoke,
                "expected_output_json": strict_smoke_json,
                "expected_success": STRICT_SMOKE_EXPECTED_SUCCESS,
            },
            {
                "id": "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
                "mutates_remote_state": False,
                "command": strict_smoke_verify,
                "expected_success": ["status=passed", *STRICT_SMOKE_VERIFIER_EXPECTED_SUCCESS],
            },
            {
                "id": "emit_fast_launch_acceptance_env_after_strict_verify",
                "mutates_remote_state": True,
                "command": strict_smoke_env_export,
                    "expected_success": [
                        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS=passed",
                    f"IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID={deployment_id_text}",
                ],
            },
            {
                "id": "restart_api_after_fast_launch_acceptance_env",
                "mutates_remote_state": True,
                "requires_operator_authorization": True,
                "command": restart_after_fast_launch_env,
                "expected_success": ["health.app=image_agent"],
            },
            {
                "id": "verify_final_fast_launch_readiness",
                "mutates_remote_state": False,
                "requires_operator_authorization": False,
                "command": verify_final_fast_launch,
                "expected_success": [
                    "fast_launch_readiness.status=ready",
                    "fast_launch_readiness.checks.strict_remote_acceptance.status=passed",
                    "fast_launch_readiness.checks.production_deployment.status=passed",
                    "fast_launch_readiness.checks.production_deployment.required=true",
                    "fast_launch_readiness.checks.production_deployment.ready=true",
                ],
            },
        ],
        "safety_invariants": [
            "do_not_run_without_explicit_operator_authorization",
            "do_not_use_IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
            "do_not_count_skipped_missing_model_config_as_passed",
            "do_not_store_or_print_api_keys_or_secrets",
        ],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a reviewed stale-task apply approval request JSON.")
    parser.add_argument("approval_json", help="Path to verified stale-task approval dry-run JSON.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids", required=True)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--now-utc", default=None, help="Testing hook: ISO-8601 UTC timestamp used as current time.")
    parser.add_argument("--output-timestamp", default=None, help="Timestamp suffix for generated /tmp output paths.")
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--expected-health-version", required=True)
    parser.add_argument("--remote-nifti-file", default=None)
    parser.add_argument("--uploaded-series-id", type=int, default=None)
    parser.add_argument("--workflow-type", required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--upload-session-id", type=int, required=True)
    parser.add_argument("--production-cors-origins", required=True)
    parser.add_argument("--production-public-base-url", required=True)
    parser.add_argument("--output-json", default=None, help="Optional path to save the approval request JSON.")
    args = parser.parse_args(argv)

    request = build_apply_request(
        approval_json=Path(args.approval_json),
        expected_task_ids=args.task_ids,
        max_age_hours=args.max_age_hours,
        now_utc=args.now_utc,
        output_timestamp=args.output_timestamp,
        deployment_id=args.deployment_id,
        expected_health_version=args.expected_health_version,
        remote_nifti_file=args.remote_nifti_file,
        uploaded_series_id=args.uploaded_series_id,
        workflow_type=args.workflow_type,
        project_id=args.project_id,
        upload_session_id=args.upload_session_id,
        production_cors_origins=args.production_cors_origins,
        production_public_base_url=args.production_public_base_url,
    )
    if args.output_json:
        request["output_json"] = str(Path(args.output_json))
        Path(args.output_json).write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(request, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
