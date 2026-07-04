import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = REPO_ROOT / "docs" / "deployment" / "remote-release-gate-command-plan.json"
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_release_gate_command_plan.py"
FRESH_APPROVAL_JSON = "<fresh_reviewed_approval_json>"
EXPIRED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260614T080202Z.json"
REVIEWED_APPROVAL_JSON = "/tmp/image_agent_stale_tasks_83_84_dry_run_20260616T010000Z.json"
CURRENT_RELEASE_OVERLAY = "/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_release_gate_command_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operator_authorization_plan() -> dict:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["status"] = "operator_authorization_required"
    plan["approval_json"] = REVIEWED_APPROVAL_JSON
    plan["approval_json_state"] = {
        "status": "fresh_reviewed",
        "previous_approval_json": EXPIRED_APPROVAL_JSON,
        "verified_approval_generated_at_utc": "2026-06-16T01:00:00+00:00",
        "approval_expires_at_utc": "2026-06-17T01:00:00+00:00",
        "next_required_step": "apply_approved_stale_task_resolution",
    }
    plan["stale_task_approval_refresh"] = {
        "status": "superseded_by_fresh_reviewed_approval",
        "source_approval_json": REVIEWED_APPROVAL_JSON,
        "approval_expires_at_utc": "2026-06-17T01:00:00+00:00",
        "next_required_step": "apply_approved_stale_task_resolution",
        "mutates_remote_state": False,
        "requires_operator_authorization": False,
    }
    for step in plan["steps"]:
        step["command"] = step["command"].replace(FRESH_APPROVAL_JSON, REVIEWED_APPROVAL_JSON)
        step["command"] = step["command"].replace("<accepted_release_or_commit>", "codex-gate-verifiers-efca895b")
        step["command"] = step["command"].replace("<expected_health_version>", "0.2.0-efca895b")
        step["command"] = step["command"].replace("<remote_nifti_file>", "/tmp/image_agent_acceptance/sub-01_T1w.nii.gz")
        step["command"] = step["command"].replace("<real_registered_workflow_type>", "t1_deepprep_anat_report")
        step["command"] = step["command"].replace("<project_id>", "13")
        step["command"] = step["command"].replace("<upload_session_id>", "77")
        step["command"] = step["command"].replace("https://<console-hostname>", "https://console.example.com")
        step["command"] = step["command"].replace("https://<api-hostname>", "https://api.example.com")
        step["command"] = step["command"].replace("<timestamp>", "20260616T020000Z")
        step["command"] = step["command"].replace(
            "/tmp/image_agent_stale_tasks_83_84_apply_<timestamp>.json",
            "/tmp/image_agent_stale_tasks_83_84_apply_20260616T020000Z.json",
        )
        step["command"] = step["command"].replace(
            "/tmp/image_agent_stale_tasks_83_84_resolved_dry_run_<timestamp>.json",
            "/tmp/image_agent_stale_tasks_83_84_resolved_dry_run_20260616T020000Z.json",
        )
        step["command"] = step["command"].replace(
            "/tmp/image_agent_remote_smoke_acceptance_<timestamp>.json",
            "/tmp/image_agent_remote_smoke_acceptance_20260616T020000Z.json",
        )
        step["expected_success"] = [
            item.replace(FRESH_APPROVAL_JSON, REVIEWED_APPROVAL_JSON)
            .replace("https://<console-hostname>", "https://console.example.com")
            .replace("https://<api-hostname>", "https://api.example.com")
            for item in step["expected_success"]
        ]
    return plan


def _step(plan: dict, step_id: str) -> dict:
    matches = [step for step in plan["steps"] if step["id"] == step_id]
    assert len(matches) == 1
    return matches[0]


def test_remote_release_gate_command_plan_is_machine_checkable():
    verifier = load_verifier()
    plan = verifier.load_plan(PLAN_PATH)
    report = verifier.verify_plan(plan)

    assert report["status"] == "passed"
    assert report["checked"]["plan_id"] == "remote_release_gate_after_stale_task_approval_v1"
    assert report["checked"]["step_count"] == 17
    assert report["checked"]["operator_authorization_required_steps"] == [
        "apply_approved_stale_task_resolution",
        "apply_production_readiness_env",
        "restart_api_normally",
        "run_strict_remote_smoke_acceptance",
        "emit_fast_launch_acceptance_env_after_strict_verify",
        "restart_api_after_fast_launch_acceptance_env",
    ]
    assert report["checked"]["mutating_steps"] == [
        "apply_approved_stale_task_resolution",
        "apply_production_readiness_env",
        "restart_api_normally",
        "run_strict_remote_smoke_acceptance",
        "emit_fast_launch_acceptance_env_after_strict_verify",
        "restart_api_after_fast_launch_acceptance_env",
    ]
    assert report["checked"]["approval_request_required_fields"] == [
        "approval_fingerprint",
        "approval_expires_at_utc",
    ]
    assert report["checked"]["approval_json_status"] == "refresh_required"
    assert plan["approval_request_requirements"] == {
        "must_include_fields": [
            "approval_fingerprint",
            "approval_expires_at_utc",
        ],
        "approval_expires_at_utc_source": "verified_approval.checked.generated_at_utc + freshness_hours",
    }


