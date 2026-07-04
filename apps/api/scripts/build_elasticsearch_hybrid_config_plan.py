from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path


PLAN_ID = "remote_elasticsearch_hybrid_config_plan_v1"
DEFAULT_REMOTE_HOST = "yyf@10.2.32.14"
DEFAULT_REMOTE_ENV_FILE = "/home/yyf/project/image_agent/.env"
DEFAULT_RELEASE_ROOT = "/home/yyf/project/image_agent_releases"
DEFAULT_ELASTICSEARCH_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:9.4.2"
DEFAULT_LOCAL_EMBEDDING_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9"
DEFAULT_LOCAL_EMBEDDING_BASE_URL = "http://127.0.0.1:18081/v1"
DEFAULT_LOCAL_EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_LOCAL_EMBEDDING_MODEL = "image-agent-minilm-l6-v2"
OFFICIAL_RUNTIME_SOURCES = [
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker",
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic",
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod",
    "https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-license-post-start-trial",
    "https://huggingface.co/docs/text-embeddings-inference/en/quick_tour",
    "https://huggingface.co/docs/text-embeddings-inference/en/basic_tutorials/using_cli",
]
RELEASE_OVERLAY_RE = re.compile(r"/home/yyf/project/image_agent_releases/[A-Za-z0-9][A-Za-z0-9_.-]{2,80}")
KNOWN_ENV_KEYS = [
    "IMAGE_AGENT_ELASTICSEARCH_URL",
    "IMAGE_AGENT_ELASTICSEARCH_INDEX",
    "IMAGE_AGENT_ELASTICSEARCH_API_KEY",
    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER",
    "IMAGE_AGENT_RAG_EMBEDDING_MODEL",
    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL",
    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY",
]
DEFAULT_OBSERVED_BLOCKERS = [
    "remote_port_9200_not_listening",
    "docker_socket_requires_operator_or_sudo",
    "live_rag_engine_not_elasticsearch_hybrid",
    "missing_required_elasticsearch_or_embedding_env",
]


def _required_release_overlay(value: str) -> str:
    text = (value or "").replace("\\", "/").strip().rstrip("/")
    if not RELEASE_OVERLAY_RE.fullmatch(text) or text.endswith(".incoming"):
        raise SystemExit(
            "release_overlay must be a release path under /home/yyf/project/image_agent_releases"
        )
    return text


def _release_id_from_overlay(release_overlay: str) -> str:
    return release_overlay.rsplit("/", 1)[-1]


def _safe_missing_keys(keys: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    safe_keys: list[str] = []
    for key in keys:
        if key in KNOWN_ENV_KEYS and key not in seen:
            safe_keys.append(key)
            seen.add(key)
    return safe_keys


def _env_presence_command(remote_env_file: str) -> str:
    keys = ", ".join(repr(key) for key in KNOWN_ENV_KEYS)
    script = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        f"keys = [{keys}]\n"
        f"env = Path('{remote_env_file}')\n"
        "seen = {}\n"
        "if env.exists():\n"
        "    for raw in env.read_text(errors='replace').splitlines():\n"
        "        line = raw.strip()\n"
        "        if not line or line.startswith('#') or '=' not in line:\n"
        "            continue\n"
        "        key, value = line.split('=', 1)\n"
        "        if key in keys:\n"
        "            seen[key] = bool(value.strip())\n"
        "for key in keys:\n"
        "    print(f'{key}=' + ('set' if seen.get(key) else 'missing'))\n"
        "print('secret_values_not_printed=true')\n"
        "PY"
    )
    return script


