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
from urllib.parse import urlsplit, urlunsplit


PLAN_ID = "local_embedding_service_setup_v1"
DEFAULT_EMBEDDING_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9"
DEFAULT_CONTAINER_NAME = "image-agent-embeddings"
DEFAULT_VOLUME_NAME = "image-agent-tei-data"
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 18081
DEFAULT_CONTAINER_PORT = 80
DEFAULT_NETWORK_MODE = "host"
DEFAULT_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_SERVED_MODEL_NAME = "image-agent-minilm-l6-v2"
DEFAULT_EMBEDDING_BASE_URL = f"http://{DEFAULT_BIND_HOST}:{DEFAULT_BIND_PORT}/v1"
DOCKER_COMMAND_ENV = "IMAGE_AGENT_DOCKER_COMMAND"
OFFICIAL_RUNTIME_SOURCES = [
    "https://huggingface.co/docs/text-embeddings-inference/en/quick_tour",
    "https://huggingface.co/docs/text-embeddings-inference/en/basic_tutorials/using_cli",
]
RUNTIME_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
LOOPBACK_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _container_proxy_value(value: str) -> tuple[str, bool]:
    parsed = urlsplit(value)
    if not parsed.scheme or parsed.hostname not in LOOPBACK_PROXY_HOSTS:
        return value, False
    netloc = "host.docker.internal"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)), True


def _container_proxy_env(*, rewrite_loopback: bool = True) -> tuple[dict[str, str], bool]:
    proxy_env: dict[str, str] = {}
    uses_host_gateway = False
    for name in RUNTIME_PROXY_ENV_NAMES:
        value = os.environ.get(name)
        if not value:
            continue
        rewritten, needs_gateway = _container_proxy_value(value) if rewrite_loopback else (value, False)
        proxy_env[name] = rewritten
        uses_host_gateway = uses_host_gateway or needs_gateway
    return proxy_env, uses_host_gateway


def _reject_floating_image(image: str) -> str:
    text = image.strip()
    if not text or text.endswith(":latest") or ":" not in text.rsplit("/", 1)[-1]:
        raise SystemExit("Embedding image must be version-pinned and must not use latest")
    return text


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