def test_remote_release_gate_command_plan_requires_rawchat_direct_bootstrap_config():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step = _step(plan, "apply_production_readiness_env")
    step["command"] = step["command"].replace(" --model-provider rawchat", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "apply_production_readiness_env.command must include --model-provider rawchat" in str(exc.value)


def test_remote_release_gate_command_plan_requires_docker_command_verification_before_restart():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step = _step(plan, "apply_production_readiness_env")
    step["command"] = step["command"].replace(" --verify-docker-command", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "apply_production_readiness_env.command must include --verify-docker-command" in str(exc.value)


def test_remote_release_gate_command_plan_requires_docker_host_policy_dry_run_before_env_apply():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["steps"] = [step for step in plan["steps"] if step["id"] != "verify_docker_host_policy_dry_run"]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected release gate sequence" in str(exc.value)


def test_remote_release_gate_command_plan_rejects_docker_host_policy_apply():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step = _step(plan, "verify_docker_host_policy_dry_run")
    step["command"] = step["command"] + " --apply"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "verify_docker_host_policy_dry_run.command must not include --apply" in str(exc.value)


def test_remote_release_gate_command_plan_requires_rawchat_direct_connectivity_probe():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["steps"] = [step for step in plan["steps"] if step["id"] != "verify_rawchat_direct_connectivity"]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected release gate sequence" in str(exc.value)


def test_remote_release_gate_command_plan_orders_safe_remote_acceptance_steps():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step_ids = [step["id"] for step in plan["steps"]]

    assert step_ids == [
        "verify_release_overlay_contents",
        "verify_frontend_api_contract_tests",
        "verify_fresh_stale_task_approval",
        "apply_approved_stale_task_resolution",
        "collect_post_apply_clean_dry_run",
        "verify_post_apply_clean_resolution",
        "verify_docker_host_policy_dry_run",
        "verify_rawchat_direct_connectivity",
        "apply_production_readiness_env",
        "restart_api_preflight_only",
        "restart_api_normally",
        "verify_elasticsearch_hybrid_prerequisites",
        "run_strict_remote_smoke_acceptance",
        "verify_strict_remote_smoke_acceptance_json",
        "emit_fast_launch_acceptance_env_after_strict_verify",
        "restart_api_after_fast_launch_acceptance_env",
        "verify_final_fast_launch_readiness",
    ]

    commands = "\n".join(step["command"] for step in plan["steps"])
    assert plan["status"] == "approval_refresh_required"
    assert plan["release_overlay"] == CURRENT_RELEASE_OVERLAY
    assert plan["approval_json"] == FRESH_APPROVAL_JSON
    assert plan["approval_json_state"]["previous_approval_json"] == EXPIRED_APPROVAL_JSON
    assert f"--approval-json {FRESH_APPROVAL_JSON}" in commands
    assert EXPIRED_APPROVAL_JSON not in commands
    assert "approval_fingerprint" in json.dumps(plan, sort_keys=True)
    assert "approval_expires_at_utc" in json.dumps(plan, sort_keys=True)
    overlay_step = _step(plan, "verify_release_overlay_contents")
    assert overlay_step["mutates_remote_state"] is False
    assert overlay_step["requires_operator_authorization"] is False
    assert f"cd {CURRENT_RELEASE_OVERLAY}" in overlay_step["command"]
    assert "test -f apps/api/scripts/build_stale_task_apply_request.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/verify_stale_task_apply_request.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/build_elasticsearch_hybrid_config_plan.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/setup_elasticsearch_hybrid_rag.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/setup_local_embedding_service.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/verify_elasticsearch_hybrid_prerequisites.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/smoke_remote_agent.py" in overlay_step["command"]
    assert "test -f apps/api/scripts/verify_remote_smoke_acceptance.py" in overlay_step["command"]
    assert "test -f apps/api/app/scripts/probe_runtime_environment.py" in overlay_step["command"]
    assert "test -f scripts/check_repository_hygiene.py" in overlay_step["command"]
    assert "test -f scripts/run_frontend_contract_tests.py" in overlay_step["command"]
    assert "test -f scripts/verify_rawchat_direct_connectivity.py" in overlay_step["command"]
    assert "test -f docs/deployment/remote-elasticsearch-hybrid-config-plan.json" in overlay_step["command"]
    assert "test -f docs/rag/contracts/elasticsearch-hybrid-search.md" in overlay_step["command"]
    assert "test -f apps/console/package.json" in overlay_step["command"]
    assert "test -f apps/console/package-lock.json" in overlay_step["command"]
    assert "test -f apps/console/src/lib/api.test.ts" in overlay_step["command"]
    assert "test -f apps/console/src/lib/workflows.test.ts" in overlay_step["command"]
    assert "test -f apps/console/src/routes/AgentPage.test.tsx" in overlay_step["command"]
    assert "test -f apps/console/src/routes/WorkflowsPage.test.tsx" in overlay_step["command"]
    assert "test -f apps/console/src/routes/ResultDetailPage.test.tsx" in overlay_step["command"]
    assert (
        "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py "
        "docs/deployment/remote-elasticsearch-hybrid-config-plan.json"
    ) in overlay_step["command"]
    assert "scripts/check_repository_hygiene.py" in overlay_step["command"]
    assert "README.md scripts apps/api/scripts docs/deployment docs/rag docs/skills" in overlay_step["command"]
    assert "test -f tools/restart_remote_image_agent_api.sh" in overlay_step["command"]
    assert "release_overlay_current=true" in overlay_step["expected_success"]
    assert "required_gate_scripts_present=true" in overlay_step["expected_success"]
    assert "elasticsearch_hybrid_contract_present=true" in overlay_step["expected_success"]
    assert "repository_hygiene_status=passed" in overlay_step["expected_success"]
    assert "elasticsearch_hybrid_config_plan_status=passed" in overlay_step["expected_success"]
    frontend_step = _step(plan, "verify_frontend_api_contract_tests")
    assert frontend_step["mutates_remote_state"] is False
    assert frontend_step["requires_operator_authorization"] is False
    assert f"cd {CURRENT_RELEASE_OVERLAY}" in frontend_step["command"]
    assert "scripts/run_frontend_contract_tests.py" in frontend_step["command"]
    assert "--console-dir apps/console" in frontend_step["command"]
    assert "--install" in frontend_step["command"]
    assert "--registry https://registry.npmjs.org/" in frontend_step["command"]
    assert "--fetch-timeout-ms 20000" in frontend_step["command"]
    assert "--fetch-retries 0" in frontend_step["command"]
    assert "--timeout-seconds 120" in frontend_step["command"]
    assert "--cache-dir /tmp/image_agent_console_npm_cache_" in frontend_step["command"]
    assert "--offline" in frontend_step["command"]
    assert "src/lib/api.test.ts" in frontend_step["command"]
    assert "src/lib/workflows.test.ts" in frontend_step["command"]
    assert "src/routes/AgentPage.test.tsx" in frontend_step["command"]
    assert "src/routes/WorkflowsPage.test.tsx" in frontend_step["command"]
    assert "src/routes/ResultDetailPage.test.tsx" in frontend_step["command"]
    assert "frontend_api_contract_tests=passed" in frontend_step["expected_success"]
    assert "--check-containers --task-id 83 --task-id 84" in commands
    assert "--require-empty-active --max-age-hours 24" in commands
    docker_policy = _step(plan, "verify_docker_host_policy_dry_run")
    assert docker_policy["mutates_remote_state"] is False
    assert docker_policy["requires_operator_authorization"] is False
    assert "scripts/configure_docker_access.py" in docker_policy["command"]
    assert "--user yyf" in docker_policy["command"]
    assert "--docker-bin /usr/bin/docker" in docker_policy["command"]
    assert "--output-json /tmp/image_agent_docker_access_policy_dry_run_<timestamp>.json" in docker_policy["command"]
    assert "--apply" not in docker_policy["command"]
    assert "plan_id=image_agent_docker_access_policy_v1" in docker_policy["expected_success"]
    assert "mode=dry_run" in docker_policy["expected_success"]
    assert "sudoers_file=/etc/sudoers.d/image-agent-docker" in docker_policy["expected_success"]
    assert "verification_command=sudo -n docker version" in docker_policy["expected_success"]
    rawchat_direct = _step(plan, "verify_rawchat_direct_connectivity")
    assert rawchat_direct["mutates_remote_state"] is False
    assert rawchat_direct["requires_operator_authorization"] is False
    assert "scripts/verify_rawchat_direct_connectivity.py" in rawchat_direct["command"]
    assert "--url https://rawchat.cn/codex" in rawchat_direct["command"]
    assert "--output-json /tmp/image_agent_rawchat_direct_connectivity_<timestamp>.json" in rawchat_direct["command"]
    assert "rawchat_direct_connectivity_status=passed" in rawchat_direct["expected_success"]
    assert "rawchat_direct_proxy_env_trusted=false" in rawchat_direct["expected_success"]
    assert "rawchat_direct_transport=direct" in rawchat_direct["expected_success"]
    production_env = _step(plan, "apply_production_readiness_env")
    assert production_env["mutates_remote_state"] is True
    assert production_env["requires_operator_authorization"] is True
    assert "scripts/bootstrap_image_agent.py" in production_env["command"]
    assert "--repo-root" in production_env["command"]
    assert "--image-agent-root /home/yyf/project/image_agent" in production_env["command"]
    assert "--env-file /home/yyf/project/image_agent/.env" in production_env["command"]
    assert "--production" in production_env["command"]
    assert "--deployment-scope public_internet" in production_env["command"]
    assert "--production-cors-origins https://<console-hostname>" in production_env["command"]
    assert "--production-public-base-url https://<api-hostname>" in production_env["command"]
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
    assert "IMAGE_AGENT_DEPLOYMENT_SCOPE=public_internet" in production_env["expected_success"]
    assert "IMAGE_AGENT_CORS_ORIGINS=https://<console-hostname>" in production_env["expected_success"]
    assert "IMAGE_AGENT_PUBLIC_BASE_URL=https://<api-hostname>" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_PROVIDER=rawchat" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_NAME=gpt-5.5" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_REVIEW_NAME=gpt-5.5" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_BASE_URL=https://rawchat.cn/codex" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_WIRE_API=responses" in production_env["expected_success"]
    assert "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY=0" in production_env["expected_success"]
    assert "IMAGE_AGENT_DOCKER_COMMAND=sudo -n docker" in production_env["expected_success"]
    assert "verify_docker_command completed" in production_env["expected_success"]
    assert "IMAGE_AGENT_RESTART_PREFLIGHT_ONLY=1" in commands
    assert "restart_preflight:ok" in json.dumps(plan, sort_keys=True)
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in commands
    assert _step(plan, "restart_api_normally")["requires_operator_authorization"] is True
    assert _step(plan, "run_strict_remote_smoke_acceptance")["requires_operator_authorization"] is True
    fast_launch_env = _step(plan, "emit_fast_launch_acceptance_env_after_strict_verify")
    assert fast_launch_env["mutates_remote_state"] is True
    assert fast_launch_env["requires_operator_authorization"] is True
    assert "scripts/bootstrap_image_agent.py" in fast_launch_env["command"]
    assert "--strict-acceptance-json /tmp/image_agent_remote_smoke_acceptance_<timestamp>.json" in fast_launch_env["command"]
    assert "--strict-acceptance-max-age-hours 24" in fast_launch_env["command"]
    assert "--skip-elasticsearch-hybrid" in fast_launch_env["command"]
    assert "--skip-workflow-images" in fast_launch_env["command"]
    assert "--config-only" in fast_launch_env["command"]
    assert "--env-file /home/yyf/project/image_agent/.env" in fast_launch_env["command"]
    assert "--apply" in fast_launch_env["command"]
    assert "--emit-fast-launch-env" not in fast_launch_env["command"]
    post_acceptance_restart = _step(plan, "restart_api_after_fast_launch_acceptance_env")
    assert post_acceptance_restart["mutates_remote_state"] is True
    assert post_acceptance_restart["requires_operator_authorization"] is True
    assert "bash tools/restart_remote_image_agent_api.sh" in post_acceptance_restart["command"]
    assert "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env" in post_acceptance_restart["command"]
    assert "bash tools/restart_remote_image_agent_api.sh /home/yyf/project/image_agent/.env" in post_acceptance_restart["command"]
    final_readiness = _step(plan, "verify_final_fast_launch_readiness")
    assert final_readiness["mutates_remote_state"] is False
    assert final_readiness["requires_operator_authorization"] is False
    assert "http://127.0.0.1:8000/deployment" in final_readiness["command"]
    assert "fast_launch_readiness.status=ready" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.strict_remote_acceptance.status=passed" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.production_deployment.status=passed" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.production_deployment.required=true" in final_readiness["expected_success"]
    assert "fast_launch_readiness.checks.production_deployment.ready=true" in final_readiness["expected_success"]
    assert "p.get(\"required\") is True" in final_readiness["command"]
    assert "p.get(\"ready\") is True" in final_readiness["command"]
    es_preflight = _step(plan, "verify_elasticsearch_hybrid_prerequisites")
    assert es_preflight["mutates_remote_state"] is False
    assert es_preflight["requires_operator_authorization"] is False
    assert "verify_elasticsearch_hybrid_prerequisites.py" in es_preflight["command"]
    assert "set -a; . /home/yyf/project/image_agent/.env; set +a;" in es_preflight["command"]
    assert "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent" in es_preflight["command"]
    assert "IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env" in es_preflight["command"]
    assert (
        "PYTHONPATH=. /home/yyf/project/image_agent/apps/api/.venv/bin/python "
        "-m app.scripts.probe_runtime_environment --json > /tmp/image_agent_runtime_probe_<timestamp>.json"
    ) in es_preflight["command"]
    assert "--env-file /home/yyf/project/image_agent/.env" in es_preflight["command"]
    assert "--rag-status-url http://127.0.0.1:8000/agent/rag/status" in es_preflight["command"]
    assert "--runtime-probe-json /tmp/image_agent_runtime_probe_<timestamp>.json" in es_preflight["command"]
    assert "elasticsearch_url_configured=true" in es_preflight["expected_success"]
    assert "rag_embedding_provider_configured=true" in es_preflight["expected_success"]
    assert "rag_embedding_provider_production_configured=true" in es_preflight["expected_success"]
    assert "rag_embedding_model_configured=true" in es_preflight["expected_success"]
    assert "rag_embedding_endpoint_configured=true" in es_preflight["expected_success"]
    assert "secrets_redacted=true" in es_preflight["expected_success"]
    assert "--require-model" in commands
    assert "rag_status_hybrid_engine=elasticsearch" in es_preflight["expected_success"]
    assert "rag_status_hybrid_configured=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_index privacy-safe" in es_preflight["expected_success"]
    assert "rag_status_hybrid_index_matches_env=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_indexed_chunk_count>0" in es_preflight["expected_success"]
    assert "rag_status_hybrid_dense_vector_dims>0" in es_preflight["expected_success"]
    assert "rag_status_hybrid_fusion=rrf" in es_preflight["expected_success"]
    assert "rag_status_hybrid_official_rrf_source_present=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_error_absent=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_error_absent=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_provider production configured" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_provider_matches_env=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_model present" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_model_matches_env=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_transport production-safe" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_endpoint_configured=true" in es_preflight["expected_success"]
    assert "rag_status_hybrid_embedding_production_ready=true" in es_preflight["expected_success"]
    assert "runtime_probe_machine_binding=runtime_discovered" in es_preflight["expected_success"]
    assert "runtime_probe_workflow_tool_execution=deployment_server_local" in es_preflight["expected_success"]
    assert "runtime_probe_docker_runtime_host=api_server" in es_preflight["expected_success"]
    assert "runtime_probe_docker_accessible=true" in es_preflight["expected_success"]
    assert "runtime_probe_docker_requires_sudo=false" in es_preflight["expected_success"]
    assert "runtime_probe_elasticsearch_discovery_status=available" in es_preflight["expected_success"]
    assert "runtime_probe_elasticsearch_container_running=true" in es_preflight["expected_success"]
    assert "runtime_probe_elasticsearch_candidate_endpoint loopback" in es_preflight["expected_success"]
    assert "--expected-model-wire-api responses" in commands
    assert "--expected-model-provider-profile rawchat" in commands
    assert "--require-model-tool-loop" in commands
    assert "--require-project-agent-context" in commands
    assert "--require-agent-workflow-confirmation" in commands
    assert "--require-agent-workflow-resume" in commands
    assert "--require-agent-workflow-fingerprint-negative" in commands
    assert "--require-unknown-workflow-incubation" in commands
    assert "--require-runtime-toolchain" in commands
    assert "--require-real-evidence-ids" in commands
    assert "--require-completed-upload" in commands
    assert "--require-elasticsearch-hybrid-rag" in commands
    assert "--require-uploaded-series" in commands
    assert "--upload-nifti-file <remote_nifti_file>" in commands
    assert "--require-completed-task" in commands
    assert "--require-task-events" in commands
    assert "--require-observe-repair" in commands
    assert "--require-launched-task" in commands
    assert "--launch-series-id <uploaded_series_id>" not in commands
    assert "--launch-workflow-type <real_registered_workflow_type>" in commands
    assert "--wait-task-completion-timeout-seconds 21600" in commands
    assert "--wait-task-completion-poll-seconds 30" in commands
    assert "--expected-health-version <expected_health_version>" in commands
    assert "--require-container-native-qc" in commands
    assert "--require-scientific-report-artifacts" in commands
    assert "verify_remote_smoke_acceptance.py" in commands
    assert "<project_id>" in commands
    assert "<upload_session_id>" in commands
    assert "<completed_task_id>" not in commands
    assert "task_status_status=passed" in json.dumps(plan, sort_keys=True)
    assert "model_status.wire_api=responses" in json.dumps(plan, sort_keys=True)
    assert "model_status.trust_env_proxy=false" in json.dumps(plan, sort_keys=True)
    assert "model_status.deployment.model_gateway_access=direct" in json.dumps(plan, sort_keys=True)
    assert "checked.model_wire_api=responses" in json.dumps(plan, sort_keys=True)
    assert "checked.model_provider_profile=rawchat" in json.dumps(plan, sort_keys=True)
    assert "checked.model_trust_env_proxy=false" in json.dumps(plan, sort_keys=True)
    assert "checked.model_gateway_access=direct" in json.dumps(plan, sort_keys=True)
    assert "checked.model_tool_loop=true" in json.dumps(plan, sort_keys=True)
    assert "uploaded_series_status=passed" in json.dumps(plan, sort_keys=True)
    assert "launched_task_status=passed" in json.dumps(plan, sort_keys=True)
    assert "task_events_status=passed" in json.dumps(plan, sort_keys=True)
    assert "task_events_event_types includes task.remote_log" in json.dumps(plan, sort_keys=True)
    assert "task_events_remote_log_count>0" in json.dumps(plan, sort_keys=True)
    assert "observe_repair_status=passed" in json.dumps(plan, sort_keys=True)
    assert "observe_repair.policy=read_only_observe_repair" in json.dumps(plan, sort_keys=True)
    assert "observe_repair.auto_rerun_allowed=false" in json.dumps(plan, sort_keys=True)
    assert "observe_repair.task_creation_allowed=false" in json.dumps(plan, sort_keys=True)
    assert "observe_repair.forbidden_actions include auto_retry,auto_rerun,task_creation" in json.dumps(plan, sort_keys=True)
    assert "observe_repair.production_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "task_workflow_selection_status=passed" in json.dumps(plan, sort_keys=True)
    assert "launched_task.launch_source=agent_workflow_resume" in json.dumps(plan, sort_keys=True)
    assert "agent_project_context_status=passed" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_confirmation_status=passed" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_confirmation.workflow_metadata.workflow_type matches workflow_type" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_confirmation.workflow_metadata.agent_selectable=true" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_confirmation.workflow_metadata.is_report_only=false" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_resume_status=passed" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_fingerprint_negative_status=passed" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_fingerprint_negative.production_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "agent_workflow_fingerprint_negative.task_created=false" in json.dumps(plan, sort_keys=True)
    assert "unknown_workflow_incubation_status=passed" in json.dumps(plan, sort_keys=True)
    assert "unknown_workflow_incubation.action_lane=toolchain_incubation" in json.dumps(plan, sort_keys=True)
    assert "unknown_workflow_incubation.task_created=false" in json.dumps(plan, sort_keys=True)
    assert "unknown_workflow_incubation.task_creation_allowed=false" in json.dumps(plan, sort_keys=True)
    assert "unknown_workflow_incubation.forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch" in json.dumps(plan, sort_keys=True)
    assert "unknown_workflow_incubation.production_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "upload_inventory_completion_status=passed" in json.dumps(plan, sort_keys=True)
    assert "fast_launch_readiness_status=pre_acceptance" in json.dumps(plan, sort_keys=True)
    assert "fast_launch_readiness.checks.production_deployment.status=passed" in json.dumps(plan, sort_keys=True)
    assert "fast_launch_readiness.checks.production_deployment.required=true" in json.dumps(plan, sort_keys=True)
    assert "fast_launch_readiness.checks.production_deployment.ready=true" in json.dumps(plan, sort_keys=True)
    assert "fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid_status=passed" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.indexed_chunk_count matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.configured=true" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.index privacy-safe" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.index matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.mode=connected" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.indexed_chunk_count>0" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.dense_vector_dims>0" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.dense_vector_dims matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.lexical_retriever matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.vector_retriever matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.dense_vector_field matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.fusion matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.error absent" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.embedding_error absent" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.embedding_provider production configured" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.embedding_model present" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.embedding_transport production-safe" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.embedding_endpoint_configured boolean" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid.embedding_production_ready=true" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.embedding_provider matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.embedding_model matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.embedding_transport matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured matches status" in json.dumps(plan, sort_keys=True)
    assert "rag_rebuild_elasticsearch_hybrid.embedding_production_ready=true" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid_query_status=passed" in json.dumps(plan, sort_keys=True)
    assert "rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid" in json.dumps(plan, sort_keys=True)
    strict_smoke_expected = _step(plan, "run_strict_remote_smoke_acceptance")["expected_success"]
    assert "rag_elasticsearch_hybrid.error absent" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid.embedding_error absent" in strict_smoke_expected
    assert "rag_rebuild_elasticsearch_hybrid.error absent" in strict_smoke_expected
    assert "rag_rebuild_elasticsearch_hybrid.embedding_error absent" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_status=passed" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_source=docs/rag/contracts/elasticsearch-hybrid-search.md" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_index matches status" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_lexical_retriever=standard" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_vector_retriever=knn" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_dense_vector_field=embedding" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_fusion=rrf" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_dense_vector_dims matches status" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_embedding_model matches status" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_embedding_endpoint_configured matches status" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_embedding_production_ready matches status" in strict_smoke_expected
    assert "rag_elasticsearch_hybrid_query_embedding_production_ready=true" in strict_smoke_expected
    assert "fast_launch_readiness_status=pre_acceptance" in strict_smoke_expected
    assert "fast_launch_readiness.checks.production_deployment.status=passed" in strict_smoke_expected
    assert "fast_launch_readiness.checks.production_deployment.required=true" in strict_smoke_expected
    assert "fast_launch_readiness.checks.production_deployment.ready=true" in strict_smoke_expected
    assert "fast_launch_readiness.checks.rag_elasticsearch_hybrid.status=passed" in strict_smoke_expected
    assert "runtime_toolchain_status=passed" in strict_smoke_expected
    assert "runtime_toolchain.workflow_tool_execution=deployment_server_local" in strict_smoke_expected
    assert "runtime_toolchain.docker_runtime_host=api_server" in strict_smoke_expected
    assert "runtime_toolchain.required_workflow_available=true" in strict_smoke_expected
    assert "launched_task.launch_source=agent_workflow_resume" in strict_smoke_expected
    assert (
        "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type matches launched_task.runtime_workflow_type"
        in strict_smoke_expected
    )
    assert "agent_workflow_confirmation.workflow_metadata.agent_selectable=true" in strict_smoke_expected
    assert "launched_task.runtime_workflow_type present" in strict_smoke_expected
    assert "task_result_summary.workflow_metadata.workflow_type matches task workflow_type" in strict_smoke_expected
    assert (
        "task_result_summary.workflow_metadata.runtime_workflow_type matches task_status.runtime_workflow_type"
        in strict_smoke_expected
    )
    assert "task_result_summary.workflow_metadata.agent_selectable=true" in strict_smoke_expected
    assert "task_result_summary.workflow_metadata.is_report_only=false" in strict_smoke_expected
    assert "project_workflow_eligibility_metadata_status=passed" in strict_smoke_expected
    assert "project_workflow_eligibility_metadata_workflow_types include task workflow_type" in strict_smoke_expected
    assert "project_workflow_eligibility_metadata_item_count>0" in strict_smoke_expected
    assert "upload_inventory_workflow_eligibility_metadata_status=passed" in strict_smoke_expected
    assert "upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type" in strict_smoke_expected
    assert "upload_inventory_workflow_eligibility_metadata_item_count>0" in strict_smoke_expected
    assert "checked.task_status_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.runtime_toolchain_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.runtime_toolchain_workflow_tool_execution=deployment_server_local" in json.dumps(plan, sort_keys=True)
    assert "checked.runtime_toolchain_docker_runtime_host=api_server" in json.dumps(plan, sort_keys=True)
    assert "checked.runtime_toolchain_required_workflow_available=true" in json.dumps(plan, sort_keys=True)
    assert "checked.launched_task_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.launched_task_launch_source=agent_workflow_resume" in json.dumps(plan, sort_keys=True)
    assert (
        "checked.agent_workflow_confirmation_metadata_runtime_workflow_type matches launched_task_runtime_workflow_type"
        in json.dumps(plan, sort_keys=True)
    )
    assert "checked.agent_workflow_confirmation_metadata_agent_selectable=true" in json.dumps(plan, sort_keys=True)
    assert "checked.launched_task_runtime_workflow_type present" in json.dumps(plan, sort_keys=True)
    assert "checked.task_events_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.task_events_remote_log_count>0" in json.dumps(plan, sort_keys=True)
    assert "checked.observe_repair_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.observe_repair_policy=read_only_observe_repair" in json.dumps(plan, sort_keys=True)
    assert "checked.observe_repair_auto_rerun_allowed=false" in json.dumps(plan, sort_keys=True)
    assert "checked.observe_repair_task_creation_allowed=false" in json.dumps(plan, sort_keys=True)
    assert "checked.observe_repair_forbidden_actions include auto_retry,auto_rerun,task_creation" in json.dumps(plan, sort_keys=True)
    assert "checked.observe_repair_production_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "checked.task_workflow_selection_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.task_result_summary_metadata_workflow_type matches task workflow_type" in json.dumps(plan, sort_keys=True)
    assert (
        "checked.task_result_summary_metadata_runtime_workflow_type matches task_status_runtime_workflow_type"
        in json.dumps(plan, sort_keys=True)
    )
    assert "checked.task_result_summary_metadata_agent_selectable=true" in json.dumps(plan, sort_keys=True)
    assert "checked.task_result_summary_metadata_is_report_only=false" in json.dumps(plan, sort_keys=True)
    assert "checked.project_workflow_eligibility_metadata_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.project_workflow_eligibility_metadata_item_count>0" in json.dumps(plan, sort_keys=True)
    assert "checked.project_workflow_eligibility_metadata_task_workflow_type_included=true" in json.dumps(
        plan, sort_keys=True
    )
    assert "checked.upload_inventory_workflow_eligibility_metadata_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.upload_inventory_workflow_eligibility_metadata_item_count>0" in json.dumps(plan, sort_keys=True)
    assert "checked.upload_inventory_workflow_eligibility_metadata_task_workflow_type_included=true" in json.dumps(
        plan, sort_keys=True
    )
    assert "checked.agent_project_context_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.fast_launch_readiness_status=pre_acceptance" in json.dumps(plan, sort_keys=True)
    assert "checked.fast_launch_production_deployment_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.fast_launch_production_deployment_required=true" in json.dumps(plan, sort_keys=True)
    assert "checked.fast_launch_production_deployment_ready=true" in json.dumps(plan, sort_keys=True)
    assert "checked.fast_launch_rag_elasticsearch_hybrid_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_confirmation_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_confirmation_metadata_workflow_type matches task workflow_type" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_confirmation_metadata_is_report_only=false" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_resume_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_fingerprint_negative_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch" in json.dumps(plan, sort_keys=True)
    assert "checked.agent_workflow_fingerprint_negative_production_task_created=false" in json.dumps(
        plan, sort_keys=True
    )
    assert "checked.agent_workflow_fingerprint_negative_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "checked.unknown_workflow_incubation_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.unknown_workflow_incubation_action_lane=toolchain_incubation" in json.dumps(plan, sort_keys=True)
    assert "checked.unknown_workflow_incubation_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "checked.unknown_workflow_incubation_task_creation_allowed=false" in json.dumps(plan, sort_keys=True)
    assert "checked.unknown_workflow_incubation_forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch" in json.dumps(plan, sort_keys=True)
    assert "checked.unknown_workflow_incubation_production_task_created=false" in json.dumps(plan, sort_keys=True)
    assert "checked.upload_inventory_completion_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_mode=connected" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_configured=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_index privacy-safe" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_index matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_indexed_chunk_count>0" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_indexed_chunk_count matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_dense_vector_dims>0" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_dense_vector_dims matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_lexical_retriever matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_vector_retriever matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_dense_vector_field matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_fusion matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_error_absent=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_embedding_error_absent=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_error_absent=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_embedding_error_absent=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_embedding_provider production configured" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_embedding_model present" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_embedding_transport production-safe" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_embedding_endpoint_configured boolean" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_official_rrf_source_present=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_embedding_production_ready=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_embedding_provider matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_embedding_model matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_embedding_transport matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_embedding_endpoint_configured matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_rebuild_elasticsearch_hybrid_embedding_production_ready=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_status=passed" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_mode=elasticsearch_hybrid" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_retrieval_source=elasticsearch_hybrid" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_source=docs/rag/contracts/elasticsearch-hybrid-search.md" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_index matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_lexical_retriever=standard" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_vector_retriever=knn" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_dense_vector_field=embedding" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_fusion=rrf" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_dense_vector_dims matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_embedding_model matches status" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_embedding_endpoint_configured matches status" in json.dumps(
        plan, sort_keys=True
    )
    assert "checked.rag_elasticsearch_hybrid_query_embedding_endpoint_configured=true" in json.dumps(plan, sort_keys=True)
    assert "checked.rag_elasticsearch_hybrid_query_embedding_production_ready matches status" in json.dumps(
        plan, sort_keys=True
    )
    assert "checked.rag_elasticsearch_hybrid_query_embedding_production_ready=true" in json.dumps(plan, sort_keys=True)


def test_remote_release_gate_command_plan_does_not_apply_expired_approval_json():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["status"] = "operator_authorization_required"
    plan["approval_json"] = EXPIRED_APPROVAL_JSON
    plan.pop("approval_json_state", None)
    for step in plan["steps"]:
        step["command"] = step["command"].replace(FRESH_APPROVAL_JSON, EXPIRED_APPROVAL_JSON)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "approval_json_state must describe the approval JSON state" in str(exc.value)


def test_remote_release_gate_command_plan_accepts_fresh_reviewed_approval_after_refresh():
    verifier = load_verifier()
    plan = _operator_authorization_plan()

    report = verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")

    assert report["status"] == "passed"
    assert report["checked"]["approval_json_status"] == "fresh_reviewed"
    assert report["checked"]["approval_json"] == REVIEWED_APPROVAL_JSON
    assert report["checked"]["approval_expires_at_utc"] == "2026-06-17T01:00:00+00:00"


def test_remote_release_gate_command_plan_rejects_operator_authorization_with_placeholders():
    verifier = load_verifier()
    plan = _operator_authorization_plan()
    step = _step(plan, "run_strict_remote_smoke_acceptance")
    step["command"] = step["command"].replace("codex-gate-verifiers-efca895b", "<accepted_release_or_commit>", 1)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")

    assert "operator_authorization_required commands must be materialized without placeholders" in str(exc.value)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "https://console.example.com",
            "https://10.2.32.14",
            "apply_production_readiness_env.command must include a concrete public HTTPS console origin",
        ),
        (
            "https://api.example.com",
            "https://api",
            "apply_production_readiness_env.command must include a concrete public HTTPS API origin",
        ),
    ],
)
def test_remote_release_gate_materialized_plan_rejects_non_public_production_origins(old, new, message):
    verifier = load_verifier()
    plan = _operator_authorization_plan()
    for step in plan["steps"]:
        step["command"] = step["command"].replace(old, new)
        step["expected_success"] = [item.replace(old, new) for item in step["expected_success"]]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")

    assert message in str(exc.value)


