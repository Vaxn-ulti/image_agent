import importlib.util
import json
import re
from pathlib import Path

from tests.test_verify_stale_task_approval import _approval_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "build_stale_task_apply_request.py"
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}")
REMOTE_LIVE_ROOT_SNIPPET = "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent"
REMOTE_ROOTFIX_OVERLAY = "/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z"
OLD_GATE_OVERLAY = "/home/yyf/project/image_agent_releases/codex-gate-verifiers-efca895b-20260613T165132"
PRODUCTION_CORS_ORIGINS = "https://console.image-agent.example.com"
PRODUCTION_PUBLIC_BASE_URL = "https://api.image-agent.example.com"


def load_module():
    spec = importlib.util.spec_from_file_location("build_stale_task_apply_request", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_stale_task_apply_request_requires_operator_authorization(tmp_path):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    payload = _approval_payload()
    approval_json.write_text(json.dumps(payload), encoding="utf-8")

    request = module.build_apply_request(
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

    assert request["status"] == "operator_authorization_required"
    assert request["request_type"] == "stale_task_apply_approval"
    assert request["authorization_required"] is True
    assert request["approval_json"] == str(approval_json)
    assert request["target_task_ids"] == [83, 84]
    assert request["approval_fingerprint"] == payload["approval_fingerprint"]
    assert request["approval_expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"
    assert request["verified_approval"]["status"] == "passed"
    assert request["verified_approval"]["checked"]["generated_at_utc"] == payload["generated_at"]
    assert request["must_not_run_until"] == "operator explicitly approves stale-task apply"

    apply = request["apply_step"]
    assert apply["mutates_remote_state"] is True
    assert apply["requires_operator_authorization"] is True
    assert "set -a; . /home/yyf/project/image_agent/.env; set +a;" in apply["command"]
    assert REMOTE_LIVE_ROOT_SNIPPET in apply["command"]
    assert REMOTE_ROOTFIX_OVERLAY in apply["command"]
    assert OLD_GATE_OVERLAY not in apply["command"]
    assert "reconcile_stale_tasks.py --apply --max-age-hours 24 --task-id 83 --task-id 84" in apply["command"]
    assert f"--approval-json {approval_json}" in apply["command"]
    assert "--reason \"operator confirmed no matching running Image Agent container\"" in apply["command"]
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in apply["command"]
    assert API_KEY_SHAPED_RE.search(json.dumps(request)) is None


def test_build_stale_task_apply_request_includes_post_apply_gates(tmp_path):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    request = module.build_apply_request(
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

    commands = "\n".join(step["command"] for step in request["required_followup_steps"])
    steps_by_id = {step["id"]: step for step in request["required_followup_steps"]}
    assert [step["id"] for step in request["required_followup_steps"]] == [
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
    assert REMOTE_LIVE_ROOT_SNIPPET in steps_by_id["collect_post_apply_clean_dry_run"]["command"]
    assert REMOTE_ROOTFIX_OVERLAY in commands
    assert OLD_GATE_OVERLAY not in commands
    assert "reconcile_stale_tasks.py --max-age-hours 24 --check-containers --task-id 83 --task-id 84" in commands
    assert "verify_stale_task_resolution.py" in commands
    assert "--require-empty-active --max-age-hours 24" in commands
    docker_policy = steps_by_id["verify_docker_host_policy_dry_run"]
    assert docker_policy["mutates_remote_state"] is False
    assert docker_policy["requires_operator_authorization"] is False
    assert "scripts/configure_docker_access.py" in docker_policy["command"]
    assert "--user yyf" in docker_policy["command"]
    assert "--docker-bin /usr/bin/docker" in docker_policy["command"]
    assert "--output-json /tmp/image_agent_docker_access_policy_dry_run_" in docker_policy["command"]
    assert "--apply" not in docker_policy["command"]
    assert "plan_id=image_agent_docker_access_policy_v1" in docker_policy["expected_success"]
    assert "mode=dry_run" in docker_policy["expected_success"]
    assert "sudoers_file=/etc/sudoers.d/image-agent-docker" in docker_policy["expected_success"]
    assert "verification_command=sudo -n docker version" in docker_policy["expected_success"]
    rawchat_direct = steps_by_id["verify_rawchat_direct_connectivity"]
    assert rawchat_direct["mutates_remote_state"] is False
    assert rawchat_direct["requires_operator_authorization"] is False
    assert "scripts/verify_rawchat_direct_connectivity.py" in rawchat_direct["command"]
    assert "--url https://rawchat.cn/codex" in rawchat_direct["command"]
    assert "--output-json /tmp/image_agent_rawchat_direct_connectivity_20260612T050000Z.json" in rawchat_direct["command"]
    assert "rawchat_direct_connectivity_status=passed" in rawchat_direct["expected_success"]
    assert "rawchat_direct_proxy_env_trusted=false" in rawchat_direct["expected_success"]
    assert "rawchat_direct_transport=direct" in rawchat_direct["expected_success"]
    production_env = steps_by_id["apply_production_readiness_env"]
    assert production_env["mutates_remote_state"] is True
    assert production_env["requires_operator_authorization"] is True
    assert "scripts/bootstrap_image_agent.py" in production_env["command"]
    assert "--repo-root" in production_env["command"]
    assert "--image-agent-root /home/yyf/project/image_agent" in production_env["command"]
    assert "--env-file /home/yyf/project/image_agent/.env" in production_env["command"]
    assert "--production" in production_env["command"]
    assert f"--production-cors-origins {PRODUCTION_CORS_ORIGINS}" in production_env["command"]
    assert f"--production-public-base-url {PRODUCTION_PUBLIC_BASE_URL}" in production_env["command"]
    assert "--model-provider rawchat" in production_env["command"]
    assert "--model-name gpt-5.5" in production_env["command"]
    assert "--model-review-name gpt-5.5" in production_env["command"]
    assert "--model-base-url https://rawchat.cn/codex" in production_env["command"]
    assert "--model-wire-api responses" in production_env["command"]
    assert "--model-trust-env-proxy" not in production_env["command"]
    assert '--docker-command "sudo -n docker"' in production_env["command"]
    assert "--verify-docker-command" in production_env["command"]
    assert "--skip-elasticsearch-hybrid" in production_env["command"]
    assert "--skip-workflow-images" in production_env["command"]
    assert "--config-only" in production_env["command"]
    assert "--apply" in production_env["command"]
    assert "IMAGE_AGENT_ENV=production" in production_env["expected_success"]
    assert f"IMAGE_AGENT_CORS_ORIGINS={PRODUCTION_CORS_ORIGINS}" in production_env["expected_success"]
    assert f"IMAGE_AGENT_PUBLIC_BASE_URL={PRODUCTION_PUBLIC_BASE_URL}" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_PROVIDER=rawchat" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_NAME=gpt-5.5" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_WIRE_API=responses" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0" in production_env["expected_success"]
    assert "IMAGE_AGENT_DOCKER_COMMAND=sudo -n docker" in production_env["expected_success"]
    assert "verify_docker_command completed" in production_env["expected_success"]
    assert "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands
    assert "restart_api_normally" in json.dumps(request)
    assert "bash tools/restart_remote_image_agent_api.sh" in commands
    assert "bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env" in commands
    assert "smoke_remote_agent.py" in commands
    assert "--require-model" in commands
    assert "--expected-model-wire-api responses" in commands
    assert "--expected-model-provider-profile rawchat" in commands
    assert "--require-model-tool-loop" in commands
    assert "--require-project-agent-context" in commands
    assert "--require-agent-workflow-confirmation" in commands
    assert "--require-agent-workflow-resume" in commands
    assert "--require-agent-workflow-fingerprint-negative" in commands
    assert "--require-unknown-workflow-incubation" in commands
    assert "--require-production-readiness" in commands
    assert "--require-runtime-toolchain" in commands
    assert "--deployment-id codex-gate-verifiers-efca895b" in commands
    assert "--expected-health-version 0.2.0-efca895b" in commands
    assert "--require-elasticsearch-hybrid-rag" in commands
    assert "--require-real-evidence-ids" in commands
    assert "--require-completed-upload" in commands
    assert "--require-uploaded-series" in commands
    assert "--upload-nifti-file /tmp/image_agent_acceptance/sub-01_T1w.nii.gz" in commands
    assert "--require-completed-task" in commands
    assert "--require-task-events" in commands
    assert "--require-observe-repair" in commands
    assert "--require-launched-task" in commands
    assert "--launch-series-id <uploaded_series_id>" not in commands
    assert "--launch-workflow-type t1_deepprep_anat_report" in commands
    assert "--wait-task-completion-timeout-seconds 21600" in commands
    assert "--wait-task-completion-poll-seconds 30" in commands
    assert "--require-container-native-qc" in commands
    assert "--require-scientific-report-artifacts" in commands
    assert "--project-id 13" in commands
    assert "--upload-session-id 77" in commands
    assert "<accepted_release_or_commit>" not in commands
    assert "<expected_health_version>" not in commands
    assert "<remote_nifti_file>" not in commands
    assert "<real_registered_workflow_type>" not in commands
    assert "<project_id>" not in commands
    assert "<upload_session_id>" not in commands
    assert "restart_preflight:ok" in json.dumps(request)
    assert "verify_elasticsearch_hybrid_prerequisites.py" in commands
    assert "--env-file /home/yyf/project/image_agent/.env" in commands
    assert "--rag-status-url http://127.0.0.1:8000/agent/rag/status" in commands
    assert "set -a; . /home/yyf/project/image_agent/.env; set +a;" in commands
    assert "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent" in commands
    assert "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env" in commands
    assert (
        "PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python "
        "-m app.scripts.probe_runtime_environment --json > "
        "/tmp/image_agent_runtime_probe_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json"
    ) in commands
    assert "--runtime-probe-json /tmp/image_agent_runtime_probe_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json" in commands
    es_expected = steps_by_id["verify_elasticsearch_hybrid_prerequisites"]["expected_success"]
    assert isinstance(es_expected, list)
    for expected in [
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
        "rag_status_hybrid_error_absent=true",
        "rag_status_hybrid_embedding_error_absent=true",
        "rag_status_hybrid_embedding_provider production configured",
        "rag_status_hybrid_embedding_provider_matches_env=true",
        "rag_status_hybrid_embedding_model present",
        "rag_status_hybrid_embedding_model_matches_env=true",
        "rag_status_hybrid_embedding_transport production-safe",
        "rag_status_hybrid_embedding_endpoint_configured=true",
        "rag_status_hybrid_embedding_production_ready=true",
    ]:
        assert expected in es_expected
    assert "verify_remote_smoke_acceptance.py" in commands
    assert "--max-age-hours 24" in commands
    fast_launch_step = steps_by_id["emit_fast_launch_acceptance_env_after_strict_verify"]
    assert "scripts/bootstrap_image_agent.py" in fast_launch_step["command"]
    assert "--strict-acceptance-json /tmp/image_agent_remote_smoke_acceptance_20260612T050000Z.json" in fast_launch_step["command"]
    assert "--strict-acceptance-max-age-hours 24" in fast_launch_step["command"]
    assert "--skip-elasticsearch-hybrid" in fast_launch_step["command"]
    assert "--skip-workflow-images" in fast_launch_step["command"]
    assert "--config-only" in fast_launch_step["command"]
    assert "--env-file /home/yyf/project/image_agent/.env" in fast_launch_step["command"]
    assert "--apply" in fast_launch_step["command"]
    assert "--emit-fast-launch-env" not in fast_launch_step["command"]
    post_acceptance_restart = steps_by_id["restart_api_after_fast_launch_acceptance_env"]
    assert post_acceptance_restart["mutates_remote_state"] is True
    assert post_acceptance_restart["requires_operator_authorization"] is True
    assert "bash tools/restart_remote_image_agent_api.sh" in post_acceptance_restart["command"]
    assert "bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env" in post_acceptance_restart["command"]
    final_readiness = steps_by_id["verify_final_fast_launch_readiness"]
    assert final_readiness["mutates_remote_state"] is False
    assert "http://127.0.0.1:8000/deployment" in final_readiness["command"]
    assert "fast_launch_readiness.status=ready" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.strict_remote_acceptance.status=passed" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.production_deployment.status=passed" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.production_deployment.required=true" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.production_deployment.ready=true" in final_readiness["expected_success"]
    assert "p.get(\"required\") is True" in final_readiness["command"]
    assert "p.get(\"ready\") is True" in final_readiness["command"]
    strict_expected = steps_by_id["run_strict_remote_smoke_acceptance"]["expected_success"]
    assert isinstance(strict_expected, list)
    for expected in [
        "model_status.trust_env_proxy=false",
        "model_status.deployment.model_gateway_access=direct",
        "launched_task.launch_source=agent_workflow_resume",
        "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type matches launched_task.runtime_workflow_type",
        "agent_workflow_confirmation.workflow_metadata.agent_selectable=true",
        "launched_task.runtime_workflow_type present",
        "task_result_summary.workflow_metadata.agent_selectable=true",
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
    ]:
        assert expected in strict_expected
    verify_expected = steps_by_id["verify_strict_remote_smoke_acceptance_json_after_normal_restart"]["expected_success"]
    assert isinstance(verify_expected, list)
    for expected in [
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
    ]:
        assert expected in verify_expected
    assert steps_by_id["run_strict_remote_smoke_acceptance"]["mutates_remote_state"] is True
    assert steps_by_id["emit_fast_launch_acceptance_env_after_strict_verify"]["mutates_remote_state"] is True
    assert steps_by_id["restart_api_after_fast_launch_acceptance_env"]["mutates_remote_state"] is True


def test_build_stale_task_apply_request_materializes_production_public_origins(tmp_path):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    request = module.build_apply_request(
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

    production_env = next(
        step for step in request["required_followup_steps"] if step["id"] == "apply_production_readiness_env"
    )
    assert f"--production-cors-origins {PRODUCTION_CORS_ORIGINS}" in production_env["command"]
    assert f"--production-public-base-url {PRODUCTION_PUBLIC_BASE_URL}" in production_env["command"]
    assert "--model-provider rawchat" in production_env["command"]
    assert "--model-base-url https://rawchat.cn/codex" in production_env["command"]
    assert '--docker-command "sudo -n docker"' in production_env["command"]
    assert "--verify-docker-command" in production_env["command"]
    assert "https://<console-hostname>" not in json.dumps(production_env, sort_keys=True)
    assert "https://<api-hostname>" not in json.dumps(production_env, sort_keys=True)
    assert f"IMAGE_AGENT_CORS_ORIGINS={PRODUCTION_CORS_ORIGINS}" in production_env["expected_success"]
    assert f"IMAGE_AGENT_PUBLIC_BASE_URL={PRODUCTION_PUBLIC_BASE_URL}" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0" in production_env["expected_success"]
    assert "IMAGE_AGENT_DOCKER_COMMAND=sudo -n docker" in production_env["expected_success"]
    assert "verify_docker_command completed" in production_env["expected_success"]


def test_build_stale_task_apply_request_can_reuse_existing_uploaded_series(tmp_path):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    request = module.build_apply_request(
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

    strict_smoke = next(
        step for step in request["required_followup_steps"] if step["id"] == "run_strict_remote_smoke_acceptance"
    )
    assert "--uploaded-series-id 49" in strict_smoke["command"]
    assert "--upload-nifti-file" not in strict_smoke["command"]
    assert "<uploaded_series_id>" not in json.dumps(request["required_followup_steps"], sort_keys=True)


def test_build_stale_task_apply_request_cli_writes_json(tmp_path, capsys):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    output_json = tmp_path / "apply-request.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    module.main(
        [
            str(approval_json),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-12T05:00:00Z",
            "--output-timestamp",
            "20260612T050000Z",
            "--deployment-id",
            "codex-gate-verifiers-efca895b",
            "--expected-health-version",
            "0.2.0-efca895b",
            "--remote-nifti-file",
            "/tmp/image_agent_acceptance/sub-01_T1w.nii.gz",
            "--workflow-type",
            "t1_deepprep_anat_report",
            "--project-id",
            "13",
            "--upload-session-id",
            "77",
            "--production-cors-origins",
            PRODUCTION_CORS_ORIGINS,
            "--production-public-base-url",
            PRODUCTION_PUBLIC_BASE_URL,
            "--output-json",
            str(output_json),
        ]
    )

    stdout_report = json.loads(capsys.readouterr().out)
    saved_report = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_report == saved_report
    assert saved_report["status"] == "operator_authorization_required"
    assert saved_report["output_json"] == str(output_json)
    assert saved_report["approval_expires_at_utc"] == "2026-06-13T04:14:24.156875+00:00"


def test_build_stale_task_apply_request_cli_can_reuse_existing_uploaded_series(tmp_path, capsys):
    module = load_module()
    approval_json = tmp_path / "approval.json"
    approval_json.write_text(json.dumps(_approval_payload()), encoding="utf-8")

    module.main(
        [
            str(approval_json),
            "--task-id",
            "83",
            "--task-id",
            "84",
            "--max-age-hours",
            "24",
            "--now-utc",
            "2026-06-12T05:00:00Z",
            "--output-timestamp",
            "20260612T050000Z",
            "--deployment-id",
            "codex-gate-verifiers-efca895b",
            "--expected-health-version",
            "0.2.0-efca895b",
            "--uploaded-series-id",
            "49",
            "--workflow-type",
            "t1_deepprep_anat_report",
            "--project-id",
            "27",
            "--upload-session-id",
            "10",
            "--production-cors-origins",
            PRODUCTION_CORS_ORIGINS,
            "--production-public-base-url",
            PRODUCTION_PUBLIC_BASE_URL,
        ]
    )

    stdout_report = json.loads(capsys.readouterr().out)
    strict_smoke = next(
        step for step in stdout_report["required_followup_steps"] if step["id"] == "run_strict_remote_smoke_acceptance"
    )
    assert "--uploaded-series-id 49" in strict_smoke["command"]
    assert "--upload-nifti-file" not in strict_smoke["command"]