def _command_preview(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _redact_log_tail(text: str, *, limit: int = 500) -> str:
    tail = (text or "")[-limit:]
    tail = re.sub(r"Authorization:\s*Bearer\s+\S+", "[redacted-secret]", tail, flags=re.IGNORECASE)
    tail = re.sub(r"(?i)(api[_-]?key|token|password|secret)=\S+", r"\1=[redacted-secret]", tail)
    tail = re.sub(r"sk-[A-Za-z0-9._-]{8,}", "[redacted-secret]", tail)
    return tail.strip()


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


def _run_container_command(command: Sequence[str], *, rewrite_loopback: bool = True) -> subprocess.CompletedProcess:
    proxy_env, _uses_host_gateway = _container_proxy_env(rewrite_loopback=rewrite_loopback)
    env = os.environ.copy()
    env.update(proxy_env)
    proc = subprocess.run(
        list(command),
        env=env,
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


def _docker_run_command(
    *,
    image: str,
    container_name: str,
    volume_name: str,
    bind_host: str,
    bind_port: int,
    container_port: int,
    network_mode: str,
    model_id: str,
    served_model_name: str,
) -> list[str]:
    use_host_network = network_mode == "host"
    if network_mode not in {"bridge", "host"}:
        raise SystemExit("network mode must be bridge or host")
    proxy_env, uses_host_gateway = _container_proxy_env(rewrite_loopback=not use_host_network)
    host_gateway_args = ["--add-host", "host.docker.internal:host-gateway"] if uses_host_gateway and not use_host_network else []
    proxy_env_args = [part for name in proxy_env for part in ("-e", name)]
    network_args = ["--network", "host"] if use_host_network else []
    port_args = [] if use_host_network else ["-p", f"{bind_host}:{bind_port}:{container_port}"]
    served_port = bind_port if use_host_network else container_port
    return [
        *_docker_command_prefix(),
        "run",
        "-d",
        "--name",
        container_name,
        *host_gateway_args,
        *network_args,
        *port_args,
        "-v",
        f"{volume_name}:/data",
        *proxy_env_args,
        image,
        "--port",
        str(served_port),
        "--model-id",
        model_id,
        "--served-model-name",
        served_model_name,
    ]


def _env_updates(*, served_model_name: str, embedding_base_url: str) -> dict[str, str]:
    return {
        "IMAGE_AGENT_RAG_EMBEDDING_PROVIDER": "openai_compatible",
        "IMAGE_AGENT_RAG_EMBEDDING_MODEL": served_model_name,
        "IMAGE_AGENT_RAG_EMBEDDING_BASE_URL": embedding_base_url,
    }


def build_setup_plan(
    *,
    env_file: Path,
    apply_changes: bool,
    embedding_image: str = DEFAULT_EMBEDDING_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    volume_name: str = DEFAULT_VOLUME_NAME,
    bind_host: str = DEFAULT_BIND_HOST,
    bind_port: int = DEFAULT_BIND_PORT,
    container_port: int = DEFAULT_CONTAINER_PORT,
    network_mode: str = DEFAULT_NETWORK_MODE,
    model_id: str = DEFAULT_MODEL_ID,
    served_model_name: str = DEFAULT_SERVED_MODEL_NAME,
    embedding_base_url: str = DEFAULT_EMBEDDING_BASE_URL,
) -> dict:
    image = _reject_floating_image(embedding_image)
    docker_run = _docker_run_command(
        image=image,
        container_name=container_name,
        volume_name=volume_name,
        bind_host=bind_host,
        bind_port=bind_port,
        container_port=container_port,
        network_mode=network_mode,
        model_id=model_id,
        served_model_name=served_model_name,
    )
    proxy_env, uses_host_gateway = _container_proxy_env(rewrite_loopback=network_mode != "host")
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply" if apply_changes else "dry_run",
        "status": "ready_to_apply" if apply_changes else "planned",
        "env_file": str(env_file),
        "embedding_image": image,
        "container_name": container_name,
        "volume_name": volume_name,
        "bind_endpoint": embedding_base_url,
        "network_mode": network_mode,
        "model_id": model_id,
        "served_model_name": served_model_name,
        "official_runtime_sources": OFFICIAL_RUNTIME_SOURCES,
        "env_updates": _env_updates(
            served_model_name=served_model_name,
            embedding_base_url=embedding_base_url,
        ),
        "secret_handling": [
            "the local embedding container does not require committing secrets",
            "caller-supplied API keys remain in local deployment env only if supplied elsewhere",
            "JSON reports never print secret values",
        ],
        "container_proxy_forwarding": {
            "enabled": bool(proxy_env),
            "environment_names": sorted(proxy_env),
            "uses_host_gateway": uses_host_gateway,
        },
        "steps": [
            {
                "id": "inspect_docker",
                "command_preview": _command_preview(_docker_cmd("info", "--format", "{{json .ServerVersion}}")),
                "mutates_state": False,
            },
            {
                "id": "inspect_embedding_image",
                "command_preview": _command_preview(_docker_cmd("image", "inspect", image)),
                "mutates_state": False,
            },
            {
                "id": "pull_embedding_image_if_missing",
                "command_preview": _command_preview(_docker_cmd("pull", image)),
                "mutates_state": True,
            },
            {
                "id": "inspect_embedding_container",
                "command_preview": _command_preview(
                    _docker_cmd("ps", "--filter", f"name=^/{container_name}$", "--filter", "status=running")
                ),
                "mutates_state": False,
            },
            {
                "id": "start_embedding_container_if_missing",
                "command_preview": _command_preview(docker_run),
                "mutates_state": True,
            },
            {
                "id": "write_embedding_env",
                "command_preview": f"update deployment env file {env_file}",
                "mutates_state": True,
            },
            {
                "id": "verify_embedding_endpoint",
                "command_preview": f"POST {embedding_base_url.rstrip('/')}/embeddings",
                "mutates_state": False,
            },
        ],
    }


def _safe_step_status(step_id: str, status: str) -> dict[str, str]:
    return {"id": step_id, "status": status}


def _is_loopback_endpoint(url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.hostname or "").lower() in LOOPBACK_PROXY_HOSTS


def _ensure_docker_volume(volume_name: str) -> str:
    probe = subprocess.run(
        _docker_cmd("volume", "inspect", volume_name),
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        return "present"
    _run(_docker_cmd("volume", "create", volume_name))
    return "created"


def _verify_embedding_endpoint(
    *,
    embedding_base_url: str,
    served_model_name: str,
    attempts: int = 30,
    interval_seconds: float = 10.0,
) -> None:
    endpoint = embedding_base_url.rstrip("/") + "/embeddings"
    payload = json.dumps({"model": served_model_name, "input": "image agent embedding probe"}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": "Bearer image-agent-local-probe",
            "Content-Type": "application/json",
        },
    )
    last_error = "unknown"
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
            data = body.get("data") if isinstance(body, dict) else None
            first = data[0] if data else None
            embedding = first.get("embedding") if isinstance(first, dict) else None
            if isinstance(embedding, list) and embedding:
                return
            last_error = "response did not contain an embedding vector"
        except (ConnectionResetError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
        if attempt < attempts:
            time.sleep(interval_seconds)
    raise SystemExit(f"embedding endpoint probe failed after {attempts} attempts: {last_error}")


def setup_local_embedding_service(
    *,
    env_file: Path,
    apply_changes: bool = False,
    pull_missing_image: bool = True,
    start_missing_container: bool = True,
    verify_endpoint: bool = True,
    verify_attempts: int = 30,
    verify_interval_seconds: float = 10.0,
    embedding_image: str = DEFAULT_EMBEDDING_IMAGE,
    container_name: str = DEFAULT_CONTAINER_NAME,
    volume_name: str = DEFAULT_VOLUME_NAME,
    bind_host: str = DEFAULT_BIND_HOST,
    bind_port: int = DEFAULT_BIND_PORT,
    container_port: int = DEFAULT_CONTAINER_PORT,
    network_mode: str = DEFAULT_NETWORK_MODE,
    model_id: str = DEFAULT_MODEL_ID,
    served_model_name: str = DEFAULT_SERVED_MODEL_NAME,
    embedding_base_url: str = DEFAULT_EMBEDDING_BASE_URL,
) -> dict:
    plan = build_setup_plan(
        env_file=env_file,
        apply_changes=apply_changes,
        embedding_image=embedding_image,
        container_name=container_name,
        volume_name=volume_name,
        bind_host=bind_host,
        bind_port=bind_port,
        container_port=container_port,
        network_mode=network_mode,
        model_id=model_id,
        served_model_name=served_model_name,
        embedding_base_url=embedding_base_url,
    )
    if not apply_changes:
        return plan

    step_results: list[dict[str, str]] = []
    endpoint_probe_passed = False
    _run(_docker_cmd("info", "--format", "{{json .ServerVersion}}"))
    step_results.append(_safe_step_status("inspect_docker", "available"))

    image_probe = subprocess.run(
        _docker_cmd("image", "inspect", plan["embedding_image"]),
        text=True,
        capture_output=True,
        check=False,
    )
    if image_probe.returncode == 0:
        step_results.append(_safe_step_status("inspect_embedding_image", "present"))
    elif pull_missing_image:
        _run(_docker_cmd("pull", plan["embedding_image"]))
        step_results.append(_safe_step_status("pull_embedding_image_if_missing", "pulled"))
    else:
        raise SystemExit("Embedding image is missing and pull_missing_image is disabled")

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
        raise SystemExit("could not inspect embedding container safely")
    if container_probe.stdout.strip():
        step_results.append(_safe_step_status("inspect_embedding_container", "running"))
    elif start_missing_container:
        exited_probe = subprocess.run(
            [
                *_docker_command_prefix(),
                "ps",
                "--filter",
                f"name=^/{container_name}$",
                "--filter",
                "status=exited",
                "--format",
                "{{.Names}}",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if exited_probe.returncode != 0:
            raise SystemExit("could not inspect exited embedding container safely")
        if exited_probe.stdout.strip():
            _run(_docker_cmd("rm", container_name))
            step_results.append(_safe_step_status("remove_exited_embedding_container", "removed"))
        volume_status = _ensure_docker_volume(volume_name)
        step_results.append(_safe_step_status("ensure_embedding_volume", volume_status))
        _run_container_command(
            _docker_run_command(
                image=plan["embedding_image"],
                container_name=container_name,
                volume_name=volume_name,
                bind_host=bind_host,
                bind_port=bind_port,
                container_port=container_port,
                network_mode=network_mode,
                model_id=model_id,
                served_model_name=served_model_name,
            ),
            rewrite_loopback=network_mode != "host",
        )
        step_results.append(_safe_step_status("start_embedding_container_if_missing", "started"))
    else:
        raise SystemExit("Embedding container is missing and start_missing_container is disabled")

    _write_env_file(env_file, dict(plan["env_updates"]))
    step_results.append(_safe_step_status("write_embedding_env", "written"))
    if verify_endpoint:
        _verify_embedding_endpoint(
            embedding_base_url=embedding_base_url,
            served_model_name=served_model_name,
            attempts=verify_attempts,
            interval_seconds=verify_interval_seconds,
        )
        endpoint_probe_passed = True
        step_results.append(_safe_step_status("verify_embedding_endpoint", "passed"))

    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply",
        "status": "completed",
        "env_file": str(env_file),
        "embedding_image": plan["embedding_image"],
        "container_name": container_name,
        "embedding_container_name": container_name,
        "bind_endpoint": embedding_base_url,
        "embedding_endpoint_bound_to_loopback": _is_loopback_endpoint(embedding_base_url),
        "embedding_endpoint_probe_passed": endpoint_probe_passed,
        "no_latest_tags": ":latest" not in plan["embedding_image"],
        "env_key_status": {key: "set" for key in plan["env_updates"]},
        "steps": step_results,
        "secrets_redacted": True,
        "secret_values_not_logged": True,
        "secret_values_not_printed": True,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Scripted local OpenAI-compatible embedding service setup for Elasticsearch hybrid RAG."
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--embedding-image", default=DEFAULT_EMBEDDING_IMAGE)
    parser.add_argument("--container-name", default=DEFAULT_CONTAINER_NAME)
    parser.add_argument("--volume-name", default=DEFAULT_VOLUME_NAME)
    parser.add_argument("--bind-host", default=DEFAULT_BIND_HOST)
    parser.add_argument("--bind-port", type=int, default=DEFAULT_BIND_PORT)
    parser.add_argument("--network-mode", choices=["bridge", "host"], default=DEFAULT_NETWORK_MODE)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--served-model-name", default=DEFAULT_SERVED_MODEL_NAME)
    parser.add_argument("--embedding-base-url", default=DEFAULT_EMBEDDING_BASE_URL)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-pull-missing-image", action="store_true")
    parser.add_argument("--no-start-missing-container", action="store_true")
    parser.add_argument("--no-verify-endpoint", action="store_true")
    parser.add_argument("--verify-attempts", type=int, default=30)
    parser.add_argument("--verify-interval-seconds", type=float, default=10.0)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args(argv)

    report = setup_local_embedding_service(
        env_file=Path(args.env_file),
        apply_changes=args.apply,
        pull_missing_image=not args.no_pull_missing_image,
        start_missing_container=not args.no_start_missing_container,
        verify_endpoint=not args.no_verify_endpoint,
        verify_attempts=args.verify_attempts,
        verify_interval_seconds=args.verify_interval_seconds,
        embedding_image=args.embedding_image,
        container_name=args.container_name,
        volume_name=args.volume_name,
        bind_host=args.bind_host,
        bind_port=args.bind_port,
        network_mode=args.network_mode,
        model_id=args.model_id,
        served_model_name=args.served_model_name,
        embedding_base_url=args.embedding_base_url,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