def test_remote_release_gate_final_readiness_requires_production_deployment_required_and_ready():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step = _step(plan, "verify_final_fast_launch_readiness")
    step["expected_success"] = [
        item
        for item in step["expected_success"]
        if item
        not in {
            "fast_launch_readiness.checks.production_deployment.required=true",
            "fast_launch_readiness.checks.production_deployment.ready=true",
        }
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert (
        "verify_final_fast_launch_readiness.expected_success must include "
        "fast_launch_readiness.checks.production_deployment.required=true"
    ) in str(exc.value)


def test_remote_release_gate_command_plan_rejects_operator_authorization_with_refresh_template():
    verifier = load_verifier()
    plan = _operator_authorization_plan()
    source_plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["stale_task_approval_refresh"] = source_plan["stale_task_approval_refresh"]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00Z")

    assert "stale_task_approval_refresh must be superseded by fresh reviewed approval" in str(exc.value)


def test_remote_release_gate_command_plan_rejects_expired_reviewed_approval_after_refresh():
    verifier = load_verifier()
    plan = _operator_authorization_plan()

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan, now_utc="2026-06-17T02:00:00Z")

    assert "approval_json_state.approval_expires_at_utc is older than now_utc" in str(exc.value)


def test_remote_release_gate_command_plan_declares_frontend_blocking_invariants():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    assert plan["frontend_gate"] == {
        "status_until_all_steps_pass": "blocked",
        "required_final_evidence": "fresh_strict_remote_smoke_acceptance_verified_within_24h",
    }
    assert plan["privacy_and_safety_invariants"] == [
        "do_not_store_or_print_api_keys_or_secrets",
        "do_not_store_raw_patient_data",
        "do_not_store_backend_absolute_paths_in_acceptance_json",
        "do_not_use_IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
        "do_not_count_skipped_missing_model_config_as_passed",
    ]


