from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path


PLAN_ID = "remote_elasticsearch_hybrid_config_plan_v1"
REMOTE_HOST = "yyf@10.2.32.14"
REMOTE_RELEASE_ROOT = "/home/yyf/project/image_agent_releases"
REMOTE_ENV_FILE = "/home/yyf/project/image_agent/.env"
PINNED_ELASTICSEARCH_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:9.4.2"
PINNED_LOCAL_EMBEDDING_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9"
LOCAL_EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_EMBEDDING_MODEL = "image-agent-minilm-l6-v2"
LOCAL_EMBEDDING_BASE_URL = "http://127.0.0.1:18081/v1"
EXPECTED_STEP_IDS = [
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
EXPECTED_OBSERVED_BLOCKERS = [
    "remote_port_9200_not_listening",
    "docker_socket_requires_operator_or_sudo",
    "live_rag_engine_not_elasticsearch_hybrid",
    "missing_required_elasticsearch_or_embedding_env",
]
EXPECTED_MISSING_ENV_KEYS = [
    "IMAGE_AGENT_ELASTICSEARCH_URL",
    "IMAGE_AGENT_ELASTICSEARCH_INDEX",
    "IMAGE_AGENT_ELASTICSEARCH_API_KEY",
    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER",
    "IMAGE_AGENT_RAG_EMBEDDING_MODEL",
    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL",
    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY",
]
EXPECTED_SAFETY_INVARIANTS = [
    "do_not_print_secret_values",
    "do_not_commit_env_files",
    "do_not_mutate_live_tree_before_release_overlay_restart",
    "do_not_run_strict_smoke_before_es_prerequisite_passes",
]
EXPECTED_OFFICIAL_RUNTIME_SOURCES = [
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker",
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic",
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod",
    "https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-license-post-start-trial",
    "https://huggingface.co/docs/text-embeddings-inference/en/quick_tour",
    "https://huggingface.co/docs/text-embeddings-inference/en/basic_tutorials/using_cli",
]
EXPECTED_ENV_TEMPLATE_PREFIXES = [
    "IMAGE_AGENT_ELASTICSEARCH_URL=<",
    "IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_",
    "IMAGE_AGENT_ELASTICSEARCH_API_KEY=<",
    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
    "IMAGE_AGENT_RAG_EMBEDDING_MODEL=<",
    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=<",
    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY=<",
]
DETAILED_PREREQUISITE_EXPECTED_SUCCESS = [
    "status=passed",
    "rag_status_engine=elasticsearch_hybrid",
    "rag_status_hybrid_engine=elasticsearch",
    "rag_status_hybrid_configured=true",
    "mode=connected",
    "persisted=true",
    "indexed_chunk_count>0",
    "rag_status_hybrid_lexical_retriever=standard",
    "rag_status_hybrid_vector_retriever=knn",
    "rag_status_hybrid_dense_vector_field=embedding",
    "rag_status_hybrid_dense_vector_dims>0",
    "rag_status_hybrid_fusion=rrf",
    "rag_status_hybrid_official_rrf_source_present=true",
    "rag_status_hybrid_error_absent=true",
    "rag_status_hybrid_embedding_error_absent=true",
    "rag_status_hybrid_embedding_provider production configured",
    "rag_status_hybrid_embedding_model present",
    "rag_status_hybrid_embedding_transport production-safe",
    "rag_status_hybrid_embedding_endpoint_configured=true",
    "rag_status_hybrid_embedding_production_ready=true",
    "runtime_probe_machine_binding=runtime_discovered",
    "runtime_probe_workflow_tool_execution=deployment_server_local",
    "runtime_probe_docker_runtime_host=api_server",
    "runtime_probe_elasticsearch_discovery_status=available",
    "runtime_probe_elasticsearch_container_running=true",
    "runtime_probe_elasticsearch_candidate_endpoint loopback",
    "secrets_redacted=true",
]
API_KEY_SHAPED_RE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9._-]{8,}")
URL_RE = re.compile(r"https?://")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_plan(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "Elasticsearch config plan must be a JSON object")
    return payload


