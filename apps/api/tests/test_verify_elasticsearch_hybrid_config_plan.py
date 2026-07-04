import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN_PATH = REPO_ROOT / "docs" / "deployment" / "remote-elasticsearch-hybrid-config-plan.json"
SCRIPT_PATH = REPO_ROOT / "apps" / "api" / "scripts" / "verify_elasticsearch_hybrid_config_plan.py"
CURRENT_RELEASE_OVERLAY = "/home/yyf/project/image_agent_releases/codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_elasticsearch_hybrid_config_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _step(plan: dict, step_id: str) -> dict:
    matches = [step for step in plan["steps"] if step["id"] == step_id]
    assert len(matches) == 1
    return matches[0]


def test_elasticsearch_hybrid_config_plan_is_machine_checkable():
    verifier = _load_verifier()
    report = verifier.verify_plan(_plan())

    assert report["status"] == "passed"
    assert report["checked"] == {
        "plan_id": "remote_elasticsearch_hybrid_config_plan_v1",
            "step_count": 9,
        "release_overlay": CURRENT_RELEASE_OVERLAY,
        "remote_env_file": "/home/yyf/project/image_agent/.env",
        "operator_authorization_required_steps": [
            "setup_local_embedding_service_from_git_script",
            "setup_elasticsearch_hybrid_rag_from_git_script",
            "restart_api_from_release_overlay",
            "operator_prepare_fixed_workflow_images_if_missing",
            "rebuild_elasticsearch_hybrid_rag",
        ],
        "mutating_steps": [
            "setup_local_embedding_service_from_git_script",
            "setup_elasticsearch_hybrid_rag_from_git_script",
            "restart_api_from_release_overlay",
            "operator_prepare_fixed_workflow_images_if_missing",
            "rebuild_elasticsearch_hybrid_rag",
        ],
        "missing_env_keys": [
            "IMAGE_AGENT_ELASTICSEARCH_URL",
            "IMAGE_AGENT_ELASTICSEARCH_INDEX",
            "IMAGE_AGENT_ELASTICSEARCH_API_KEY",
            "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER",
            "IMAGE_AGENT_RAG_EMBEDDING_MODEL",
            "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL",
            "IMAGE_AGENT_RAG_EMBEDDING_API_KEY",
        ],
    }