def test_remote_release_gate_command_plan_includes_approval_refresh_path():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    refresh = plan["stale_task_approval_refresh"]

    assert refresh["required_when"] == "approval_json_missing_or_older_than_24h"
    assert refresh["must_be_operator_reviewed_before_apply"] is True
    assert refresh["mutates_remote_state"] is False
    assert refresh["output_json_pattern"] == "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json"

    command = refresh["command"]
    assert "reconcile_stale_tasks.py --max-age-hours 24 --check-containers" in command
    assert "--task-id 83 --task-id 84" in command
    assert "--apply" not in command
    assert "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1" not in command
    assert refresh["materialize_plan_command"] == (
        "cd /home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z && "
        "PYTHONPATH=apps/api /home/yyf/project/image_agent/apps/api/.venv/bin/python "
        "apps/api/scripts/build_release_gate_command_plan.py docs/deployment/remote-release-gate-command-plan.json "
        "/tmp/image_agent_stale_tasks_83_84_dry_run_<timestamp>.json --task-id 83 --task-id 84 "
        "--max-age-hours 24 --deployment-id <accepted_release_or_commit> "
            "--expected-health-version <expected_health_version> --remote-nifti-file <remote_nifti_file> "
            "--workflow-type <real_registered_workflow_type> --project-id <project_id> "
            "--upload-session-id <upload_session_id> --evidence-timestamp <timestamp> "
            "--deployment-scope public_internet "
            "--production-cors-origins <https_console_origin> "
            "--production-public-base-url <https_api_origin> "
            "--output-json /tmp/image_agent_remote_release_gate_plan_<timestamp>.json"
        )
    assert refresh["production_origin_materialization"] == {
        "required_arguments": [
            "--deployment-scope public_internet",
            "--production-cors-origins <https_console_origin>",
            "--production-public-base-url <https_api_origin>",
        ],
        "boundary": (
            "Use public_internet for real public HTTPS origins without path, query, or fragment, or replace "
            "with private_network plus explicit loopback/private HTTP(S) origins for private usable deployment; "
            "do not use placeholders, 0.0.0.0, bare host names, wildcard CORS values, paths, query, or fragments."
        ),
    }
    assert refresh["existing_uploaded_series_materialization"] == {
        "replace": "--remote-nifti-file <remote_nifti_file>",
        "with": "--uploaded-series-id <uploaded_series_id>",
        "boundary": "Use only for a completed upload session whose series belongs to the same project and remains privacy-safe in saved evidence.",
    }
    assert refresh["next_steps_after_refresh"] == [
        "operator reviews refreshed dry-run JSON and approval_fingerprint",
        "run build_release_gate_command_plan.py to materialize an operator_authorization_required plan",
        "verify the materialized plan with verify_release_gate_command_plan.py before apply",
    ]


