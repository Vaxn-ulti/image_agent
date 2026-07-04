from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path


PLAN_ID = "elasticsearch_hybrid_rag_setup_v1"
DEFAULT_ELASTICSEARCH_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:9.4.2"
DEFAULT_CONTAINER_NAME = "image-agent-es"
DEFAULT_NETWORK_NAME = "image-agent-elastic"
DEFAULT_VOLUME_NAME = "image-agent-es-data"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 9200
DEFAULT_ELASTICSEARCH_URL = f"http://{DEFAULT_BIND_HOST}:{DEFAULT_BIND_PORT}"
DEFAULT_MEMORY = "2g"
OFFICIAL_RUNTIME_SOURCES = [
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker",
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-basic",
    "https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-docker-prod",
    "https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-license-post-start-trial",
]
SECRET_ENV_KEYS = {
    "IMAGE_AGENT_ELASTICSEARCH_API_KEY",
    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY",
}
DOCKER_COMMAND_ENV = "IMAGE_AGENT_DOCKER_COMMAND"
EMBEDDING_MODEL_DEFAULT = "text-embedding-3-small"
EMBEDDING_MODEL_SOURCE_KEYS = [
    "IMAGE_AGENT_RAG_EMBEDDING_MODEL",
    "OPENAI_EMBEDDING_MODEL",
]
EMBEDDING_BASE_URL_SOURCE_KEYS = [
    "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL",
    "IMAGE_AGENT_MODEL_BASE_URL",
    "OPENAI_BASE_URL",
    "RAWCHAT_BASE_URL",
    "KRILL_BASE_URL",
]
EMBEDDING_API_KEY_SOURCE_KEYS = [
    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY",
    "IMAGE_AGENT_MODEL_API_KEY",
    "OPENAI_API_KEY",
    "RAWCHAT_API_KEY",
    "KRILL_API_KEY",
]
LOCAL_PLACEHOLDER_EMBEDDING_MODELS = {"local-token-hash-v1"}


def _reject_floating_image(image: str) -> str:
    text = image.strip()
    if not text or text.endswith(":latest") or ":" not in text.rsplit("/", 1)[-1]:
        raise SystemExit("Elasticsearch image must be version-pinned and must not use latest")
    return text