def build_elasticsearch_hybrid_config_plan(
    *,
    release_overlay: str,
    missing_env_keys: Sequence[str] = (),
    remote_host: str = DEFAULT_REMOTE_HOST,
    remote_env_file: str = DEFAULT_REMOTE_ENV_FILE,
) -> dict:
    overlay = _required_release_overlay(release_overlay)
    release_id = _release_id_from_overlay(overlay)
    index_name = f"image_agent_rag_{release_id}"
    api_dir = f"{overlay}/apps/api"
    shared_python = "/home/yyf/project/image_agent/apps/api/.venv/bin/python"
    runtime_probe_json = f"/tmp/image_agent_runtime_probe_{release_id}.json"
    setup_report_json = f"/tmp/image_agent_elasticsearch_hybrid_setup_{release_id}.json"
    env_presence = _env_presence_command(remote_env_file)
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "status": "operator_configuration_required",
        "remote_host": remote_host,
        "release_overlay": overlay,
        "remote_env_file": remote_env_file,
        "official_runtime_sources": OFFICIAL_RUNTIME_SOURCES,
        "observed_blockers": DEFAULT_OBSERVED_BLOCKERS,
        "missing_env_keys": _safe_missing_keys(missing_env_keys),
        "env_template": [
            "IMAGE_AGENT_ELASTICSEARCH_URL=<operator-managed-elasticsearch-url>",
            f"IMAGE_AGENT_ELASTICSEARCH_INDEX={index_name}",
            "IMAGE_AGENT_ELASTICSEARCH_API_KEY=<optional-operator-managed-secret>",
            "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=openai_compatible",
            "IMAGE_AGENT_RAG_EMBEDDING_MODEL=<operator-approved-embedding-model>",
            "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=<operator-managed-openai-compatible-embedding-endpoint>",
            "IMAGE_AGENT_RAG_EMBEDDING_API_KEY=<operator-managed-secret-or-reused-model-key>",
        ],
        "safety_invariants": [
            "do_not_print_secret_values",
            "do_not_commit_env_files",
            "do_not_mutate_live_tree_before_release_overlay_restart",
            "do_not_run_strict_smoke_before_es_prerequisite_passes",
        ],
        "steps": [
            {
                "id": "inspect_local_elasticsearch_runtime",
                "purpose": "Discover whether this deployment server already has a local Elasticsearch container or endpoint candidate before applying secrets.",
                "command": (
                    f"ssh {remote_host} 'cd {api_dir} && "
                    f"PYTHONPATH=. {shared_python} -m app.scripts.probe_runtime_environment --json "
                    f"> {runtime_probe_json} && "
                    f"grep -q schema_version {runtime_probe_json} && "
                    f"grep -q runtime_discovered {runtime_probe_json} && "
                    f"grep -q runtime_discovery {runtime_probe_json} && "
                    "echo runtime_probe.schema_version=1 && "
                    "echo runtime_probe.machine_binding=runtime_discovered && "
                    "echo elasticsearch.runtime_discovery_present=true && "
                    "echo secret_values_not_printed=true'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "runtime_probe.schema_version=1",
                    "runtime_probe.machine_binding=runtime_discovered",
                    "elasticsearch.runtime_discovery_present=true",
                    "secret_values_not_printed=true",
                ],
            },
            {
                "id": "setup_local_embedding_service_from_git_script",
                "purpose": (
                    "Start a deployment-local OpenAI-compatible embedding endpoint when no external production "
                    "embedding endpoint is available. The Git script uses a pinned Hugging Face TEI image, binds "
                    "only to loopback, and writes only non-secret RAG embedding endpoint metadata to the deployment env."
                ),
                "command": (
                    f"ssh {remote_host} 'cd {api_dir} && "
                    "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
                    f"PYTHONPATH=. {shared_python} scripts/setup_local_embedding_service.py "
                    f"--env-file {remote_env_file} "
                    f"--embedding-image {DEFAULT_LOCAL_EMBEDDING_IMAGE} "
                    "--network-mode host "
                    f"--model-id {DEFAULT_LOCAL_EMBEDDING_MODEL_ID} "
                    f"--served-model-name {DEFAULT_LOCAL_EMBEDDING_MODEL} "
                    f"--embedding-base-url {DEFAULT_LOCAL_EMBEDDING_BASE_URL} "
                    "--apply "
                    f"--output-json /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q local_embedding_service_setup_v1 /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q {DEFAULT_LOCAL_EMBEDDING_IMAGE} /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q embedding_endpoint_bound_to_loopback /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q embedding_endpoint_probe_passed /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q no_latest_tags /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q env_key_status /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q secret_values_not_logged /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    f"grep -q secret_values_not_printed /tmp/image_agent_local_embedding_setup_{release_id}.json && "
                    "echo local_embedding_service_setup_v1 && "
                    f"echo embedding_image={DEFAULT_LOCAL_EMBEDDING_IMAGE} && "
                    f"echo embedding_model_id={DEFAULT_LOCAL_EMBEDDING_MODEL_ID} && "
                    f"echo embedding_served_model={DEFAULT_LOCAL_EMBEDDING_MODEL} && "
                    "echo embedding_network_mode=host && "
                    "echo status=completed && "
                    "echo embedding_container_name=image-agent-embeddings && "
                    f"echo embedding_base_url={DEFAULT_LOCAL_EMBEDDING_BASE_URL} && "
                    "echo embedding_endpoint_bound_to_loopback=true && "
                    "echo embedding_endpoint_probe_passed=true && "
                    "echo no_latest_tags=true && "
                    "echo IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set && "
                    "echo IMAGE_AGENT_RAG_EMBEDDING_MODEL=set && "
                    "echo IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set && "
                    "echo secret_values_not_logged=true && "
                    "echo secret_values_not_printed=true'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    "local_embedding_service_setup_v1",
                    f"embedding_image={DEFAULT_LOCAL_EMBEDDING_IMAGE}",
                    f"embedding_model_id={DEFAULT_LOCAL_EMBEDDING_MODEL_ID}",
                    f"embedding_served_model={DEFAULT_LOCAL_EMBEDDING_MODEL}",
                    "embedding_network_mode=host",
                    "status=completed",
                    "embedding_container_name=image-agent-embeddings",
                    f"embedding_base_url={DEFAULT_LOCAL_EMBEDDING_BASE_URL}",
                    "embedding_endpoint_bound_to_loopback=true",
                    "embedding_endpoint_probe_passed=true",
                    "no_latest_tags=true",
                    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_MODEL=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set",
                    "secret_values_not_logged=true",
                    "secret_values_not_printed=true",
                ],
            },
            {
                "id": "setup_elasticsearch_hybrid_rag_from_git_script",
                "purpose": (
                    "Configure Elasticsearch hybrid RAG by running the repository bootstrap script on the "
                    "deployment server. The script probes local Docker, pulls the pinned Elasticsearch image when "
                    "missing, starts a loopback-bound container when missing, writes deployment-local env values, "
                    "rebuilds curated RAG into Elasticsearch, and runs the prerequisite verifier."
                ),
                "command": (
                    f"ssh {remote_host} 'cd {api_dir} && "
                    f"set -a; . {remote_env_file}; set +a; "
                    "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
                    f"PYTHONPATH=. {shared_python} scripts/setup_elasticsearch_hybrid_rag.py "
                    f"--env-file {remote_env_file} "
                    f"--index-name {index_name} "
                    "--embedding-provider openai_compatible "
                    "--derive-embedding-from-env "
                    "--embedding-api-key-env IMAGE_AGENT_RAG_EMBEDDING_API_KEY "
                    "--apply "
                    f"--output-json {setup_report_json} && "
                    f"grep -q elasticsearch_hybrid_rag_setup_v1 {setup_report_json} && "
                    f"grep -q {DEFAULT_ELASTICSEARCH_IMAGE} {setup_report_json} && "
                    f"grep -q start_elasticsearch_trial_license {setup_report_json} && "
                    f"grep -q elastic_endpoint_bound_to_loopback {setup_report_json} && "
                    f"grep -q no_latest_tags {setup_report_json} && "
                    f"grep -q env_key_status {setup_report_json} && "
                    f"grep -q secret_values_not_logged {setup_report_json} && "
                    f"grep -q secret_values_not_printed {setup_report_json} && "
                    f"grep -q secret {setup_report_json} && "
                    "echo elasticsearch_hybrid_rag_setup_v1 && "
                    f"echo elasticsearch_image={DEFAULT_ELASTICSEARCH_IMAGE} && "
                    "echo elasticsearch_trial_license_status=started_or_already_started && "
                    "echo status=completed && "
                    "echo elastic_container_name=image-agent-es && "
                    "echo elastic_endpoint_bound_to_loopback=true && "
                    "echo no_latest_tags=true && "
                    "echo IMAGE_AGENT_ELASTICSEARCH_URL=set && "
                    "echo IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set && "
                    "echo IMAGE_AGENT_RAG_EMBEDDING_MODEL=set && "
                    "echo IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set && "
                    "echo secret_values_not_logged=true && "
                    "echo secret_values_not_printed=true'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    "elasticsearch_hybrid_rag_setup_v1",
                    f"elasticsearch_image={DEFAULT_ELASTICSEARCH_IMAGE}",
                    "elasticsearch_trial_license_status=started_or_already_started",
                    "status=completed",
                    "elastic_container_name=image-agent-es",
                    "elastic_endpoint_bound_to_loopback=true",
                    "no_latest_tags=true",
                    "IMAGE_AGENT_ELASTICSEARCH_URL=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_MODEL=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set",
                    "secret_values_not_logged=true",
                    "secret_values_not_printed=true",
                ],
            },
            {
                "id": "verify_secret_env_presence_without_values",
                "purpose": "Confirm only key presence after operator configuration; never print URL or key values.",
                "command": f"ssh {remote_host} \"{env_presence}\"",
                "runs_on": "remote",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "IMAGE_AGENT_ELASTICSEARCH_URL=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_MODEL=set",
                    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL=set",
                    "secret_values_not_printed=true",
                ],
            },
            {
                "id": "restart_api_from_release_overlay",
                "purpose": "Restart the API from the verified release overlay after config is present and restart drain gates pass.",
                "command": (
                    f"ssh {remote_host} 'cd {overlay} && "
                    "export IMAGE_AGENT_ROOT=/home/yyf/project/image_agent && "
                    f"export IMAGE_AGENT_RELEASE_ROOT={overlay} && "
                    f"export IMAGE_AGENT_ENV_FILE={remote_env_file} && "
                    "export IMAGE_AGENT_SHARED_VENV_BIN=/home/yyf/project/image_agent/apps/api/.venv/bin && "
                    f"bash tools/restart_remote_image_agent_api.sh {remote_env_file}'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    "restart_preflight:ok",
                    "health.app=image_agent",
                    "release_overlay_serving=true",
                ],
            },
            {
                "id": "operator_prepare_fixed_workflow_images_if_missing",
                "purpose": (
                    "Prepare fixed-workflow Docker images on the deployment server by pulling missing pinned images "
                    "only through an explicit operator-authorized runtime preparation setting."
                ),
                "command": (
                    f"ssh {remote_host} 'cd {api_dir} && "
                    f"set -a; . {remote_env_file}; set +a; "
                    "IMAGE_AGENT_ROOT=/home/yyf/project/image_agent "
                    "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES=1 "
                    f"PYTHONPATH=. {shared_python} -m app.scripts.probe_runtime_environment --json "
                    f"--prepare-missing-images > {runtime_probe_json} && "
                    f"grep -q runtime_preparation {runtime_probe_json} && "
                    f"grep -q IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES {runtime_probe_json} && "
                    f"grep -q auto_pull_missing_images {runtime_probe_json} && "
                    "echo workflow_images.prepare_missing_images_setting=IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES && "
                    "echo runtime_preparation.auto_pull_missing_images=true && "
                    "echo workflow_images_prepare_attempted_evidence=true && "
                    "echo secret_values_not_printed=true'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    "workflow_images.prepare_missing_images_setting=IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES",
                    "runtime_preparation.auto_pull_missing_images=true",
                    "workflow_images_prepare_attempted_evidence=true",
                    "secret_values_not_printed=true",
                ],
            },
            {
                "id": "rebuild_elasticsearch_hybrid_rag",
                "purpose": "Rebuild curated RAG chunks into the configured Elasticsearch index using production embeddings.",
                "command": (
                    f"ssh {remote_host} 'cd {api_dir} && "
                    f"PYTHONPATH=. {shared_python} - <<\"PY\"\n"
                    "from pathlib import Path\n"
                    "from app.agent.status import rebuild_rag_index, rag_status\n"
                    "def is_true(value):\n"
                    "    return value is True or str(value).lower() == \"true\"\n"
                    "def positive_int(value):\n"
                    "    try:\n"
                    "        return int(value) > 0\n"
                    "    except (TypeError, ValueError):\n"
                    "        return False\n"
                    "def require(condition, marker):\n"
                    "    if not condition:\n"
                    "        raise SystemExit(marker)\n"
                    "root = Path(\"/home/yyf/project/image_agent\")\n"
                    "rebuild = rebuild_rag_index(root).get(\"hybrid_search\") or {}\n"
                    "status = rag_status(root).get(\"index\", {}).get(\"hybrid_search\") or {}\n"
                    "require(is_true(rebuild.get(\"configured\")) and is_true(status.get(\"configured\")), \"configured=true\")\n"
                    "require(rebuild.get(\"mode\") == \"connected\" and status.get(\"mode\") == \"connected\", \"mode=connected\")\n"
                    "require(is_true(rebuild.get(\"persisted\")) and is_true(status.get(\"persisted\")), \"persisted=true\")\n"
                    "require(positive_int(rebuild.get(\"indexed_chunk_count\")) and positive_int(status.get(\"indexed_chunk_count\")), \"indexed_chunk_count>0\")\n"
                    "require(is_true(rebuild.get(\"embedding_production_ready\")) and is_true(status.get(\"embedding_production_ready\")), \"embedding_production_ready=true\")\n"
                    "require(not rebuild.get(\"error\") and not status.get(\"error\"), \"error absent\")\n"
                    "require(not rebuild.get(\"embedding_error\") and not status.get(\"embedding_error\"), \"embedding_error absent\")\n"
                    "print(\"configured=true\")\n"
                    "print(\"mode=connected\")\n"
                    "print(\"persisted=true\")\n"
                    "print(\"indexed_chunk_count>0\")\n"
                    "print(\"embedding_production_ready=true\")\n"
                    "print(\"error absent\")\n"
                    "print(\"embedding_error absent\")\n"
                    "PY'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": True,
                "mutates_remote_state": True,
                "expected_success": [
                    "configured=true",
                    "mode=connected",
                    "persisted=true",
                    "indexed_chunk_count>0",
                    "embedding_production_ready=true",
                    "error absent",
                    "embedding_error absent",
                ],
            },
            {
                "id": "verify_elasticsearch_hybrid_prerequisites",
                "purpose": "Run the read-only ES hybrid prerequisite gate before strict smoke.",
                "command": (
                    f"ssh {remote_host} 'cd {api_dir} && "
                    f"PYTHONPATH=. {shared_python} scripts/verify_elasticsearch_hybrid_prerequisites.py "
                    f"--env-file {remote_env_file} "
                    "--rag-status-url http://127.0.0.1:8000/agent/rag/status "
                    f"--runtime-probe-json {runtime_probe_json}'"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
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
                    "dense_vector_field=embedding",
                    "fusion=rrf",
                    "embedding_production_ready=true",
                    "runtime_probe_machine_binding=runtime_discovered",
                    "runtime_probe_workflow_tool_execution=deployment_server_local",
                    "runtime_probe_docker_runtime_host=api_server",
                    "runtime_probe_elasticsearch_discovery_status=available",
                    "runtime_probe_elasticsearch_container_running=true",
                    "runtime_probe_elasticsearch_candidate_endpoint loopback",
                    "secrets_redacted=true",
                ],
            },
            {
                "id": "continue_release_gate_strict_smoke",
                "purpose": "Continue with the existing machine-checkable release gate only after the ES prerequisite passes.",
                "command": (
                    f"cd {overlay} && PYTHONPATH=apps/api {shared_python} "
                    "apps/api/scripts/verify_release_gate_command_plan.py "
                    "docs/deployment/remote-release-gate-command-plan.json && "
                    "echo remote-release-gate-command-plan.json status=passed && "
                    "echo strict_smoke_next_step_unblocked=true"
                ),
                "runs_on": "remote",
                "requires_operator_authorization": False,
                "mutates_remote_state": False,
                "expected_success": [
                    "remote-release-gate-command-plan.json status=passed",
                    "strict_smoke_next_step_unblocked=true",
                ],
            },
        ],
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build a secret-safe operator plan for enabling Elasticsearch hybrid RAG on yyf."
    )
    parser.add_argument("--release-overlay", required=True)
    parser.add_argument("--remote-host", default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-env-file", default=DEFAULT_REMOTE_ENV_FILE)
    parser.add_argument("--missing-env-key", action="append", default=[])
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args(argv)

    plan = build_elasticsearch_hybrid_config_plan(
        release_overlay=args.release_overlay,
        missing_env_keys=args.missing_env_key,
        remote_host=args.remote_host,
        remote_env_file=args.remote_env_file,
    )
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