def test_remote_release_gate_command_plan_rejects_missing_production_origin_materialization():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["stale_task_approval_refresh"].pop("production_origin_materialization", None)

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "stale_task_approval_refresh.production_origin_materialization mismatch" in str(exc.value)


def test_remote_release_gate_reconcile_commands_load_remote_env_for_docker_checks():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    env_prefix = "set -a; . /home/yyf/project/image_agent/.env; set +a;"
    live_root = "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent"

    refresh_command = plan["stale_task_approval_refresh"]["command"]
    assert env_prefix in refresh_command
    assert live_root in refresh_command

    commands_by_step = {step["id"]: step["command"] for step in plan["steps"]}
    for step_id in (
        "apply_approved_stale_task_resolution",
        "collect_post_apply_clean_dry_run",
    ):
        assert env_prefix in commands_by_step[step_id]
        assert live_root in commands_by_step[step_id]


def test_remote_release_gate_rejects_es_runtime_probe_without_deployment_env():
    verifier = load_verifier()
    plan = _operator_authorization_plan()
    step = _step(plan, "verify_elasticsearch_hybrid_prerequisites")
    step["command"] = step["command"].replace(
        "set -a; . /home/yyf/project/image_agent/.env; set +a; ",
        "",
    )
    step["command"] = step["command"].replace(
        "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent IMAGE_AGENT_ENV_FILE=/home/yyf/project/image_agent/.env ",
        "",
    )

    with pytest.raises(SystemExit, match="ES prerequisite runtime probe must load deployment env"):
        verifier.verify_plan(plan, now_utc="2026-06-16T02:00:00+00:00")