def test_elasticsearch_hybrid_config_plan_orders_config_before_restart_rebuild_and_gate():
    plan = _plan()
    step_ids = [step["id"] for step in plan["steps"]]

    assert step_ids == [
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
    assert "verify_elasticsearch_hybrid_prerequisites.py" in _step(
        plan, "verify_elasticsearch_hybrid_prerequisites"
    )["command"]
    assert (
        "--runtime-probe-json /tmp/image_agent_runtime_probe_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json"
        in _step(plan, "verify_elasticsearch_hybrid_prerequisites")["command"]
    )
    assert "app.scripts.probe_runtime_environment --json" in _step(
        plan, "inspect_local_elasticsearch_runtime"
    )["command"]
    assert "open('/tmp" not in _step(plan, "inspect_local_elasticsearch_runtime")["command"]
    assert "print('" not in _step(plan, "inspect_local_elasticsearch_runtime")["command"]
    assert "elasticsearch.runtime_discovery_present=true" in _step(
        plan, "inspect_local_elasticsearch_runtime"
    )["expected_success"]
    setup_step = _step(plan, "setup_elasticsearch_hybrid_rag_from_git_script")
    assert "scripts/setup_elasticsearch_hybrid_rag.py" in setup_step["command"]
    assert "--apply" in setup_step["command"]
    assert "--derive-embedding-from-env" in setup_step["command"]
    assert "--rebuild-rag" not in setup_step["command"]
    assert "--verify-prerequisites" not in setup_step["command"]
    assert "--embedding-api-key-env IMAGE_AGENT_RAG_EMBEDDING_API_KEY" in setup_step["command"]
    assert "start_elasticsearch_trial_license" in setup_step["command"]
    assert ":latest" not in setup_step["command"]
    assert "elasticsearch_hybrid_rag_setup_v1" in setup_step["expected_success"]
    assert "elasticsearch_trial_license_status=started_or_already_started" in setup_step["expected_success"]
    assert "docker.elastic.co/elasticsearch/elasticsearch:9.4.2" in json.dumps(setup_step["expected_success"])
    assert "elastic_endpoint_bound_to_loopback" in setup_step["command"]
    assert "no_latest_tags" in setup_step["command"]
    assert "env_key_status" in setup_step["command"]
    assert "secret_values_not_logged" in setup_step["command"]
    assert "secret_values_not_printed" in setup_step["command"]
    for expected in setup_step["expected_success"]:
        assert f"echo {expected}" in setup_step["command"]
    embedding_step = _step(plan, "setup_local_embedding_service_from_git_script")
    assert "scripts/setup_local_embedding_service.py" in embedding_step["command"]
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
    assert "embedding_endpoint_bound_to_loopback" in embedding_step["command"]
    assert "embedding_endpoint_probe_passed" in embedding_step["command"]
    assert "no_latest_tags" in embedding_step["command"]
    assert "env_key_status" in embedding_step["command"]
    assert "secret_values_not_logged" in embedding_step["command"]
    assert "secret_values_not_printed" in embedding_step["command"]
    for expected in embedding_step["expected_success"]:
        assert f"echo {expected}" in embedding_step["command"]
    prepare_images_step = _step(plan, "operator_prepare_fixed_workflow_images_if_missing")
    assert "--prepare-missing-images" in prepare_images_step["command"]
    assert "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES" in prepare_images_step["command"]
    assert "workflow_images_prepare_attempted_evidence=true" in prepare_images_step["expected_success"]
    assert prepare_images_step["requires_operator_authorization"] is True
    assert prepare_images_step["mutates_remote_state"] is True
    assert "remote-release-gate-command-plan.json" in _step(plan, "continue_release_gate_strict_smoke")[
        "command"
    ]


def test_elasticsearch_hybrid_config_plan_rejects_env_presence_command_without_secret_safe_marker():
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "verify_secret_env_presence_without_values")
    step["command"] = step["command"].replace("print('secret_values_not_printed=true')\n", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "secret_values_not_printed=true" in str(exc.value)


def test_elasticsearch_hybrid_config_plan_rejects_missing_local_runtime_probe_step():
    verifier = _load_verifier()
    plan = _plan()
    plan["steps"] = [step for step in plan["steps"] if step["id"] != "inspect_local_elasticsearch_runtime"]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected Elasticsearch config sequence" in str(exc.value)


def test_elasticsearch_hybrid_config_plan_rejects_unpinned_local_elasticsearch_image():
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "setup_elasticsearch_hybrid_rag_from_git_script")
    step["expected_success"] = [item.replace(":9.4.2", ":latest") for item in step["expected_success"]]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "setup_elasticsearch_hybrid_rag_from_git_script.expected_success must use pinned Elastic image" in str(
        exc.value
    )


def test_elasticsearch_hybrid_config_plan_rejects_missing_git_setup_script_step():
    verifier = _load_verifier()
    plan = _plan()
    plan["steps"] = [step for step in plan["steps"] if step["id"] != "setup_elasticsearch_hybrid_rag_from_git_script"]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected Elasticsearch config sequence" in str(exc.value)


@pytest.mark.parametrize(
    "missing_probe",
    [
        "elastic_endpoint_bound_to_loopback",
        "no_latest_tags",
        "env_key_status",
        "secret_values_not_logged",
        "secret_values_not_printed",
    ],
)
def test_elasticsearch_hybrid_config_plan_rejects_missing_setup_report_probe(missing_probe):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "setup_elasticsearch_hybrid_rag_from_git_script")
    step["command"] = step["command"].replace(f" && grep -q {missing_probe} /tmp/image_agent_elasticsearch_hybrid_setup_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_probe in str(exc.value)


@pytest.mark.parametrize(
    "missing_probe",
    [
        "embedding_endpoint_bound_to_loopback",
        "embedding_endpoint_probe_passed",
        "no_latest_tags",
        "env_key_status",
        "secret_values_not_logged",
        "secret_values_not_printed",
    ],
)
def test_elasticsearch_hybrid_config_plan_rejects_missing_embedding_setup_report_probe(missing_probe):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "setup_local_embedding_service_from_git_script")
    step["command"] = step["command"].replace(f" && grep -q {missing_probe} /tmp/image_agent_local_embedding_setup_codex-es-hybrid-runtime-probe-rootfix10-20260619T154306Z.json", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_probe in str(exc.value)


@pytest.mark.parametrize(
    ("step_id", "marker"),
    [
        ("setup_local_embedding_service_from_git_script", "status=completed"),
        ("setup_elasticsearch_hybrid_rag_from_git_script", "elastic_container_name=image-agent-es"),
    ],
)
def test_elasticsearch_hybrid_config_plan_rejects_setup_expected_success_without_echo(step_id, marker):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, step_id)
    step["command"] = step["command"].replace(f" && echo {marker}", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert marker in str(exc.value)


@pytest.mark.parametrize(
    "missing_marker",
    [
        "restart_preflight:ok",
        "health.app=image_agent",
        "release_overlay_serving=true",
    ],
)
def test_elasticsearch_hybrid_config_plan_rejects_restart_without_health_evidence(missing_marker):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "restart_api_from_release_overlay")
    step["expected_success"] = [item for item in step["expected_success"] if item != missing_marker]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_marker in str(exc.value)