def _is_privacy_safe_release_symbol(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,80}", value or ""))


def _require_release_overlay(value: object) -> str:
    _require(
        isinstance(value, str) and value.startswith(f"{REMOTE_RELEASE_ROOT}/"),
        "release_overlay must be under /home/yyf/project/image_agent_releases",
    )
    release_id = value.removeprefix(f"{REMOTE_RELEASE_ROOT}/")
    _require("/" not in release_id, "release_overlay must not contain nested path segments")
    _require(not release_id.endswith(".incoming"), "release_overlay must not point at an incoming overlay")
    _require(_is_privacy_safe_release_symbol(release_id), "release_overlay must end with a privacy-safe release id")
    return value


def _require_no_secret_like_values(plan: dict) -> None:
    serialized = json.dumps(plan, sort_keys=True)
    _require("OPENAI_API_KEY=" not in serialized, "Elasticsearch config plan must not contain secret-like values")
    _require(API_KEY_SHAPED_RE.search(serialized) is None, "Elasticsearch config plan must not contain secret-like values")
    for item in plan.get("env_template") or []:
        if isinstance(item, str) and item.startswith(("IMAGE_AGENT_ELASTICSEARCH_URL=", "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=")):
            value = item.split("=", 1)[1]
            _require(value.startswith("<") and value.endswith(">"), "Elasticsearch config plan must not contain secret-like values")
        if isinstance(item, str) and item.startswith(("IMAGE_AGENT_ELASTICSEARCH_API_KEY=", "IMAGE_AGENT_RAG_EMBEDDING_API_KEY=")):
            value = item.split("=", 1)[1]
            _require(value.startswith("<") and value.endswith(">"), "Elasticsearch config plan must not contain secret-like values")
    for step in plan.get("steps") or []:
        command = step.get("command") if isinstance(step, dict) else None
        if isinstance(command, str) and URL_RE.search(command):
            allowed_local_status_url = "http://127.0.0.1:8000/agent/rag/status" in command
            allowed_local_embedding_url = LOCAL_EMBEDDING_BASE_URL in command
            _require(
                allowed_local_status_url or allowed_local_embedding_url or ("<" in command and ">" in command),
                "Elasticsearch config plan must not contain secret-like values",
            )


def _verify_step_shape(step: object, *, expected_id: str, index: int) -> dict:
    _require(isinstance(step, dict), f"steps[{index}] must be an object")
    _require(step.get("id") == expected_id, f"steps[{index}].id must be {expected_id}")
    _require(isinstance(step.get("command"), str) and step["command"].strip(), f"{expected_id}.command must be non-empty")
    _require(isinstance(step.get("mutates_remote_state"), bool), f"{expected_id}.mutates_remote_state must be boolean")
    _require(
        isinstance(step.get("requires_operator_authorization"), bool),
        f"{expected_id}.requires_operator_authorization must be boolean",
    )
    expected_success = step.get("expected_success")
    _require(isinstance(expected_success, list) and expected_success, f"{expected_id}.expected_success must be non-empty")
    return step


def _step_by_id(steps: Sequence[dict], step_id: str) -> dict:
    for step in steps:
        if step.get("id") == step_id:
            return step
    raise SystemExit(f"missing step {step_id}")


def _require_command_contains(step: dict, needle: str) -> None:
    _require(needle in step["command"], f"{step['id']}.command must include {needle}")


def _require_expected_success_contains(step: dict, needle: str) -> None:
    _require(needle in step["expected_success"], f"{step['id']}.expected_success must include {needle}")


def _require_expected_success_echoed(step: dict) -> None:
    for marker in step["expected_success"]:
        _require_command_contains(step, f"echo {marker}")


