import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "build_elasticsearch_hybrid_config_plan.py"
CURRENT_RELEASE_OVERLAY = "/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_elasticsearch_hybrid_config_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _step(plan: dict, step_id: str) -> dict:
    matches = [step for step in plan["steps"] if step["id"] == step_id]
    assert len(matches) == 1
    return matches[0]


def test_build_elasticsearch_hybrid_config_plan_is_secret_safe_and_ordered():
    builder = _load_builder()

    plan = builder.build_elasticsearch_hybrid_config_plan(
        release_overlay=CURRENT_RELEASE_OVERLAY,
        missing_env_keys=[
            "IMAGE_AGENT_ELASTICSEARCH_URL",
            "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER",
            "IMAGE_AGENT_RAG_EMBEDDING_MODEL",
            "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL",
        ],
    )

    assert plan["plan_id"] == "remote_elasticsearch_hybrid_config_plan_v1"
    assert plan["status"] == "operator_configuration_required"
    assert plan["release_overlay"] == CURRENT_RELEASE_OVERLAY
    assert plan["remote_host"] == "yyf@10.2.32.14"
    assert plan["remote_env_file"] == "/home/yyf/project/image_agent/.env"
    assert plan["observed_blockers"] == [
        "remote_port_9200_not_listening",
        "docker_socket_requires_operator_or_sudo",
        "live_rag_engine_not_elasticsearch_hybrid",
        "missing_required_elasticsearch_or_embedding_env",
    ]
    assert plan["missing_env_keys"] == [
        "IMAGE_AGENT_ELASTICSEARCH_URL",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL",
    ]
    assert [step["id"] for step in plan["steps"]] == [
        "inspect_local_elasticsearch_runtime",
        "setup_local_embedding_service_from_git_script",
        "setup_elasticsearch_hybrid_rag_from_git_script",
        "verify_secret_env_presence_without_values",
        "restart_api_from_release_overlay",
        "operator_prepare_fixed_workflow_images_if_missing",
        "rebuild_elasticsearch_hybrid_rag",
        "verify_elasticsearch_hybrid_prerequisites",
        "continue_release_gate_strict_smoke",
    ]
    assert plan["official_runtime_sources"] == [
        "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker",
        "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic",
        "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod",
        "https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-license-post-start-trial",
        "https://huggingface.co/docs/text-embeddings-inference/en/quick_tour",
        "https://huggingface.co/docs/text-embeddings-inference/en/basic_tutorials/using_cli",
    ]
    assert plan["env_template"] == [
        "IMAGE_AGENT_ELASTICSEARCH_URL=<operator-managed-elasticsearch-url>",
        "IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z",
        "IMAGE_AGENT_ELASTICSEARCH_API_KEY=<optional-operator-managed-secret>",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL=<operator-approved-embedding-model>",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=<operator-managed-openai-compatible-embedding-endpoint>",
        "IMAGE_AGENT_RAG_EMBEDDING_API_KEY=<operator-managed-secret-or-reused-model-key>",
    ]
    serialized = json.dumps(plan, sort_keys=True)
    assert "sk-" not in serialized
    assert "rawchat.cn/codex" not in serialized
    assert "OPENAI_API_KEY=" not in serialized
    assert "IMAGE_AGENT_RAG_EMBEDDING_API_KEY=<operator-managed-secret-or-reused-model-key>" in serialized
    assert _step(plan, "inspect_local_elasticsearch_runtime")["requires_operator_authorization"] is False
    assert _step(plan, "inspect_local_elasticsearch_runtime")["mutates_remote_state"] is False
    assert "app.scripts.probe_runtime_environment --json" in _step(
        plan, "inspect_local_elasticsearch_runtime"
    )["command"]
    assert "python3 - <<" not in _step(plan, "inspect_local_elasticsearch_runtime")["command"]
    assert "open(" not in _step(plan, "inspect_local_elasticsearch_runtime")["command"]
    assert "open('/tmp" not in _step(plan, "inspect_local_elasticsearch_runtime")["command"]
    assert "print('" not in _step(plan, "inspect_local_elasticsearch_runtime")["command"]
    assert "elasticsearch.runtime_discovery_present=true" in _step(
        plan, "inspect_local_elasticsearch_runtime"
    )["expected_success"]
    assert "operator_configure_elasticsearch_service" not in [step["id"] for step in plan["steps"]]
    assert "operator_provision_local_elasticsearch_container_if_missing" not in [step["id"] for step in plan["steps"]]
    assert "operator_apply_secret_env" not in [step["id"] for step in plan["steps"]]
    embedding_step = _step(plan, "setup_local_embedding_service_from_git_script")
    assert embedding_step["requires_operator_authorization"] is True
    assert embedding_step["mutates_remote_state"] is True
    assert "scripts/setup_local_embedding_service.py" in embedding_step["command"]
    assert "--apply" in embedding_step["command"]
    assert "--embedding-image ghcr.io/huggingface/text-embeddings-inference:cpu-1.9" in embedding_step["command"]
    assert "--network-mode host" in embedding_step["command"]
    assert "--model-id sentence-transformers/all-MiniLM-L6-v2" in embedding_step["command"]
    assert "--served-model-name image-agent-minilm-l6-v2" in embedding_step["command"]
    assert "--embedding-base-url http://127.0.0.1:18081/v1" in embedding_step["command"]
    assert ":latest" not in embedding_step["command"]
    assert "local_embedding_service_setup_v1" in embedding_step["expected_success"]
    assert "embedding_model_id=sentence-transformers/all-MiniLM-L6-v2" in embedding_step["expected_success"]
    assert "embedding_served_model=image-agent-minilm-l6-v2" in embedding_step["expected_success"]
    assert "embedding_network_mode=host" in embedding_step["expected_success"]
    assert "embedding_endpoint_bound_to_loopback=true" in embedding_step["expected_success"]
    assert "embedding_endpoint_bound_to_loopback" in embedding_step["command"]
    assert "embedding_endpoint_probe_passed" in embedding_step["command"]
    assert "no_latest_tags" in embedding_step["command"]
    assert "env_key_status" in embedding_step["command"]
    assert "secret_values_not_logged" in embedding_step["command"]
    assert "secret_values_not_printed" in embedding_step["command"]
    for expected in embedding_step["expected_success"]:
        assert f"echo {expected}" in embedding_step["command"]
    setup_step = _step(plan, "setup_elasticsearch_hybrid_rag_from_git_script")
    assert setup_step["requires_operator_authorization"] is True
    assert setup_step["mutates_remote_state"] is True
    assert "scripts/setup_elasticsearch_hybrid_rag.py" in setup_step["command"]
    assert "--apply" in setup_step["command"]
    assert "--rebuild-rag" not in setup_step["command"]
    assert "--verify-prerequisites" not in setup_step["command"]
    assert "--index-name image_agent_rag_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z" in setup_step["command"]
    assert "--embedding-provider openai_compatible" in setup_step["command"]
    assert "--derive-embedding-from-env" in setup_step["command"]
    assert "--embedding-model \"$IMAGE_AGENT_RAG_EMBEDDING_MODEL\"" not in setup_step["command"]
    assert "--embedding-base-url \"$IMAGE_AGENT_RAG_EMBEDDING_BASE_URL\"" not in setup_step["command"]
    assert "--embedding-api-key-env IMAGE_AGENT_RAG_EMBEDDING_API_KEY" in setup_step["command"]
    assert "docker.elastic.co/elasticsearch/elasticsearch:9.4.2" in json.dumps(setup_step["expected_success"])
    assert ":latest" not in setup_step["command"]
    assert "elasticsearch_hybrid_rag_setup_v1" in setup_step["expected_success"]
    assert "start_elasticsearch_trial_license" in setup_step["command"]
    assert "elastic_endpoint_bound_to_loopback" in setup_step["command"]
    assert "no_latest_tags" in setup_step["command"]
    assert "env_key_status" in setup_step["command"]
    assert "secret_values_not_logged" in setup_step["command"]
    assert "secret_values_not_printed" in setup_step["command"]
    assert "elasticsearch_trial_license_status=started_or_already_started" in setup_step["expected_success"]
    assert "secret_values_not_printed=true" in setup_step["expected_success"]
    for expected in setup_step["expected_success"]:
        assert f"echo {expected}" in setup_step["command"]
    assert _step(plan, "verify_secret_env_presence_without_values")["requires_operator_authorization"] is False
    assert _step(plan, "verify_secret_env_presence_without_values")["mutates_remote_state"] is False
    assert "print(f'{key}=' + ('set' if seen.get(key) else 'missing'))" in _step(
        plan, "verify_secret_env_presence_without_values"
    )["command"]
    assert "secret_values_not_printed=true" in _step(
        plan, "verify_secret_env_presence_without_values"
    )["command"]
    prepare_images_step = _step(plan, "operator_prepare_fixed_workflow_images_if_missing")
    assert prepare_images_step["requires_operator_authorization"] is True
    assert prepare_images_step["mutates_remote_state"] is True
    assert "--prepare-missing-images" in prepare_images_step["command"]
    assert "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES" in prepare_images_step["command"]
    assert "workflow_images_prepare_attempted_evidence=true" in prepare_images_step["expected_success"]
    assert "runtime_preparation" in prepare_images_step["command"]
    assert "verify_elasticsearch_hybrid_prerequisites.py" in _step(
        plan, "verify_elasticsearch_hybrid_prerequisites"
    )["command"]
    assert "--rag-status-url http://127.0.0.1:8000/agent/rag/status" in _step(
        plan, "verify_elasticsearch_hybrid_prerequisites"
    )["command"]
    assert (
        "--runtime-probe-json /tmp/image_agent_runtime_probe_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json"
        in _step(plan, "verify_elasticsearch_hybrid_prerequisites")["command"]
    )
    assert "mode=connected" in _step(plan, "verify_elasticsearch_hybrid_prerequisites")["expected_success"]
    assert "embedding_production_ready=true" in _step(
        plan, "verify_elasticsearch_hybrid_prerequisites"
    )["expected_success"]
    assert "runtime_probe_machine_binding=runtime_discovered" in _step(
        plan, "verify_elasticsearch_hybrid_prerequisites"
    )["expected_success"]
    assert "runtime_probe_elasticsearch_container_running=true" in _step(
        plan, "verify_elasticsearch_hybrid_prerequisites"
    )["expected_success"]
    rebuild_step = _step(plan, "rebuild_elasticsearch_hybrid_rag")
    for expected in rebuild_step["expected_success"]:
        assert f'print("{expected}")' in rebuild_step["command"]
    assert "raise SystemExit" in rebuild_step["command"]
    assert _step(plan, "continue_release_gate_strict_smoke")["mutates_remote_state"] is False
    assert _step(plan, "continue_release_gate_strict_smoke")["requires_operator_authorization"] is False
    continue_command = _step(plan, "continue_release_gate_strict_smoke")["command"]
    assert f"cd {CURRENT_RELEASE_OVERLAY} &&" in continue_command
    assert "apps/api/scripts/verify_release_gate_command_plan.py" in continue_command
    assert "docs/deployment/remote-release-gate-command-plan.json" in continue_command
    for expected in _step(plan, "continue_release_gate_strict_smoke")["expected_success"]:
        assert f"echo {expected}" in continue_command


def test_build_elasticsearch_hybrid_config_plan_rejects_unsafe_release_overlay():
    builder = _load_builder()

    with pytest.raises(SystemExit) as exc:
        builder.build_elasticsearch_hybrid_config_plan(
            release_overlay="/home/yyf/project/image_agent",
            missing_env_keys=[],
        )

    assert "release_overlay must be a release path under /home/yyf/project/image_agent_releases" in str(exc.value)


def test_build_elasticsearch_hybrid_config_plan_cli_writes_json(tmp_path, capsys):
    builder = _load_builder()
    output_json = tmp_path / "es-config-plan.json"

    builder.main(
        [
            "--release-overlay",
            CURRENT_RELEASE_OVERLAY,
            "--missing-env-key",
            "IMAGE_AGENT_ELASTICSEARCH_URL",
            "--output-json",
            str(output_json),
        ]
    )

    stdout_plan = json.loads(capsys.readouterr().out)
    saved_plan = json.loads(output_json.read_text(encoding="utf-8"))
    assert stdout_plan == saved_plan
    assert saved_plan["steps"][0]["id"] == "inspect_local_elasticsearch_runtime"