def test_elasticsearch_hybrid_config_plan_rejects_missing_workflow_image_preparation():
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "operator_prepare_fixed_workflow_images_if_missing")
    step["command"] = step["command"].replace(" --prepare-missing-images", "")

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "operator_prepare_fixed_workflow_images_if_missing.command must include --prepare-missing-images" in str(
        exc.value
    )


@pytest.mark.parametrize(
    "missing_marker",
    [
        "configured=true",
        "mode=connected",
        "persisted=true",
        "indexed_chunk_count>0",
        "embedding_production_ready=true",
        "error absent",
        "embedding_error absent",
    ],
)
def test_elasticsearch_hybrid_config_plan_rejects_rebuild_without_machine_evidence(missing_marker):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "rebuild_elasticsearch_hybrid_rag")
    step["expected_success"] = [item for item in step["expected_success"] if item != missing_marker]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_marker in str(exc.value)


@pytest.mark.parametrize(
    "missing_marker",
    [
        "remote-release-gate-command-plan.json status=passed",
        "strict_smoke_next_step_unblocked=true",
    ],
)
def test_elasticsearch_hybrid_config_plan_rejects_strict_smoke_handoff_without_machine_evidence(missing_marker):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "continue_release_gate_strict_smoke")
    step["expected_success"] = [item for item in step["expected_success"] if item != missing_marker]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_marker in str(exc.value)


def test_elasticsearch_hybrid_config_plan_rejects_missing_prerequisite_step():
    verifier = _load_verifier()
    plan = _plan()
    plan["steps"] = [step for step in plan["steps"] if step["id"] != "verify_elasticsearch_hybrid_prerequisites"]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "steps must contain the expected Elasticsearch config sequence" in str(exc.value)


def test_elasticsearch_hybrid_config_plan_rejects_secret_like_values():
    verifier = _load_verifier()
    plan = _plan()
    plan["env_template"][0] = "IMAGE_AGENT_ELASTICSEARCH_URL=https://elastic.example.local:9200"
    _step(plan, "setup_elasticsearch_hybrid_rag_from_git_script")["command"] += " OPENAI_API_KEY=sk-live-secret-token"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "must not contain secret-like values" in str(exc.value)


def test_elasticsearch_hybrid_config_plan_rejects_unsafe_release_overlay():
    verifier = _load_verifier()
    plan = _plan()
    plan["release_overlay"] = "/home/yyf/project/image_agent"

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert "release_overlay must be under /home/yyf/project/image_agent_releases" in str(exc.value)


@pytest.mark.parametrize(
    "missing_item",
    [
        "rag_status_hybrid_lexical_retriever=standard",
        "rag_status_hybrid_vector_retriever=knn",
        "rag_status_hybrid_dense_vector_field=embedding",
        "rag_status_hybrid_fusion=rrf",
        "rag_status_hybrid_official_rrf_source_present=true",
        "rag_status_hybrid_embedding_transport production-safe",
        "rag_status_hybrid_embedding_endpoint_configured=true",
        "rag_status_hybrid_embedding_production_ready=true",
        "runtime_probe_machine_binding=runtime_discovered",
        "runtime_probe_workflow_tool_execution=deployment_server_local",
        "runtime_probe_docker_runtime_host=api_server",
        "runtime_probe_elasticsearch_discovery_status=available",
        "runtime_probe_elasticsearch_container_running=true",
        "runtime_probe_elasticsearch_candidate_endpoint loopback",
    ],
)
def test_elasticsearch_hybrid_config_plan_requires_detailed_prerequisite_expected_success(missing_item):
    verifier = _load_verifier()
    plan = _plan()
    step = _step(plan, "verify_elasticsearch_hybrid_prerequisites")
    step["expected_success"] = [item for item in step["expected_success"] if item != missing_item]

    with pytest.raises(SystemExit) as exc:
        verifier.verify_plan(plan)

    assert missing_item in str(exc.value)


def test_elasticsearch_hybrid_config_plan_cli_writes_passed_report(capsys):
    verifier = _load_verifier()

    verifier.main([str(PLAN_PATH)])

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "passed"
    assert report["source_json"].endswith("remote-elasticsearch-hybrid-config-plan.json")