def verify_plan(plan: dict) -> dict:
    _require(plan.get("plan_id") == PLAN_ID, f"plan_id must be {PLAN_ID}")
    _require(plan.get("schema_version") == 1, "schema_version must be 1")
    _require(plan.get("status") == "operator_configuration_required", "status must be operator_configuration_required")
    _require(plan.get("remote_host") == REMOTE_HOST, "remote_host must identify yyf")
    release_overlay = _require_release_overlay(plan.get("release_overlay"))
    _require(plan.get("remote_env_file") == REMOTE_ENV_FILE, "remote_env_file mismatch")
    _require(
        plan.get("official_runtime_sources") == EXPECTED_OFFICIAL_RUNTIME_SOURCES,
        "official_runtime_sources mismatch",
    )
    _require(plan.get("observed_blockers") == EXPECTED_OBSERVED_BLOCKERS, "observed_blockers mismatch")
    _require(plan.get("missing_env_keys") == EXPECTED_MISSING_ENV_KEYS, "missing_env_keys mismatch")
    _require(plan.get("safety_invariants") == EXPECTED_SAFETY_INVARIANTS, "safety_invariants mismatch")
    _require_no_secret_like_values(plan)

    env_template = plan.get("env_template")
    _require(isinstance(env_template, list), "env_template must be a list")
    _require(len(env_template) == len(EXPECTED_ENV_TEMPLATE_PREFIXES), "env_template entries mismatch")
    for entry, expected_prefix in zip(env_template, EXPECTED_ENV_TEMPLATE_PREFIXES, strict=True):
        _require(isinstance(entry, str) and entry.startswith(expected_prefix), "env_template entries mismatch")
    release_id = release_overlay.rsplit("/", 1)[-1]
    _require(
        f"IMAGE_AGENT_ELASTICSEARCH_INDEX=image_agent_rag_{release_id}" in env_template,
        "env_template must bind index to the release id",
    )
    steps = plan.get("steps")
    _require(isinstance(steps, list) and len(steps) == len(EXPECTED_STEP_IDS), "steps must contain the expected Elasticsearch config sequence")
    verified_steps = [
        _verify_step_shape(step, expected_id=expected_id, index=index)
        for index, (step, expected_id) in enumerate(zip(steps, EXPECTED_STEP_IDS, strict=True))
    ]
    steps_by_id = {step["id"]: step for step in verified_steps}

    _require_command_contains(steps_by_id["inspect_local_elasticsearch_runtime"], "-m app.scripts.probe_runtime_environment --json")
    _require_command_contains(steps_by_id["inspect_local_elasticsearch_runtime"], "runtime_discovery")
    for expected in (
        "runtime_probe.schema_version=1",
        "runtime_probe.machine_binding=runtime_discovered",
        "elasticsearch.runtime_discovery_present=true",
        "secret_values_not_printed=true",
    ):
        _require_expected_success_contains(steps_by_id["inspect_local_elasticsearch_runtime"], expected)
    provision_step = steps_by_id["setup_elasticsearch_hybrid_rag_from_git_script"]
    embedding_step = steps_by_id["setup_local_embedding_service_from_git_script"]
    _require(
        PINNED_LOCAL_EMBEDDING_IMAGE in json.dumps(embedding_step) and ":latest" not in json.dumps(embedding_step),
        "setup_local_embedding_service_from_git_script must use pinned TEI image",
    )
    _require_command_contains(embedding_step, "scripts/setup_local_embedding_service.py")
    _require_command_contains(embedding_step, "--apply")
    _require_command_contains(embedding_step, f"--embedding-image {PINNED_LOCAL_EMBEDDING_IMAGE}")
    _require_command_contains(embedding_step, "--network-mode host")
    _require_command_contains(embedding_step, f"--model-id {LOCAL_EMBEDDING_MODEL_ID}")
    _require_command_contains(embedding_step, f"--served-model-name {LOCAL_EMBEDDING_MODEL}")
    _require_command_contains(embedding_step, f"--embedding-base-url {LOCAL_EMBEDDING_BASE_URL}")
    for required_probe in (
        "embedding_endpoint_bound_to_loopback",
        "embedding_endpoint_probe_passed",
        "no_latest_tags",
        "env_key_status",
        "secret_values_not_logged",
        "secret_values_not_printed",
    ):
        _require_command_contains(embedding_step, f"grep -q {required_probe}")
    for expected in (
        "local_embedding_service_setup_v1",
        f"embedding_image={PINNED_LOCAL_EMBEDDING_IMAGE}",
        f"embedding_model_id={LOCAL_EMBEDDING_MODEL_ID}",
        f"embedding_served_model={LOCAL_EMBEDDING_MODEL}",
        "embedding_network_mode=host",
        "status=completed",
        "embedding_endpoint_bound_to_loopback=true",
        "embedding_endpoint_probe_passed=true",
        "no_latest_tags=true",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL=set",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set",
        "secret_values_not_logged=true",
        "secret_values_not_printed=true",
    ):
        _require_expected_success_contains(embedding_step, expected)
    _require_expected_success_echoed(embedding_step)
    _require(
        PINNED_ELASTICSEARCH_IMAGE in json.dumps(provision_step["expected_success"]) and ":latest" not in json.dumps(provision_step),
        "setup_elasticsearch_hybrid_rag_from_git_script.expected_success must use pinned Elastic image",
    )
    _require_command_contains(provision_step, "scripts/setup_elasticsearch_hybrid_rag.py")
    _require_command_contains(provision_step, "--apply")
    _require_command_contains(provision_step, "--derive-embedding-from-env")
    _require_command_contains(provision_step, "--embedding-api-key-env IMAGE_AGENT_RAG_EMBEDDING_API_KEY")
    _require_command_contains(provision_step, "start_elasticsearch_trial_license")
    for required_probe in (
        "elastic_endpoint_bound_to_loopback",
        "no_latest_tags",
        "env_key_status",
        "secret_values_not_logged",
        "secret_values_not_printed",
    ):
        _require_command_contains(provision_step, f"grep -q {required_probe}")
    _require("--rebuild-rag" not in provision_step["command"], "setup step must not rebuild RAG before API restart")
    _require(
        "--verify-prerequisites" not in provision_step["command"],
        "setup step must not run ES prerequisite verification before API restart",
    )
    for expected in (
        "elasticsearch_hybrid_rag_setup_v1",
        f"elasticsearch_image={PINNED_ELASTICSEARCH_IMAGE}",
        "elasticsearch_trial_license_status=started_or_already_started",
        "status=completed",
        "elastic_endpoint_bound_to_loopback=true",
        "no_latest_tags=true",
        "IMAGE_AGENT_ELASTICSEARCH_URL=set",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL=set",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set",
        "secret_values_not_logged=true",
        "secret_values_not_printed=true",
    ):
        _require_expected_success_contains(provision_step, expected)
    _require_expected_success_echoed(provision_step)
    for env_key in (
        "IMAGE_AGENT_ELASTICSEARCH_URL=set",
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL=set",
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set",
    ):
        _require_expected_success_contains(steps_by_id["verify_secret_env_presence_without_values"], env_key)
    _require_command_contains(steps_by_id["verify_secret_env_presence_without_values"], "print(f'{key}='")
    _require_command_contains(
        steps_by_id["verify_secret_env_presence_without_values"],
        "secret_values_not_printed=true",
    )
    _require_command_contains(steps_by_id["restart_api_from_release_overlay"], f"export IMAGE_AGENT_RELEASE_ROOT={release_overlay}")
    _require_command_contains(steps_by_id["restart_api_from_release_overlay"], f"export IMAGE_AGENT_ENV_FILE={REMOTE_ENV_FILE}")
    _require_command_contains(steps_by_id["restart_api_from_release_overlay"], "bash tools/restart_remote_image_agent_api.sh")
    for expected in (
        "restart_preflight:ok",
        "health.app=image_agent",
        "release_overlay_serving=true",
    ):
        _require_expected_success_contains(steps_by_id["restart_api_from_release_overlay"], expected)
    prepare_images_step = steps_by_id["operator_prepare_fixed_workflow_images_if_missing"]
    _require_command_contains(prepare_images_step, "--prepare-missing-images")
    _require_command_contains(prepare_images_step, "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES=1")
    _require_command_contains(prepare_images_step, "runtime_preparation")
    _require_command_contains(prepare_images_step, "app.scripts.probe_runtime_environment")
    for expected in (
        "workflow_images.prepare_missing_images_setting=IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES",
        "runtime_preparation.auto_pull_missing_images=true",
        "workflow_images_prepare_attempted_evidence=true",
        "secret_values_not_printed=true",
    ):
        _require_expected_success_contains(prepare_images_step, expected)
    rebuild_step = steps_by_id["rebuild_elasticsearch_hybrid_rag"]
    _require_command_contains(rebuild_step, "rebuild_rag_index")
    _require_command_contains(rebuild_step, "rag_status")
    _require_command_contains(rebuild_step, "raise SystemExit")
    for expected in (
        "configured=true",
        "mode=connected",
        "persisted=true",
        "indexed_chunk_count>0",
        "embedding_production_ready=true",
        "error absent",
        "embedding_error absent",
    ):
        _require_expected_success_contains(rebuild_step, expected)
        _require_command_contains(rebuild_step, f'print("{expected}")')
    _require_command_contains(steps_by_id["verify_elasticsearch_hybrid_prerequisites"], "verify_elasticsearch_hybrid_prerequisites.py")
    _require_command_contains(steps_by_id["verify_elasticsearch_hybrid_prerequisites"], f"--env-file {REMOTE_ENV_FILE}")
    _require_command_contains(
        steps_by_id["verify_elasticsearch_hybrid_prerequisites"],
        "--rag-status-url http://127.0.0.1:8000/agent/rag/status",
    )
    _require_command_contains(
        steps_by_id["verify_elasticsearch_hybrid_prerequisites"],
        f"--runtime-probe-json /tmp/image_agent_runtime_probe_{release_id}.json",
    )
    for expected in DETAILED_PREREQUISITE_EXPECTED_SUCCESS:
        _require_expected_success_contains(steps_by_id["verify_elasticsearch_hybrid_prerequisites"], expected)
    strict_smoke_handoff_step = steps_by_id["continue_release_gate_strict_smoke"]
    _require_command_contains(strict_smoke_handoff_step, "remote-release-gate-command-plan.json")
    _require_command_contains(strict_smoke_handoff_step, "verify_release_gate_command_plan.py")
    for expected in (
        "remote-release-gate-command-plan.json status=passed",
        "strict_smoke_next_step_unblocked=true",
    ):
        _require_expected_success_contains(strict_smoke_handoff_step, expected)
        _require_command_contains(strict_smoke_handoff_step, f"echo {expected}")

    operator_steps = [step["id"] for step in verified_steps if step["requires_operator_authorization"]]
    mutating_steps = [step["id"] for step in verified_steps if step["mutates_remote_state"]]
    expected_mutating = [
        "setup_local_embedding_service_from_git_script",
        "setup_elasticsearch_hybrid_rag_from_git_script",
        "restart_api_from_release_overlay",
        "operator_prepare_fixed_workflow_images_if_missing",
        "rebuild_elasticsearch_hybrid_rag",
    ]
    _require(operator_steps == expected_mutating, "operator authorization steps mismatch")
    _require(mutating_steps == expected_mutating, "mutating steps mismatch")
    _require(
        verified_steps.index(_step_by_id(verified_steps, "verify_elasticsearch_hybrid_prerequisites"))
        < verified_steps.index(_step_by_id(verified_steps, "continue_release_gate_strict_smoke")),
        "ES prerequisite must run before strict smoke handoff",
    )

    return {
        "status": "passed",
        "summary": "status=passed",
        "checked": {
            "plan_id": plan["plan_id"],
            "step_count": len(verified_steps),
            "release_overlay": release_overlay,
            "remote_env_file": plan["remote_env_file"],
            "operator_authorization_required_steps": operator_steps,
            "mutating_steps": mutating_steps,
            "missing_env_keys": plan["missing_env_keys"],
        },
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify the remote Elasticsearch hybrid configuration plan JSON.")
    parser.add_argument("plan_json", help="Path to docs/deployment/remote-elasticsearch-hybrid-config-plan.json")
    args = parser.parse_args(argv)
    report = verify_plan(load_plan(args.plan_json))
    report["source_json"] = str(Path(args.plan_json))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
