from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path


EXPECTED_FOLLOWUP_STEP_IDS = [
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
REMOTE_ENV_LOAD_SNIPPET = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
REMOTE_LIVE_ROOT_SNIPPET = "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent"
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")
PLACEHOLDER_RE = re.compile(r"<[^>\s]+>")
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
    "status=passed",
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _parse_utc_timestamp(value: object, *, key: str) -> datetime:
    _require(isinstance(value, str) and value, f"{key} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, f"{key} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _verify_freshness(generated_at: str, *, max_age_hours: float, now_utc: datetime | None) -> datetime:
    _require(max_age_hours >= 0, "max_age_hours must be non-negative")
    parsed = _parse_utc_timestamp(generated_at, key="verified_approval.checked.generated_at_utc")
    now = now_utc or datetime.now(timezone.utc)
    _require(now.tzinfo is not None and now.utcoffset() is not None, "now_utc must be timezone-aware")
    age_hours = (now.astimezone(timezone.utc) - parsed).total_seconds() / 3600
    _require(age_hours >= 0, "verified approval generated_at_utc must not be in the future")
    _require(age_hours <= max_age_hours, "verified approval generated_at_utc is older than max_age_hours")
    return parsed


def _task_flags(task_ids: Sequence[int]) -> str:
    return " ".join(f"--task-id {int(task_id)}" for task_id in task_ids)


def _assert_safe_command(command: object, *, key: str) -> str:
    _require(isinstance(command, str) and command.strip(), f"{key} command must be non-empty")
    _require(
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command,
        f"{key} command must not use active-task restart override",
    )
    _require("OPENAI_API_KEY" not in command, f"{key} command must not mention OPENAI_API_KEY")
    _require(API_KEY_SHAPED_RE.search(command) is None, f"{key} command must not contain API-key shaped strings")
    _require(PLACEHOLDER_RE.search(command) is None, f"{key} command must be materialized without placeholders")
    return command


def _step_by_id(steps: list[dict], step_id: str) -> dict:
    for step in steps:
        if step.get("id") == step_id:
            return step
    raise SystemExit(f"missing follow-up step {step_id}")


def _token_after(command: str, token: str, *, key: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise SystemExit(f"{key} command could not be parsed") from exc
    try:
        index = parts.index(token)
    except ValueError as exc:
        raise SystemExit(f"{key} command must include {token}") from exc
    _require(index + 1 < len(parts) and parts[index + 1], f"{key} command must include a value after {token}")
    return parts[index + 1]


def _is_positive_int_text(value: str) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _command_parts(command: str, *, key: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise SystemExit(f"{key} command could not be parsed") from exc


def _command_has_token(command: str, token: str, *, key: str) -> bool:
    return token in _command_parts(command, key=key)


def _is_privacy_safe_release_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,80}", value or ""))


def _is_remote_nifti_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return normalized.startswith("/") and (normalized.endswith(".nii") or normalized.endswith(".nii.gz"))


def _is_workflow_type_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,80}", value or "")) and not value.endswith("_mock")


def _is_public_https_origin(value: str) -> bool:
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?", value or ""):
        return False
    host = value.removeprefix("https://").split(":", 1)[0].lower()
    return _is_public_deployment_host(host)


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def verify_apply_request(
    request: dict,
    *,
    expected_task_ids: Sequence[int] | None = None,
    max_age_hours: float = 24.0,
    now_utc: str | datetime | None = None,
) -> dict:
    _require(isinstance(request, dict), "apply request must be a JSON object")
    _require(request.get("status") == "operator_authorization_required", "status must be operator_authorization_required")
    _require(request.get("request_type") == "stale_task_apply_approval", "request_type must be stale_task_apply_approval")
    _require(request.get("authorization_required") is True, "authorization_required must be true")
    _require(
        request.get("must_not_run_until") == "operator explicitly approves stale-task apply",
        "must_not_run_until must require explicit operator approval",
    )
    target_task_ids = request.get("target_task_ids")
    _require(isinstance(target_task_ids, list) and target_task_ids, "target_task_ids must be non-empty")
    _require(all(isinstance(item, int) and not isinstance(item, bool) for item in target_task_ids), "target_task_ids entries must be integers")
    if expected_task_ids is not None:
        _require(sorted(target_task_ids) == sorted(int(item) for item in expected_task_ids), "target_task_ids must match expected task ids")
    task_flags = _task_flags(target_task_ids)

    verified = request.get("verified_approval")
    _require(isinstance(verified, dict), "verified_approval must be present")
    _require(verified.get("status") == "passed", "verified_approval.status must be passed")
    checked = verified.get("checked")
    _require(isinstance(checked, dict), "verified_approval.checked must be present")
    _require(checked.get("target_task_ids") == target_task_ids, "verified approval target_task_ids mismatch")
    approval_fingerprint = request.get("approval_fingerprint")
    _require(isinstance(approval_fingerprint, str) and len(approval_fingerprint) == 64, "approval_fingerprint must be SHA-256 hex")
    _require(checked.get("approval_fingerprint") == approval_fingerprint, "approval_fingerprint mismatch")
    now = _parse_utc_timestamp(now_utc, key="now_utc") if isinstance(now_utc, str) else now_utc
    generated_at_utc = _verify_freshness(
        checked.get("generated_at_utc"),
        max_age_hours=max_age_hours,
        now_utc=now,
    )
    expires_at_utc = generated_at_utc + timedelta(hours=max_age_hours)
    _require(
        request.get("approval_expires_at_utc") == expires_at_utc.isoformat(),
        "approval_expires_at_utc mismatch",
    )

    apply_step = request.get("apply_step")
    _require(isinstance(apply_step, dict), "apply_step must be present")
    _require(apply_step.get("id") == "apply_approved_stale_task_resolution", "apply_step.id mismatch")
    _require(apply_step.get("requires_operator_authorization") is True, "apply_step must require operator authorization")
    _require(apply_step.get("mutates_remote_state") is True, "apply_step must mutate remote state")
    apply_command = _assert_safe_command(apply_step.get("command"), key="apply_step")
    for required in (
        REMOTE_ENV_LOAD_SNIPPET,
        REMOTE_LIVE_ROOT_SNIPPET,
        "reconcile_stale_tasks.py --apply",
        f"--max-age-hours {max_age_hours:g}",
        task_flags,
        f"--approval-json {request.get('approval_json')}",
        '--reason "operator confirmed no matching running Image Agent container"',
    ):
        _require(required in apply_command, f"apply_step command must include {required}")

    steps = request.get("required_followup_steps")
    _require(isinstance(steps, list), "required_followup_steps must be a list")
    _require(all(isinstance(step, dict) for step in steps), "required_followup_steps entries must be objects")
    step_ids = [step.get("id") for step in steps]
    _require(step_ids == EXPECTED_FOLLOWUP_STEP_IDS, "required follow-up step ids mismatch")
    commands = {step["id"]: _assert_safe_command(step.get("command"), key=step["id"]) for step in steps}

    _require("reconcile_stale_tasks.py --max-age-hours 24 --check-containers" in commands["collect_post_apply_clean_dry_run"], "post-apply dry-run command mismatch")
    _require(REMOTE_ENV_LOAD_SNIPPET in commands["collect_post_apply_clean_dry_run"], "post-apply dry-run must load remote env")
    _require(
        REMOTE_LIVE_ROOT_SNIPPET in commands["collect_post_apply_clean_dry_run"],
        "post-apply dry-run must set IMAGE_AGENT_ROOT=/home/yyf/project/image_agent",
    )
    _require("verify_stale_task_resolution.py" in commands["verify_post_apply_clean_resolution"], "resolution verifier command missing")
    _require("--require-empty-active --max-age-hours 24" in commands["verify_post_apply_clean_resolution"], "resolution verifier must require empty active and freshness")
    docker_policy_command = commands["verify_docker_host_policy_dry_run"]
    for required in (
        "scripts/configure_docker_access.py",
        "--user yyf",
        "--docker-bin /usr/bin/docker",
        "--output-json /tmp/image_agent_docker_access_policy_dry_run_",
        "plan_id=image_agent_docker_access_policy_v1",
        "mode=dry_run",
        "sudoers_file=/etc/sudoers.d/image-agent-docker",
        "verification_command=sudo -n docker version",
    ):
        _require(required in docker_policy_command, f"docker host policy dry-run command must include {required}")
    _require(
        "--apply" not in _command_parts(docker_policy_command, key="verify_docker_host_policy_dry_run"),
        "docker host policy dry-run command must not include --apply",
    )
    docker_policy_step = _step_by_id(steps, "verify_docker_host_policy_dry_run")
    _require(
        docker_policy_step.get("mutates_remote_state") is False,
        "docker host policy dry-run step must be read-only",
    )
    _require(
        docker_policy_step.get("requires_operator_authorization") is False,
        "docker host policy dry-run step must not require operator apply authorization",
    )
    docker_policy_expected = docker_policy_step.get("expected_success")
    _require(
        isinstance(docker_policy_expected, list)
        and "plan_id=image_agent_docker_access_policy_v1" in docker_policy_expected
        and "mode=dry_run" in docker_policy_expected
        and "sudoers_file=/etc/sudoers.d/image-agent-docker" in docker_policy_expected
        and "verification_command=sudo -n docker version" in docker_policy_expected,
        "docker host policy dry-run expected_success mismatch",
    )
    rawchat_direct_command = commands["verify_rawchat_direct_connectivity"]
    for required in (
        "scripts/verify_rawchat_direct_connectivity.py",
        "--url https://rawchat.cn/codex",
        "--output-json /tmp/image_agent_rawchat_direct_connectivity_",
    ):
        _require(required in rawchat_direct_command, f"rawchat direct connectivity command must include {required}")
    rawchat_direct_step = _step_by_id(steps, "verify_rawchat_direct_connectivity")
    _require(
        rawchat_direct_step.get("mutates_remote_state") is False,
        "rawchat direct connectivity step must be read-only",
    )
    _require(
        rawchat_direct_step.get("requires_operator_authorization") is False,
        "rawchat direct connectivity step must not require operator apply authorization",
    )
    rawchat_direct_expected = rawchat_direct_step.get("expected_success")
    _require(
        isinstance(rawchat_direct_expected, list)
        and "rawchat_direct_connectivity_status=passed" in rawchat_direct_expected
        and "rawchat_direct_proxy_env_trusted=false" in rawchat_direct_expected
        and "rawchat_direct_transport=direct" in rawchat_direct_expected,
        "rawchat direct connectivity expected_success mismatch",
    )
    production_env_command = commands["apply_production_readiness_env"]
    for required in (
        "scripts/bootstrap_image_agent.py",
        "--repo-root",
        "--image-agent-root /home/yyf/project/image_agent",
        "--env-file /home/yyf/project/image_agent/.env",
        "--production",
        "--model-provider rawchat",
        "--model-name gpt-5.5",
        "--model-review-name gpt-5.5",
        "--model-base-url https://rawchat.cn/codex",
        "--model-wire-api responses",
        "--verify-docker-command",
        "--skip-elasticsearch-hybrid",
        "--skip-workflow-images",
        "--config-only",
        "--apply",
    ):
        _require(required in production_env_command, f"production readiness env command must include {required}")
    production_cors_origins = _token_after(
        production_env_command,
        "--production-cors-origins",
        key="apply_production_readiness_env",
    )
    _require(
        _is_public_https_origin(production_cors_origins),
        "production readiness env command must include a concrete public HTTPS console origin",
    )
    production_public_base_url = _token_after(
        production_env_command,
        "--production-public-base-url",
        key="apply_production_readiness_env",
    )
    _require(
        _is_public_https_origin(production_public_base_url),
        "production readiness env command must include a concrete public HTTPS API origin",
    )
    docker_command = _token_after(
        production_env_command,
        "--docker-command",
        key="apply_production_readiness_env",
    )
    _require(
        docker_command in {"docker", "sudo -n docker"},
        "production readiness env command must include --docker-command docker or --docker-command 'sudo -n docker'",
    )
    production_env_step = _step_by_id(steps, "apply_production_readiness_env")
    _require(
        production_env_step.get("mutates_remote_state") is True,
        "production readiness env step must mutate remote state",
    )
    _require(
        production_env_step.get("requires_operator_authorization") is True,
        "production readiness env step must require operator authorization",
    )
    production_expected = production_env_step.get("expected_success")
    _require(
        isinstance(production_expected, list)
        and "IMAGE_AGENT_ENV=production" in production_expected
        and f"IMAGE_AGENT_CORS_ORIGINS={production_cors_origins}" in production_expected
        and f"IMAGE_AGENT_PUBLIC_BASE_URL={production_public_base_url}" in production_expected,
        "production readiness env step must declare production env expected_success",
    )
    for required in (
        "IMAGE_AGENT_MODEL_PROVIDER=rawchat",
        "IMAGE_AGENT_MODEL_NAME=gpt-5.5",
        "IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5",
        "IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex",
        "IMAGE_AGENT_MODEL_WIRE_API=responses",
        "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0",
        f"IMAGE_AGENT_DOCKER_COMMAND={docker_command}",
        "verify_docker_command completed",
    ):
        _require(
            required in production_expected,
            f"production readiness env expected_success must include {required}",
        )
    _require("IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands["restart_api_preflight_only"], "preflight command must set preflight-only mode")
    _require("restart_preflight:ok" == _step_by_id(steps, "restart_api_preflight_only").get("expected_success"), "preflight expected success mismatch")
    _require("bash tools/restart_remote_image_agent_api.sh" in commands["restart_api_normally"], "normal restart command missing")
    _require("IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" not in commands["restart_api_normally"], "normal restart must not be preflight-only")
    _require(
        "verify_elasticsearch_hybrid_prerequisites.py" in commands["verify_elasticsearch_hybrid_prerequisites"],
        "ES hybrid prerequisite verifier command missing",
    )
    _require(
        "--env-file /home/yyf/project/image_agent/.env" in commands["verify_elasticsearch_hybrid_prerequisites"],
        "ES hybrid prerequisite verifier must load the deployment env file",
    )
    _require(
        "--rag-status-url http://127.0.0.1:8000/agent/rag/status" in commands["verify_elasticsearch_hybrid_prerequisites"],
        "ES hybrid prerequisite verifier must read the deployed rag status",
    )
    es_prereq_command = commands["verify_elasticsearch_hybrid_prerequisites"]
    _require(
        "set -a; . /home/yyf/project/image_agent/.env; set +a;" in es_prereq_command
        and "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent" in es_prereq_command
        and "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env" in es_prereq_command,
        "ES prerequisite runtime probe must load deployment env",
    )
    _require(
        "-m app.scripts.probe_runtime_environment --json > /tmp/image_agent_runtime_probe_" in es_prereq_command,
        "ES hybrid prerequisite verifier must capture deployment runtime probe JSON",
    )
    _require(
        "--runtime-probe-json /tmp/image_agent_runtime_probe_" in commands[
            "verify_elasticsearch_hybrid_prerequisites"
        ],
        "ES hybrid prerequisite verifier must read deployment runtime probe JSON",
    )
    es_prereq_expected = _step_by_id(steps, "verify_elasticsearch_hybrid_prerequisites").get("expected_success")
    _require(
        isinstance(es_prereq_expected, list),
        "ES hybrid prerequisite verifier expected_success must include detailed checked fields",
    )
    missing_es_prereq_expected = [
        expected for expected in ELASTICSEARCH_HYBRID_PREREQ_EXPECTED_SUCCESS if expected not in es_prereq_expected
    ]
    _require(
        not missing_es_prereq_expected,
        "ES hybrid prerequisite verifier expected_success must include detailed checked fields",
    )
    strict_smoke_step = _step_by_id(steps, "run_strict_remote_smoke_acceptance")
    strict_smoke_command = commands["run_strict_remote_smoke_acceptance"]
    strict_smoke_verify_command = commands["verify_strict_remote_smoke_acceptance_json_after_normal_restart"]
    strict_smoke_env_export_command = commands["emit_fast_launch_acceptance_env_after_strict_verify"]
    for required in (
        "smoke_remote_agent.py",
        "--require-model",
        "--expected-model-wire-api responses",
        "--expected-model-provider-profile rawchat",
        "--require-model-tool-loop",
        "--require-project-agent-context",
        "--require-agent-workflow-confirmation",
        "--require-agent-workflow-resume",
        "--require-agent-workflow-fingerprint-negative",
        "--require-unknown-workflow-incubation",
        "--require-deployment-identity",
        "--require-production-readiness",
        "--require-runtime-toolchain",
        "--min-documents 60",
        "--min-chunks 200",
        "--require-raw-source-policy",
        "--require-vendor-pointer-integrity",
        "--require-elasticsearch-hybrid-rag",
        "--require-real-evidence-ids",
        "--require-completed-upload",
        "--require-uploaded-series",
        "--require-completed-task",
        "--require-task-events",
        "--require-observe-repair",
        "--require-launched-task",
        "--wait-task-completion-timeout-seconds 21600",
        "--wait-task-completion-poll-seconds 30",
        "--require-launchability-matrix",
        "--require-container-native-qc",
        "--min-native-qc-images 1",
        "--require-scientific-report-artifacts",
        "--min-scientific-report-images 1",
        "--output-json",
    ):
        _require(required in strict_smoke_command, f"strict smoke command must include {required}")
    for token, validator, message in (
        ("--deployment-id", _is_privacy_safe_release_symbol, "strict smoke command must include a concrete privacy-safe deployment id"),
        ("--expected-health-version", _is_privacy_safe_release_symbol, "strict smoke command must include a concrete privacy-safe expected health version"),
        ("--launch-workflow-type", _is_workflow_type_symbol, "strict smoke command must include a concrete registered workflow type"),
        ("--project-id", _is_positive_int_text, "strict smoke command must include a positive project id"),
        ("--upload-session-id", _is_positive_int_text, "strict smoke command must include a positive upload session id"),
    ):
        _require(validator(_token_after(strict_smoke_command, token, key="run_strict_remote_smoke_acceptance")), message)
    strict_parts = _command_parts(strict_smoke_command, key="run_strict_remote_smoke_acceptance")
    has_uploaded_series = "--uploaded-series-id" in strict_parts
    has_upload_nifti = "--upload-nifti-file" in strict_parts
    _require(
        has_uploaded_series != has_upload_nifti,
        "strict smoke command must choose either --uploaded-series-id or --upload-nifti-file",
    )
    if has_uploaded_series:
        _require(
            _is_positive_int_text(
                _token_after(strict_smoke_command, "--uploaded-series-id", key="run_strict_remote_smoke_acceptance")
            ),
            "strict smoke command must include a positive uploaded series id",
        )
    else:
        _require(
            _is_remote_nifti_path(
                _token_after(strict_smoke_command, "--upload-nifti-file", key="run_strict_remote_smoke_acceptance")
            ),
            "strict smoke command must include a concrete remote NIfTI file path",
        )
    _require(
        "<completed_task_id>" not in strict_smoke_command,
        "strict smoke command must launch and resolve the task id instead of using <completed_task_id>",
    )
    _require(
        "--launch-series-id <uploaded_series_id>" not in strict_smoke_command,
        "strict smoke command must use the uploaded series returned by --require-uploaded-series",
    )
    _require(
        strict_smoke_step.get("mutates_remote_state") is True,
        "strict smoke step must be marked as mutating remote state",
    )
    strict_smoke_json = _token_after(strict_smoke_command, "--output-json", key="run_strict_remote_smoke_acceptance")
    _require(
        strict_smoke_step.get("expected_output_json") == strict_smoke_json,
        "strict smoke expected_output_json must match --output-json",
    )
    strict_smoke_expected = strict_smoke_step.get("expected_success")
    _require(
        isinstance(strict_smoke_expected, list)
        and all(expected in strict_smoke_expected for expected in STRICT_SMOKE_EXPECTED_SUCCESS),
        "strict smoke expected_success must include strict acceptance evidence fields",
    )
    _require("verify_remote_smoke_acceptance.py" in strict_smoke_verify_command, "strict smoke verifier command missing")
    _require("--max-age-hours 24" in strict_smoke_verify_command, "strict smoke verifier must require freshness")
    _require(
        strict_smoke_json in shlex.split(strict_smoke_verify_command),
        "strict smoke verifier command must verify the smoke output JSON",
    )
    strict_smoke_verify_expected = _step_by_id(
        steps,
        "verify_strict_remote_smoke_acceptance_json_after_normal_restart",
    ).get("expected_success")
    _require(
        isinstance(strict_smoke_verify_expected, list)
        and all(expected in strict_smoke_verify_expected for expected in STRICT_SMOKE_VERIFIER_EXPECTED_SUCCESS),
        "strict smoke verifier expected_success must include checked strict acceptance evidence fields",
    )
    for required in (
        "scripts/bootstrap_image_agent.py",
        "--env-file /home/yyf/project/image_agent/.env",
        "--skip-elasticsearch-hybrid",
        "--skip-workflow-images",
        "--config-only",
        "--strict-acceptance-max-age-hours 24",
        "--apply",
    ):
        _require(required in strict_smoke_env_export_command, f"fast-launch env apply command must include {required}")
    _require(
        "--emit-fast-launch-env" not in strict_smoke_env_export_command,
        "fast-launch env apply command must use bootstrap instead of printing env lines",
    )
    _require(
        strict_smoke_json in shlex.split(strict_smoke_env_export_command),
        "fast-launch env apply command must verify the smoke output JSON",
    )
    restart_after_fast_launch_step = _step_by_id(steps, "restart_api_after_fast_launch_acceptance_env")
    restart_after_fast_launch_command = commands["restart_api_after_fast_launch_acceptance_env"]
    _require(
        restart_after_fast_launch_step.get("mutates_remote_state") is True,
        "fast-launch env restart step must mutate remote state",
    )
    _require(
        restart_after_fast_launch_step.get("requires_operator_authorization") is True,
        "fast-launch env restart step must require operator authorization",
    )
    for required in (
        "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env",
        "bash tools/restart_remote_image_agent_api.sh",
    ):
        _require(required in restart_after_fast_launch_command, f"fast-launch env restart command must include {required}")
    final_fast_launch_command = commands["verify_final_fast_launch_readiness"]
    _require(
        "http://127.0.0.1:8000/deployment" in final_fast_launch_command,
        "final fast-launch readiness check must read /deployment",
    )
    final_fast_launch_expected = _step_by_id(steps, "verify_final_fast_launch_readiness").get("expected_success")
    _require(
        isinstance(final_fast_launch_expected, list)
        and "fast_launch_readiness.status=ready" in final_fast_launch_expected
        and "fast_launch_readiness.checks.strict_remote_acceptance.status=passed" in final_fast_launch_expected
        and "fast_launch_readiness.checks.production_deployment.status=passed" in final_fast_launch_expected
        and "fast_launch_readiness.checks.production_deployment.required=true" in final_fast_launch_expected
        and "fast_launch_readiness.checks.production_deployment.ready=true" in final_fast_launch_expected,
        "final fast-launch readiness expected_success mismatch",
    )
    for required in (
        "p.get(\"required\") is True",
        "p.get(\"ready\") is True",
    ):
        _require(required in final_fast_launch_command, f"final fast-launch readiness command must include {required}")

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "request_type": request["request_type"],
            "authorization_required": request["authorization_required"],
            "target_task_ids": target_task_ids,
            "approval_fingerprint": approval_fingerprint,
            "verified_approval_generated_at_utc": generated_at_utc.isoformat(),
            "max_age_hours": float(max_age_hours),
            "expires_at_utc": expires_at_utc.isoformat(),
            "followup_step_ids": step_ids,
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify a stale-task apply approval request JSON.")
    parser.add_argument("request_json", help="Path to JSON written by build_stale_task_apply_request.py.")
    parser.add_argument("--task-id", action="append", type=int, dest="task_ids")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--now-utc", default=None, help="Testing hook: ISO-8601 UTC timestamp used as current time.")
    args = parser.parse_args(argv)
    source_path = Path(args.request_json)
    request = json.loads(source_path.read_text(encoding="utf-8"))
    report = verify_apply_request(
        request,
        expected_task_ids=args.task_ids,
        max_age_hours=args.max_age_hours,
        now_utc=args.now_utc,
    )
    report["source_json"] = str(source_path)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