def _load_env_values(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    for key, value in os.environ.items():
        if value and key not in values:
            values[key] = value
    return values


def _first_env_value(values: dict[str, str], keys: Sequence[str]) -> tuple[str, str | None]:
    for key in keys:
        value = (values.get(key) or "").strip()
        if value:
            return value, key
    return "", None


def _first_non_placeholder_embedding_model(values: dict[str, str]) -> tuple[str, str | None]:
    for key in EMBEDDING_MODEL_SOURCE_KEYS:
        value = (values.get(key) or "").strip()
        if value and value not in LOCAL_PLACEHOLDER_EMBEDDING_MODELS:
            return value, key
    return "", None


def _derive_embedding_config(
    *,
    env_file: Path,
    embedding_model: str,
    embedding_base_url: str,
    derive_embedding_from_env: bool,
) -> tuple[str, str, dict[str, str]]:
    if not derive_embedding_from_env:
        model, base_url = _require_embedding_config(embedding_model, embedding_base_url)
        return model, base_url, {"model": "argument", "base_url": "argument", "api_key": "not_inspected"}
    values = _load_env_values(env_file)
    model = (embedding_model or "").strip()
    model_source = "argument" if model else None
    if not model:
        model, model_source = _first_non_placeholder_embedding_model(values)
    if not model:
        model = EMBEDDING_MODEL_DEFAULT
        model_source = "default_text_embedding_3_small"
    base_url = (embedding_base_url or "").strip()
    base_url_source = "argument" if base_url else None
    if not base_url:
        base_url, base_url_source = _first_env_value(values, EMBEDDING_BASE_URL_SOURCE_KEYS)
    _require_embedding_config(model, base_url)
    _api_key, api_key_source = _first_env_value(values, EMBEDDING_API_KEY_SOURCE_KEYS)
    return model, base_url, {
        "model": str(model_source),
        "base_url": str(base_url_source),
        "api_key": "existing_runtime_fallback_present" if api_key_source else "missing",
    }


def _require_embedding_config(embedding_model: str, embedding_base_url: str) -> tuple[str, str]:
    model = (embedding_model or "").strip()
    base_url = (embedding_base_url or "").strip()
    if not model or not base_url:
        raise SystemExit("embedding model and embedding base URL are required for Elasticsearch hybrid RAG setup")
    return model, base_url


def _command_preview(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _redact_log_tail(text: str, *, limit: int = 500) -> str:
    tail = (text or "")[-limit:]
    tail = re.sub(r"Authorization:\s*Bearer\s+\S+", "[redacted-secret]", tail, flags=re.IGNORECASE)
    tail = re.sub(r"(?i)(api[_-]?key|token|password|secret)=\S+", r"\1=[redacted-secret]", tail)
    tail = re.sub(r"sk-[A-Za-z0-9._-]{8,}", "[redacted-secret]", tail)
    return tail.strip()


def _docker_command_prefix() -> list[str]:
    configured = os.environ.get(DOCKER_COMMAND_ENV, "").strip()
    if not configured:
        return ["docker"]
    parts = shlex.split(configured)
    if not parts or parts[-1] != "docker":
        raise SystemExit(f"{DOCKER_COMMAND_ENV} must end with docker")
    return parts


def _docker_cmd(*args: str) -> list[str]:
    return [*_docker_command_prefix(), *args]


def _docker_run_command(
    *,
    image: str,
    container_name: str,
    network_name: str,
    volume_name: str,
    bind_host: str,
    bind_port: int,
    memory: str,
) -> list[str]:
    return [
        *_docker_command_prefix(),
        "run",
        "-d",
        "--name",
        container_name,
        "--network",
        network_name,
        "-p",
        f"{bind_host}:{bind_port}:9200",
        "-e",
        "discovery.type=single-node",
        "-e",
        "xpack.security.enabled=false",
        "-e",
        "ES_JAVA_OPTS=-Xms1g -Xmx1g",
        "--memory",
        memory,
        "-v",
        f"{volume_name}:/usr/share/elasticsearch/data",
        image,
    ]


def _trial_license_endpoint(elasticsearch_url: str) -> str:
    return f"{elasticsearch_url.rstrip('/')}/_license/start_trial?acknowledge=true"


def _start_trial_license(elasticsearch_url: str, *, attempts: int = 30, delay_seconds: float = 2.0) -> dict[str, str]:
    endpoint = _trial_license_endpoint(elasticsearch_url)
    last_error = ""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(endpoint, data=b"", method="POST")
        try:
            with opener.open(request, timeout=10) as response:
                raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw.strip() else {}
            trial_was_started = payload.get("trial_was_started")
            acknowledged = payload.get("acknowledged")
            if trial_was_started is True:
                status = "started"
            elif trial_was_started is False:
                status = "already_started_or_unavailable"
            elif acknowledged is True:
                status = "acknowledged"
            else:
                status = "accepted"
            return {
                "status": status,
                "trial_was_started": str(trial_was_started).lower(),
                "acknowledged": str(acknowledged).lower(),
            }
        except urllib.error.HTTPError as exc:
            body = _redact_log_tail(exc.read().decode("utf-8", errors="replace"))
            raise SystemExit(f"Elasticsearch trial license start failed: HTTP {exc.code}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = _redact_log_tail(str(exc))
            if attempt == attempts:
                break
            time.sleep(delay_seconds)
    raise SystemExit(f"Elasticsearch trial license start failed after {attempts} attempts: {last_error}")


def _env_updates(
    *,
    index_name: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_base_url: str,
    elasticsearch_url: str,
) -> dict[str, str]:
    return {
        "IMAGE_AGENT_ELASTICSEARCH_URL": elasticsearch_url,
        "IMAGE_AGENT_ELASTICSEARCH_INDEX": index_name,
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": embedding_provider,
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL": embedding_model,
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL": embedding_base_url,
    }


def build_setup_plan(
    *,
    env_file: Path,
    index_name: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_base_url: str,
    apply_changes: bool,
    derive_embedding_from_env: bool = False,
    elasticsearch_image: str = DEFAULT_ELASTICSEARCH_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    network_name: str = DEFAULT_NETWORK_NAME,
    volume_name: str = DEFAULT_VOLUME_NAME,
    bind_host: str = DEFAULT_BIND_HOST,
    bind_port: int = DEFAULT_BIND_PORT,
    memory: str = DEFAULT_MEMORY,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    start_trial_license: bool = True,
) -> dict:
    image = _reject_floating_image(elasticsearch_image)
    embedding_model, embedding_base_url, embedding_config_source = _derive_embedding_config(
        env_file=env_file,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        derive_embedding_from_env=derive_embedding_from_env,
    )
    docker_run = _docker_run_command(
        image=image,
        container_name=container_name,
        network_name=network_name,
        volume_name=volume_name,
        bind_host=bind_host,
        bind_port=bind_port,
        memory=memory,
    )
    env_updates = _env_updates(
        index_name=index_name,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        elasticsearch_url=elasticsearch_url,
    )
    steps = [
        {
            "id": "inspect_docker",
            "command_preview": _command_preview(_docker_cmd("info", "--format", "{{json .ServerVersion}}")),
            "mutates_state": False,
        },
        {
            "id": "inspect_elasticsearch_image",
            "command_preview": _command_preview(_docker_cmd("image", "inspect", image)),
            "mutates_state": False,
        },
        {
            "id": "pull_elasticsearch_image_if_missing",
            "command_preview": _command_preview(_docker_cmd("pull", image)),
            "mutates_state": True,
        },
        {
            "id": "inspect_elasticsearch_container",
            "command_preview": _command_preview(
                _docker_cmd("ps", "--filter", f"name=^/{container_name}$", "--filter", "status=running")
            ),
            "mutates_state": False,
        },
        {
            "id": "start_elasticsearch_container_if_missing",
            "command_preview": _command_preview(docker_run),
            "mutates_state": True,
        },
    ]
    if start_trial_license:
        steps.append(
            {
                "id": "start_elasticsearch_trial_license",
                "command_preview": f"POST {_trial_license_endpoint(elasticsearch_url)}",
                "mutates_state": True,
            }
        )
    steps.extend(
        [
            {
                "id": "write_elasticsearch_hybrid_env",
                "command_preview": f"update deployment env file {env_file}",
                "mutates_state": True,
            },
            {
                "id": "rebuild_elasticsearch_hybrid_rag",
                "command_preview": "python -c 'from app.agent.status import rebuild_rag_index; rebuild_rag_index(...)'",
                "mutates_state": True,
            },
            {
                "id": "verify_elasticsearch_hybrid_prerequisites",
                "command_preview": "python verify_elasticsearch_hybrid_prerequisites.py --env-file <env>",
                "mutates_state": False,
            },
        ]
    )
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply" if apply_changes else "dry_run",
        "status": "ready_to_apply" if apply_changes else "planned",
        "env_file": str(env_file),
        "elasticsearch_image": image,
        "container_name": container_name,
        "network_name": network_name,
        "volume_name": volume_name,
        "bind_endpoint": elasticsearch_url,
        "official_runtime_sources": OFFICIAL_RUNTIME_SOURCES,
        "embedding_config_source": embedding_config_source,
        "env_updates": env_updates,
        "start_trial_license": start_trial_license,
        "trial_license_endpoint": _trial_license_endpoint(elasticsearch_url),
        "secret_handling": [
            "read optional embedding API key from a caller-provided environment variable",
            "write secrets only to the local deployment env file when explicitly supplied",
            "never print secret values in JSON reports",
        ],
        "steps": steps,
    }


def _run(command: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = _redact_log_tail(getattr(proc, "stderr", "") or getattr(proc, "stdout", ""))
        suffix = f": {err}" if err else ""
        raise SystemExit(f"command failed: {_command_preview(command)}{suffix}")
    return proc


def _write_env_file(env_file: Path, updates: dict[str, str]) -> None:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    remaining = dict(updates)
    rewritten: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            rewritten.append(raw)
            continue
        key, _value = raw.split("=", 1)
        key = key.strip()
        if key in remaining:
            rewritten.append(f"{key}={remaining.pop(key)}")
        else:
            rewritten.append(raw)
    for key, value in remaining.items():
        rewritten.append(f"{key}={value}")
    env_file.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def _safe_step_status(step_id: str, status: str) -> dict[str, str]:
    return {"id": step_id, "status": status}


def _normalize_trial_license_status(status: str) -> str:
    if status in {"started", "already_started_or_unavailable", "acknowledged", "accepted"}:
        return "started_or_already_started"
    if status:
        return status
    return "unknown"


def _is_loopback_bind(bind_host: str, elasticsearch_url: str) -> bool:
    host = (bind_host or "").strip().lower()
    endpoint = (elasticsearch_url or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"} and (
        endpoint.startswith("http://127.0.0.1:")
        or endpoint.startswith("http://localhost:")
        or endpoint.startswith("http://[::1]:")
    )


def _ensure_docker_resource(kind: str, name: str) -> str:
    inspect = subprocess.run(
        _docker_cmd(kind, "inspect", name),
        text=True,
        capture_output=True,
        check=False,
    )
    if inspect.returncode == 0:
        return "present"
    _run(_docker_cmd(kind, "create", name))
    return "created"


def setup_elasticsearch_hybrid_rag(
    *,
    env_file: Path,
    index_name: str,
    embedding_provider: str,
    embedding_model: str,
    embedding_base_url: str,
    derive_embedding_from_env: bool = False,
    embedding_api_key_env: str | None = None,
    apply_changes: bool = False,
    pull_missing_image: bool = True,
    start_missing_container: bool = True,
    rebuild_rag: bool = False,
    verify_prerequisites: bool = False,
    rag_status_url: str | None = None,
    runtime_probe_json: Path | None = None,
    project_root: Path | None = None,
    python_executable: str | None = None,
    elasticsearch_image: str = DEFAULT_ELASTICSEARCH_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    network_name: str = DEFAULT_NETWORK_NAME,
    volume_name: str = DEFAULT_VOLUME_NAME,
    bind_host: str = DEFAULT_BIND_HOST,
    bind_port: int = DEFAULT_BIND_PORT,
    memory: str = DEFAULT_MEMORY,
    elasticsearch_url: str = DEFAULT_ELASTICSEARCH_URL,
    start_trial_license: bool = True,
) -> dict:
    plan = build_setup_plan(
        env_file=env_file,
        index_name=index_name,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        derive_embedding_from_env=derive_embedding_from_env,
        apply_changes=apply_changes,
        elasticsearch_image=elasticsearch_image,
        container_name=container_name,
        network_name=network_name,
        volume_name=volume_name,
        bind_host=bind_host,
        bind_port=bind_port,
        memory=memory,
        elasticsearch_url=elasticsearch_url,
        start_trial_license=start_trial_license,
    )
    if not apply_changes:
        return plan

    step_results: list[dict[str, str]] = []
    trial_license_status = "skipped"
    _run(_docker_cmd("info", "--format", "{{json .ServerVersion}}"))
    step_results.append(_safe_step_status("inspect_docker", "available"))

    image_probe = subprocess.run(
        _docker_cmd("image", "inspect", plan["elasticsearch_image"]),
        text=True,
        capture_output=True,
        check=False,
    )
    if image_probe.returncode == 0:
        step_results.append(_safe_step_status("inspect_elasticsearch_image", "present"))
    elif pull_missing_image:
        _run(_docker_cmd("pull", plan["elasticsearch_image"]))
        step_results.append(_safe_step_status("pull_elasticsearch_image_if_missing", "pulled"))
    else:
        raise SystemExit("Elasticsearch image is missing and pull_missing_image is disabled")

    container_probe = subprocess.run(
        [
            *_docker_command_prefix(),
            "ps",
            "--filter",
            f"name=^/{container_name}$",
            "--filter",
            "status=running",
            "--format",
            "{{.Names}}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if container_probe.returncode != 0:
        raise SystemExit("could not inspect Elasticsearch container safely")
    if container_probe.stdout.strip():
        step_results.append(_safe_step_status("inspect_elasticsearch_container", "running"))
    elif start_missing_container:
        network_status = _ensure_docker_resource("network", network_name)
        volume_status = _ensure_docker_resource("volume", volume_name)
        step_results.append(_safe_step_status("ensure_elasticsearch_network", network_status))
        step_results.append(_safe_step_status("ensure_elasticsearch_volume", volume_status))
        _run(
            _docker_run_command(
                image=plan["elasticsearch_image"],
                container_name=container_name,
                network_name=network_name,
                volume_name=volume_name,
                bind_host=bind_host,
                bind_port=bind_port,
                memory=memory,
            )
        )
        step_results.append(_safe_step_status("start_elasticsearch_container_if_missing", "started"))
    else:
        raise SystemExit("Elasticsearch container is missing and start_missing_container is disabled")

    if start_trial_license:
        license_status = _start_trial_license(elasticsearch_url)
        raw_trial_license_status = license_status.get("status") or "completed"
        trial_license_status = _normalize_trial_license_status(raw_trial_license_status)
        step_results.append(
            _safe_step_status(
                "start_elasticsearch_trial_license",
                raw_trial_license_status,
            )
        )

    updates = dict(plan["env_updates"])
    if embedding_api_key_env:
        secret_value = os.environ.get(embedding_api_key_env, "").strip()
        if secret_value:
            updates["IMAGE_AGENT_RAG_EMBEDDING_API_KEY"] = secret_value
    _write_env_file(env_file, updates)
    step_results.append(_safe_step_status("write_elasticsearch_hybrid_env", "written"))

    script_dir = Path(__file__).resolve().parent
    api_dir = script_dir.parent
    root = project_root or api_dir.parents[1]
    python_bin = python_executable or sys.executable

    if rebuild_rag:
        rebuild_code = (
            "from pathlib import Path\n"
            "from app.agent.status import rebuild_rag_index\n"
            f"rebuild_rag_index(Path({str(root)!r}))\n"
        )
        _run([python_bin, "-c", rebuild_code], cwd=api_dir)
        step_results.append(_safe_step_status("rebuild_elasticsearch_hybrid_rag", "completed"))

    if verify_prerequisites:
        command = [
            python_bin,
            "verify_elasticsearch_hybrid_prerequisites.py",
            "--env-file",
            str(env_file),
        ]
        if rag_status_url:
            command.extend(["--rag-status-url", rag_status_url])
        if runtime_probe_json:
            command.extend(["--runtime-probe-json", str(runtime_probe_json)])
        _run(command, cwd=script_dir)
        step_results.append(_safe_step_status("verify_elasticsearch_hybrid_prerequisites", "passed"))

    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply",
        "status": "completed",
        "env_file": str(env_file),
        "elasticsearch_image": plan["elasticsearch_image"],
        "container_name": container_name,
        "elastic_container_name": container_name,
        "bind_endpoint": elasticsearch_url,
        "elastic_endpoint_bound_to_loopback": _is_loopback_bind(bind_host, elasticsearch_url),
        "no_latest_tags": ":latest" not in plan["elasticsearch_image"],
        "env_key_status": {key: "set" for key in plan["env_updates"]},
        "elasticsearch_trial_license_status": trial_license_status,
        "steps": step_results,
        "secrets_redacted": True,
        "secret_values_not_logged": True,
        "secret_values_not_printed": True,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Scripted bootstrap for Elasticsearch hybrid RAG using local Docker and deployment env files."
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--index-name", required=True)
    parser.add_argument("--embedding-provider", default="openai_compatible")
    parser.add_argument("--embedding-model", default="")
    parser.add_argument("--embedding-base-url", default="")
    parser.add_argument(
        "--derive-embedding-from-env",
        action="store_true",
        help="Derive RAG embedding model/base URL from deployment env when explicit values are absent.",
    )
    parser.add_argument("--embedding-api-key-env", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-pull-missing-image", action="store_true")
    parser.add_argument("--no-start-missing-container", action="store_true")
    parser.add_argument("--skip-start-trial-license", action="store_true")
    parser.add_argument("--rebuild-rag", action="store_true")
    parser.add_argument("--verify-prerequisites", action="store_true")
    parser.add_argument("--rag-status-url", default=None)
    parser.add_argument("--runtime-probe-json", default=None)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args(argv)

    report = setup_elasticsearch_hybrid_rag(
        env_file=Path(args.env_file),
        index_name=args.index_name,
        embedding_provider=args.embedding_provider,
        embedding_model=args.embedding_model,
        embedding_base_url=args.embedding_base_url,
        derive_embedding_from_env=args.derive_embedding_from_env,
        embedding_api_key_env=args.embedding_api_key_env,
        apply_changes=args.apply,
        pull_missing_image=not args.no_pull_missing_image,
        start_missing_container=not args.no_start_missing_container,
        start_trial_license=not args.skip_start_trial_license,
        rebuild_rag=args.rebuild_rag,
        verify_prerequisites=args.verify_prerequisites,
        rag_status_url=args.rag_status_url,
        runtime_probe_json=Path(args.runtime_probe_json) if args.runtime_probe_json else None,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