def test_remote_release_gate_command_plan_requires_single_strict_smoke_json_path():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    for step in plan["steps"]:
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["command"] = step["command"].replace(
                "/tmp/image_agent_remote_smoke_acceptance_<timestamp>.json",
                "/tmp/other_remote_smoke_acceptance_<timestamp>.json",
            )
            break

    try:
        verifier.verify_plan(plan)
    except SystemExit as exc:
        assert "strict smoke verifier command must verify the smoke output JSON" in str(exc)
    else:
        raise AssertionError("verify_plan should reject mismatched strict smoke JSON paths")


def test_remote_release_gate_command_plan_requires_fast_launch_env_export_after_strict_verify():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["steps"] = [
        step for step in plan["steps"] if step["id"] != "emit_fast_launch_acceptance_env_after_strict_verify"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected release gate sequence" in str(exc.value)


def test_remote_release_gate_command_plan_requires_elasticsearch_hybrid_prerequisite_step():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    plan["steps"] = [
        step for step in plan["steps"] if step["id"] != "verify_elasticsearch_hybrid_prerequisites"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected release gate sequence" in str(exc.value)


@pytest.mark.parametrize(
    "missing_file",
    [
        "apps/api/scripts/build_elasticsearch_hybrid_config_plan.py",
        "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py",
        "apps/api/scripts/setup_elasticsearch_hybrid_rag.py",
        "apps/api/scripts/setup_local_embedding_service.py",
        "docs/deployment/remote-elasticsearch-hybrid-config-plan.json",
    ],
)
def test_remote_release_gate_command_plan_requires_elasticsearch_config_handoff_in_overlay(missing_file):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "verify_release_overlay_contents":
            step["command"] = step["command"].replace(f" && test -f {missing_file}", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_file in str(exc.value)


def test_remote_release_gate_command_plan_requires_es_config_plan_verification_in_overlay_gate():
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    step = _step(plan, "verify_release_overlay_contents")
    step["command"] = step["command"].replace(
        " && PYTHONPATH=apps/api /home/yyf/project/image_agent/apps/api/.venv/bin/python "
        "apps/api/scripts/verify_elasticsearch_hybrid_config_plan.py "
        "docs/deployment/remote-elasticsearch-hybrid-config-plan.json",
        "",
    )
    step["expected_success"] = [
        item for item in step["expected_success"] if item != "elasticsearch_hybrid_config_plan_status=passed"
    ]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "verify_elasticsearch_hybrid_config_plan.py" in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "rag_status_hybrid_lexical_retriever=standard",
        "rag_status_hybrid_vector_retriever=knn",
        "rag_status_hybrid_dense_vector_field=embedding",
        "rag_status_hybrid_official_rrf_source_present=true",
        "runtime_probe_machine_binding=runtime_discovered",
        "runtime_probe_workflow_tool_execution=deployment_server_local",
        "runtime_probe_docker_runtime_host=api_server",
        "runtime_probe_docker_accessible=true",
        "runtime_probe_docker_requires_sudo=false",
        "runtime_probe_elasticsearch_discovery_status=available",
        "runtime_probe_elasticsearch_container_running=true",
        "runtime_probe_elasticsearch_candidate_endpoint loopback",
    ],
)
def test_remote_release_gate_command_plan_requires_elasticsearch_hybrid_prerequisite_components(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "verify_elasticsearch_hybrid_prerequisites":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "rag_elasticsearch_hybrid.embedding_transport production-safe",
        "rag_elasticsearch_hybrid.embedding_endpoint_configured boolean",
        "rag_elasticsearch_hybrid.official_rrf_source_present=true",
        "rag_rebuild_elasticsearch_hybrid.embedding_transport matches status",
        "rag_rebuild_elasticsearch_hybrid.embedding_endpoint_configured matches status",
        "checked.rag_elasticsearch_hybrid_embedding_transport production-safe",
        "checked.rag_elasticsearch_hybrid_embedding_endpoint_configured boolean",
        "checked.rag_elasticsearch_hybrid_official_rrf_source_present=true",
        "checked.rag_rebuild_elasticsearch_hybrid_embedding_transport matches status",
        "checked.rag_rebuild_elasticsearch_hybrid_embedding_endpoint_configured matches status",
    ],
)
def test_remote_release_gate_command_plan_requires_elasticsearch_hybrid_transport_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
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
    ],
)
def test_remote_release_gate_command_plan_requires_elasticsearch_hybrid_query_evidence_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "launched_task.launch_source=agent_workflow_resume",
        "checked.launched_task_launch_source=agent_workflow_resume",
    ],
)
def test_remote_release_gate_command_plan_requires_agent_resume_launch_source_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "agent_workflow_confirmation.workflow_metadata.runtime_workflow_type matches launched_task.runtime_workflow_type",
        "launched_task.runtime_workflow_type present",
        "agent_workflow_resume.runtime_workflow_type matches launched_task.runtime_workflow_type",
        "task_status.runtime_workflow_type matches launched_task.runtime_workflow_type",
        "checked.agent_workflow_confirmation_metadata_runtime_workflow_type matches launched_task_runtime_workflow_type",
        "checked.launched_task_runtime_workflow_type present",
        "checked.agent_workflow_resume_runtime_workflow_type matches launched_task_runtime_workflow_type",
        "checked.task_status_runtime_workflow_type matches launched_task_runtime_workflow_type",
    ],
)
def test_remote_release_gate_command_plan_requires_runtime_workflow_alias_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "project_workflow_eligibility_metadata_status=passed",
        "project_workflow_eligibility_metadata_workflow_types include task workflow_type",
        "project_workflow_eligibility_metadata_item_count>0",
        "upload_inventory_workflow_eligibility_metadata_status=passed",
        "upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
        "upload_inventory_workflow_eligibility_metadata_item_count>0",
        "checked.project_workflow_eligibility_metadata_status=passed",
        "checked.project_workflow_eligibility_metadata_workflow_types include task workflow_type",
        "checked.project_workflow_eligibility_metadata_task_workflow_type_included=true",
        "checked.project_workflow_eligibility_metadata_item_count>0",
        "checked.upload_inventory_workflow_eligibility_metadata_status=passed",
        "checked.upload_inventory_workflow_eligibility_metadata_workflow_types include task workflow_type",
        "checked.upload_inventory_workflow_eligibility_metadata_task_workflow_type_included=true",
        "checked.upload_inventory_workflow_eligibility_metadata_item_count>0",
    ],
)
def test_remote_release_gate_command_plan_requires_workflow_eligibility_metadata_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "agent_workflow_fingerprint_negative_status=passed",
        "agent_workflow_fingerprint_negative.confirmation_gate=fingerprint_mismatch",
        "agent_workflow_fingerprint_negative.production_task_created=false",
        "agent_workflow_fingerprint_negative.task_created=false",
        "checked.agent_workflow_fingerprint_negative_status=passed",
        "checked.agent_workflow_fingerprint_negative_confirmation_gate=fingerprint_mismatch",
        "checked.agent_workflow_fingerprint_negative_production_task_created=false",
        "checked.agent_workflow_fingerprint_negative_task_created=false",
    ],
)
def test_remote_release_gate_command_plan_requires_fingerprint_negative_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "unknown_workflow_incubation_status=passed",
        "unknown_workflow_incubation.action_lane=toolchain_incubation",
        "unknown_workflow_incubation.task_created=false",
        "unknown_workflow_incubation.confirmation_created=false",
        "unknown_workflow_incubation.task_creation_allowed=false",
        "unknown_workflow_incubation.forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch",
        "unknown_workflow_incubation.production_task_created=false",
        "unknown_workflow_incubation.proposal_production_task_created=false",
        "checked.unknown_workflow_incubation_status=passed",
        "checked.unknown_workflow_incubation_action_lane=toolchain_incubation",
        "checked.unknown_workflow_incubation_task_created=false",
        "checked.unknown_workflow_incubation_confirmation_created=false",
        "checked.unknown_workflow_incubation_task_creation_allowed=false",
        "checked.unknown_workflow_incubation_forbidden_actions include confirmation_creation,production_task_creation,pipeline_runner_launch",
        "checked.unknown_workflow_incubation_production_task_created=false",
        "checked.unknown_workflow_incubation_proposal_production_task_created=false",
    ],
)
def test_remote_release_gate_command_plan_requires_unknown_workflow_incubation_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "observe_repair_status=passed",
        "observe_repair.policy=read_only_observe_repair",
        "observe_repair.auto_rerun_allowed=false",
        "observe_repair.task_creation_allowed=false",
        "observe_repair.forbidden_actions include auto_retry,auto_rerun,task_creation",
        "observe_repair.production_task_created=false",
        "observe_repair.requires_preflight_before_retry=true",
        "observe_repair.requires_human_confirmation_before_retry=true",
        "checked.observe_repair_status=passed",
        "checked.observe_repair_policy=read_only_observe_repair",
        "checked.observe_repair_auto_rerun_allowed=false",
        "checked.observe_repair_task_creation_allowed=false",
        "checked.observe_repair_forbidden_actions include auto_retry,auto_rerun,task_creation",
        "checked.observe_repair_production_task_created=false",
        "checked.observe_repair_requires_preflight_before_retry=true",
        "checked.observe_repair_requires_human_confirmation_before_retry=true",
    ],
)
def test_remote_release_gate_command_plan_requires_observe_repair_expected_success(missing_item):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]
        if step["id"] == "verify_strict_remote_smoke_acceptance_json":
            step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


@pytest.mark.parametrize(
    "required_flag",
    [
        "--require-project-agent-context",
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
        "--require-elasticsearch-hybrid-rag",
        "--require-completed-upload",
        "--require-completed-task",
        "--require-task-events",
        "--require-observe-repair",
    ],
)
def test_remote_release_gate_command_plan_requires_full_strict_smoke_flags(required_flag):
    verifier = load_verifier()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    for step in plan["steps"]:
        if step["id"] == "run_strict_remote_smoke_acceptance":
            step["command"] = step["command"].replace(f" {required_flag}", "")
            break

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert f"run_strict_remote_smoke_acceptance.command must include {required_flag}" in str(exc.value)
