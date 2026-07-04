from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit


PLAN_ID = "image_agent_bootstrap_v1"
PINNED_WORKFLOW_IMAGES = [
    "pbfslab/deepprep:25.1.0",
    "pennlinc/qsiprep:26.0.0",
    "pennlinc/qsirecon:26.0.0",
]
PINNED_ELASTICSEARCH_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:9.4.2"
PINNED_LOCAL_EMBEDDING_IMAGE = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.9"
PINNED_FMRIPREP_IMAGE = "nipreps/fmriprep:25.2.5"
LOCAL_EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_EMBEDDING_MODEL = "image-agent-minilm-l6-v2"
LOCAL_EMBEDDING_BASE_URL = "http://127.0.0.1:18081/v1"
DEFAULT_TEMPLATEFLOW_HOME = "cache/templateflow"


def _venv_python(api_dir: Path) -> str:
    if os.name == "nt":
        return str(api_dir / ".venv" / "Scripts" / "python.exe")
    return str(api_dir / ".venv" / "bin" / "python")


def _venv_pip(api_dir: Path) -> str:
    if os.name == "nt":
        return str(api_dir / ".venv" / "Scripts" / "pip.exe")
    return str(api_dir / ".venv" / "bin" / "pip")


def _command_preview(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _env_file_value(value: str) -> str:
    return shlex.quote(str(value))


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
        normalized = key.strip()
        if normalized in remaining:
            rewritten.append(f"{normalized}={_env_file_value(remaining.pop(normalized))}")
        else:
            rewritten.append(raw)
    for key, value in remaining.items():
        rewritten.append(f"{key}={_env_file_value(value)}")
    env_file.write_text("\n".join(rewritten).rstrip() + "\n", encoding="utf-8")


def _require_embedding_config(embedding_model: str, embedding_base_url: str) -> tuple[str, str]:
    model = (embedding_model or "").strip()
    base_url = (embedding_base_url or "").strip()
    if not model or not base_url:
        raise SystemExit("embedding model and embedding base URL are required for Elasticsearch hybrid RAG setup")
    return model, base_url


def _is_public_https_origin(value: str) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if not _is_public_deployment_host(host):
        return False
    return (
        parsed.scheme == "https"
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _is_origin_without_path(value: str, *, schemes: set[str]) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme in schemes
        and bool(parsed.hostname)
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _is_private_network_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    if normalized == "0.0.0.0":
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return normalized.endswith(".local")
    return not address.is_global and not address.is_unspecified


def _is_private_network_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return _is_origin_without_path(value, schemes={"http", "https"}) and _is_private_network_host(parsed.hostname or "")


def _is_public_deployment_host(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")
    if normalized in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    try:
        return ipaddress.ip_address(normalized).is_global
    except ValueError:
        return "." in normalized and not normalized.endswith(".local")


def _deployment_scope_value(scope: str) -> str:
    normalized = (scope or "public_internet").strip().lower()
    if normalized not in {"public_internet", "private_network"}:
        raise SystemExit("deployment scope must be public_internet or private_network")
    return normalized


def _production_env_updates(
    *,
    production: bool,
    deployment_scope: str,
    cors_origins: str,
    public_base_url: str,
) -> dict[str, str]:
    if not production:
        return {}
    scope = _deployment_scope_value(deployment_scope)
    public_base = (public_base_url or "").strip()
    cors_value = (cors_origins or "").strip()
    if not public_base:
        raise SystemExit("production public base URL is required")
    if scope == "private_network":
        if not _is_private_network_origin(public_base):
            raise SystemExit("production private network API base URL must be an HTTP(S) origin without path, query, or fragment")
    elif not _is_public_https_origin(public_base):
        raise SystemExit("production public base URL must be a public HTTPS origin without path, query, or fragment")
    if not cors_value:
        raise SystemExit("production CORS origins are required")
    origins = [origin.strip() for origin in cors_value.split(",") if origin.strip()]
    if scope == "private_network":
        if not origins or any(origin == "*" or not _is_private_network_origin(origin) for origin in origins):
            raise SystemExit("production private network CORS origins must be HTTP(S) origins without path, query, or fragment")
    elif not origins or any(origin == "*" or not _is_public_https_origin(origin) for origin in origins):
        raise SystemExit("production CORS origins must be HTTPS public origins without path, query, or fragment")
    return {
        "IMAGE_AGENT_ENV": "production",
        "IMAGE_AGENT_DEPLOYMENT_SCOPE": scope,
        "IMAGE_AGENT_CORS_ORIGINS": ",".join(origins),
        "IMAGE_AGENT_PUBLIC_BASE_URL": public_base,
    }


def _docker_command_env_updates(docker_command: str | None) -> dict[str, str]:
    if docker_command is None:
        return {}
    text = docker_command.strip()
    if not text:
        raise SystemExit("docker command must be a non-empty non-interactive command")
    parts = shlex.split(text)
    if parts in (["docker"], ["sudo", "-n", "docker"]):
        return {"IMAGE_AGENT_DOCKER_COMMAND": text}
    raise SystemExit("docker command must be either 'docker' or 'sudo -n docker'")


def _is_rawchat_model_target(provider: str, base_url: str) -> bool:
    provider_name = (provider or "").strip().lower()
    host = (urlsplit(base_url).hostname or "").lower()
    return provider_name == "rawchat" or host == "rawchat.cn" or host.endswith(".rawchat.cn")


def _model_env_updates(
    *,
    model_provider: str,
    model_name: str,
    model_review_name: str,
    model_base_url: str,
    model_wire_api: str,
    model_trust_env_proxy: bool,
) -> dict[str, str]:
    values = {
        "provider": (model_provider or "").strip(),
        "name": (model_name or "").strip(),
        "review_name": (model_review_name or "").strip(),
        "base_url": (model_base_url or "").strip(),
        "wire_api": (model_wire_api or "").strip(),
    }
    if not any(values.values()):
        return {}
    required = ["provider", "name", "base_url", "wire_api"]
    missing = [key for key in required if not values[key]]
    if missing:
        raise SystemExit("model provider, model name, model base URL, and model wire API are required together")
    if values["wire_api"] not in {"responses", "chat_completions"}:
        raise SystemExit("model wire API must be either 'responses' or 'chat_completions'")
    if _is_rawchat_model_target(values["provider"], values["base_url"]) and model_trust_env_proxy:
        raise SystemExit("rawchat model gateway must use direct transport, not environment proxy")
    review_name = values["review_name"] or values["name"]
    return {
        "IMAGE_AGENT_MODEL_PROVIDER": values["provider"],
        "IMAGE_AGENT_MODEL_NAME": values["name"],
        "IMAGE_AGENT_MODEL_REVIEW_NAME": review_name,
        "IMAGE_AGENT_MODEL_BASE_URL": values["base_url"],
        "IMAGE_AGENT_MODEL_WIRE_API": values["wire_api"],
        "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY": "1" if model_trust_env_proxy else "0",
    }


def _load_strict_acceptance_verifier(repo_root: Path):
    script_path = repo_root / "apps" / "api" / "scripts" / "verify_remote_smoke_acceptance.py"
    spec = importlib.util.spec_from_file_location("verify_remote_smoke_acceptance", script_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load strict acceptance verifier: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _strict_acceptance_env_updates(
    *,
    repo_root: Path,
    strict_acceptance_json: Path | None,
    strict_acceptance_max_age_hours: float | None,
    strict_acceptance_now_utc: str,
) -> dict[str, str]:
    if strict_acceptance_json is None:
        return {}
    source_path = strict_acceptance_json.resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    verifier = _load_strict_acceptance_verifier(repo_root)
    now_utc = None
    if strict_acceptance_now_utc:
        parse_utc = getattr(verifier, "_parse_utc_timestamp", None)
        now_utc = (
            parse_utc(strict_acceptance_now_utc, key="now_utc")
            if parse_utc is not None
            else strict_acceptance_now_utc
        )
    report = verifier.verify_acceptance_payload(
        payload,
        max_age_hours=strict_acceptance_max_age_hours,
        now_utc=now_utc,
    )
    allowed_keys = {
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS",
        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID",
    }
    updates: dict[str, str] = {}
    for line in verifier.fast_launch_env_lines(report, payload):
        if "=" not in line:
            raise SystemExit("strict acceptance env line is invalid")
        key, value = line.split("=", 1)
        if key not in allowed_keys or not value or "\n" in value or "\r" in value:
            raise SystemExit("strict acceptance env line is unsafe")
        updates[key] = value
    if set(updates) != allowed_keys:
        raise SystemExit("strict acceptance env lines are incomplete")
    return updates


def _step(step_id: str, command: Sequence[str], *, cwd: Path, mutates_state: bool) -> dict:
    return {
        "id": step_id,
        "cwd": str(cwd),
        "command": [str(part) for part in command],
        "command_preview": _command_preview(command),
        "mutates_state": mutates_state,
    }


def _commands(
    *,
    repo_root: Path,
    image_agent_root: Path,
    env_file: Path,
    enable_elasticsearch_hybrid: bool,
    prepare_workflow_images: bool,
    prewarm_templateflow: bool,
    forward_templateflow_proxy_env: bool,
    templateflow_network_mode: str,
    templateflow_download_method: str,
    direct_templateflow_download: bool,
    templateflow_attempts: int,
    templateflow_request_timeout: int,
    setup_local_embedding_service: bool,
    embedding_model: str,
    embedding_base_url: str,
    skip_elasticsearch_trial_license: bool = False,
    production: bool = False,
    deployment_scope: str = "public_internet",
    production_cors_origins: str = "",
    production_public_base_url: str = "",
    strict_acceptance_json: Path | None = None,
    strict_acceptance_max_age_hours: float | None = None,
    strict_acceptance_now_utc: str = "",
    docker_command: str | None = None,
    verify_docker_command: bool = False,
    model_provider: str = "",
    model_name: str = "",
    model_review_name: str = "",
    model_base_url: str = "",
    model_wire_api: str = "",
    model_trust_env_proxy: bool = False,
    config_only: bool = False,
) -> list[tuple[str, Path, list[str], bool]]:
    if enable_elasticsearch_hybrid and setup_local_embedding_service:
        embedding_model = embedding_model or LOCAL_EMBEDDING_MODEL
        embedding_base_url = embedding_base_url or LOCAL_EMBEDDING_BASE_URL
    elif enable_elasticsearch_hybrid:
        embedding_model, embedding_base_url = _require_embedding_config(embedding_model, embedding_base_url)
    api_dir = repo_root / "apps" / "api"
    desktop_dir = repo_root / "apps" / "desktop"
    python_bin = _venv_python(api_dir)
    production_updates = _production_env_updates(
        production=production,
        deployment_scope=deployment_scope,
        cors_origins=production_cors_origins,
        public_base_url=production_public_base_url,
    )
    strict_acceptance_updates = _strict_acceptance_env_updates(
        repo_root=repo_root,
        strict_acceptance_json=strict_acceptance_json,
        strict_acceptance_max_age_hours=strict_acceptance_max_age_hours,
        strict_acceptance_now_utc=strict_acceptance_now_utc,
    )
    docker_updates = _docker_command_env_updates(docker_command)
    model_updates = _model_env_updates(
        model_provider=model_provider,
        model_name=model_name,
        model_review_name=model_review_name,
        model_base_url=model_base_url,
        model_wire_api=model_wire_api,
        model_trust_env_proxy=model_trust_env_proxy,
    )
    preflight_commands: list[tuple[str, Path, list[str], bool]] = []
    if verify_docker_command:
        command_text = docker_updates.get("IMAGE_AGENT_DOCKER_COMMAND")
        if not command_text:
            raise SystemExit("docker command is required when verifying Docker access")
        preflight_commands.append(
            (
                "verify_docker_command",
                repo_root,
                [*shlex.split(command_text), "version", "--format", "{{.Server.Version}}"],
                False,
            )
        )
    commands: list[tuple[str, Path, list[str], bool]] = [
        *preflight_commands,
        (
            "configure_image_agent_root",
            repo_root,
            ["write_env", str(env_file), "IMAGE_AGENT_ROOT", str(image_agent_root)],
            True,
        ),
        (
            "configure_image_agent_release_root",
            repo_root,
            ["write_env", str(env_file), "IMAGE_AGENT_RELEASE_ROOT", str(repo_root)],
            True,
        ),
    ]
    if production_updates:
        commands.extend(
            [
                (
                    "configure_image_agent_env",
                    repo_root,
                    ["write_env", str(env_file), "IMAGE_AGENT_ENV", production_updates["IMAGE_AGENT_ENV"]],
                    True,
                ),
                (
                    "configure_deployment_scope",
                    repo_root,
                    [
                        "write_env",
                        str(env_file),
                        "IMAGE_AGENT_DEPLOYMENT_SCOPE",
                        production_updates["IMAGE_AGENT_DEPLOYMENT_SCOPE"],
                    ],
                    True,
                ),
                (
                    "configure_production_cors_origins",
                    repo_root,
                    [
                        "write_env",
                        str(env_file),
                        "IMAGE_AGENT_CORS_ORIGINS",
                        production_updates["IMAGE_AGENT_CORS_ORIGINS"],
                    ],
                    True,
                ),
                (
                    "configure_public_base_url",
                    repo_root,
                    [
                        "write_env",
                        str(env_file),
                        "IMAGE_AGENT_PUBLIC_BASE_URL",
                        production_updates["IMAGE_AGENT_PUBLIC_BASE_URL"],
                    ],
                    True,
                ),
            ]
        )
    if strict_acceptance_updates:
        commands.extend(
            [
                (
                    "configure_strict_remote_acceptance_status",
                    repo_root,
                    [
                        "write_env",
                        str(env_file),
                        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS",
                        strict_acceptance_updates["IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_STATUS"],
                    ],
                    True,
                ),
                (
                    "configure_strict_remote_acceptance_id",
                    repo_root,
                    [
                        "write_env",
                        str(env_file),
                        "IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID",
                        strict_acceptance_updates["IMAGE_AGENT_STRICT_REMOTE_ACCEPTANCE_ID"],
                    ],
                    True,
                ),
            ]
        )
    if docker_updates:
        commands.append(
            (
                "configure_docker_command",
                repo_root,
                ["write_env", str(env_file), "IMAGE_AGENT_DOCKER_COMMAND", docker_updates["IMAGE_AGENT_DOCKER_COMMAND"]],
                True,
            )
        )
    if model_updates:
        model_step_names = {
            "IMAGE_AGENT_MODEL_PROVIDER": "configure_model_provider",
            "IMAGE_AGENT_MODEL_NAME": "configure_model_name",
            "IMAGE_AGENT_MODEL_REVIEW_NAME": "configure_model_review_name",
            "IMAGE_AGENT_MODEL_BASE_URL": "configure_model_base_url",
            "IMAGE_AGENT_MODEL_WIRE_API": "configure_model_wire_api",
            "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY": "configure_model_trust_env_proxy",
        }
        for key, value in model_updates.items():
            commands.append((model_step_names[key], repo_root, ["write_env", str(env_file), key, value], True))
    if config_only:
        return commands
    commands.extend(
        [
            ("check_python", repo_root, [sys.executable, "--version"], False),
            ("create_api_venv", api_dir, [sys.executable, "-m", "venv", str(api_dir / ".venv")], True),
            (
                "install_api_requirements",
                api_dir,
                [_venv_pip(api_dir), "install", "-r", "requirements.txt"],
                True,
            ),
            ("install_desktop_dependencies", desktop_dir, ["npm", "install"], True),
        ]
    )
    if prepare_workflow_images:
        commands.append(
            (
                "prepare_fixed_workflow_images",
                api_dir,
                [
                    python_bin,
                    "-m",
                    "app.scripts.probe_runtime_environment",
                    "--json",
                    "--prepare-missing-images",
                ],
                True,
            )
        )
    if prewarm_templateflow:
        templateflow_proxy_args = ["--forward-proxy-env"] if forward_templateflow_proxy_env else []
        templateflow_direct_args = ["--direct-download"] if direct_templateflow_download else []
        commands.append(
            (
                "prewarm_templateflow_cache",
                api_dir,
                [
                    python_bin,
                    "scripts/prewarm_templateflow_cache.py",
                    "--templateflow-home",
                    str(repo_root / DEFAULT_TEMPLATEFLOW_HOME),
                    "--image",
                    PINNED_FMRIPREP_IMAGE,
                    "--template",
                    "MNI152NLin2009cAsym",
                    "--template",
                    "MNI152NLin6Asym",
                    "--template",
                    "OASIS30ANTs",
                    "--write-env",
                    str(env_file),
                    "--network-mode",
                    templateflow_network_mode,
                    "--download-method",
                    templateflow_download_method,
                    "--attempts",
                    str(templateflow_attempts),
                    "--request-timeout",
                    str(templateflow_request_timeout),
                    *templateflow_proxy_args,
                    *templateflow_direct_args,
                    "--apply",
                ],
                True,
            )
        )
    if enable_elasticsearch_hybrid:
        if setup_local_embedding_service:
            commands.append(
                (
                    "setup_local_embedding_service",
                    api_dir,
                    [
                        python_bin,
                        "scripts/setup_local_embedding_service.py",
                        "--env-file",
                        str(env_file),
                        "--embedding-image",
                        PINNED_LOCAL_EMBEDDING_IMAGE,
                        "--network-mode",
                        "host",
                        "--model-id",
                        LOCAL_EMBEDDING_MODEL_ID,
                        "--served-model-name",
                        embedding_model,
                        "--embedding-base-url",
                        embedding_base_url,
                        "--apply",
                    ],
                    True,
                )
            )
        commands.append(
            (
                "setup_elasticsearch_hybrid_rag",
                api_dir,
                [
                    python_bin,
                    "scripts/setup_elasticsearch_hybrid_rag.py",
                    "--env-file",
                    str(env_file),
                    "--index-name",
                    "image_agent_rag_local",
                    "--embedding-provider",
                    "openai_compatible",
                    "--embedding-model",
                    embedding_model,
                    "--embedding-base-url",
                    embedding_base_url,
                    "--embedding-api-key-env",
                    "IMAGE_AGENT_RAG_EMBEDDING_API_KEY",
                    "--apply",
                    "--rebuild-rag",
                    "--verify-prerequisites",
                    "--rag-status-url",
                    "http://127.0.0.1:8000/agent/rag/status",
                    *(["--skip-start-trial-license"] if skip_elasticsearch_trial_license else []),
                ],
                True,
            )
        )
    commands.append(
        (
            "verify_local_runtime_probe",
            api_dir,
            [python_bin, "-m", "app.scripts.probe_runtime_environment", "--json"],
            False,
        )
    )
    return commands


def build_bootstrap_plan(
    *,
    repo_root: Path,
    image_agent_root: Path | None = None,
    env_file: Path,
    enable_elasticsearch_hybrid: bool,
    prepare_workflow_images: bool,
    prewarm_templateflow: bool = False,
    forward_templateflow_proxy_env: bool = False,
    templateflow_network_mode: str = "bridge",
    templateflow_download_method: str = "client",
    direct_templateflow_download: bool = False,
    templateflow_attempts: int = 3,
    templateflow_request_timeout: int = 120,
    setup_local_embedding_service: bool = False,
    embedding_model: str,
    embedding_base_url: str,
    skip_elasticsearch_trial_license: bool = False,
    production: bool = False,
    deployment_scope: str = "public_internet",
    production_cors_origins: str = "",
    production_public_base_url: str = "",
    strict_acceptance_json: Path | None = None,
    strict_acceptance_max_age_hours: float | None = None,
    strict_acceptance_now_utc: str = "",
    docker_command: str | None = None,
    verify_docker_command: bool = False,
    model_provider: str = "",
    model_name: str = "",
    model_review_name: str = "",
    model_base_url: str = "",
    model_wire_api: str = "",
    model_trust_env_proxy: bool = False,
    config_only: bool = False,
    apply_changes: bool,
) -> dict:
    image_agent_root = image_agent_root or repo_root
    commands = _commands(
        repo_root=repo_root,
        image_agent_root=image_agent_root,
        env_file=env_file,
        enable_elasticsearch_hybrid=enable_elasticsearch_hybrid,
        prepare_workflow_images=prepare_workflow_images,
        prewarm_templateflow=prewarm_templateflow,
        forward_templateflow_proxy_env=forward_templateflow_proxy_env,
        templateflow_network_mode=templateflow_network_mode,
        templateflow_download_method=templateflow_download_method,
        direct_templateflow_download=direct_templateflow_download,
        templateflow_attempts=templateflow_attempts,
        templateflow_request_timeout=templateflow_request_timeout,
        setup_local_embedding_service=setup_local_embedding_service,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        skip_elasticsearch_trial_license=skip_elasticsearch_trial_license,
        production=production,
        deployment_scope=deployment_scope,
        production_cors_origins=production_cors_origins,
        production_public_base_url=production_public_base_url,
        strict_acceptance_json=strict_acceptance_json,
        strict_acceptance_max_age_hours=strict_acceptance_max_age_hours,
        strict_acceptance_now_utc=strict_acceptance_now_utc,
        docker_command=docker_command,
        verify_docker_command=verify_docker_command,
        model_provider=model_provider,
        model_name=model_name,
        model_review_name=model_review_name,
        model_base_url=model_base_url,
        model_wire_api=model_wire_api,
        model_trust_env_proxy=model_trust_env_proxy,
        config_only=config_only,
    )
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply" if apply_changes else "dry_run",
        "repo_root": str(repo_root),
        "image_agent_root": str(image_agent_root),
        "env_file": str(env_file),
        "strict_acceptance_json": str(strict_acceptance_json.resolve()) if strict_acceptance_json else None,
        "pinned_workflow_images": PINNED_WORKFLOW_IMAGES,
        "pinned_elasticsearch_image": PINNED_ELASTICSEARCH_IMAGE,
        "pinned_local_embedding_image": PINNED_LOCAL_EMBEDDING_IMAGE,
        "pinned_fmriprep_image": PINNED_FMRIPREP_IMAGE,
        "git_script_entrypoints": [
            "scripts/bootstrap_image_agent.py",
            "apps/api/scripts/prewarm_templateflow_cache.py",
            "apps/api/scripts/setup_local_embedding_service.py",
            "apps/api/scripts/setup_elasticsearch_hybrid_rag.py",
            "apps/api/app/scripts/probe_runtime_environment.py",
        ],
        "secret_handling": [
            "supply IMAGE_AGENT_RAG_EMBEDDING_API_KEY through the local environment or secret manager",
            "supply IMAGE_AGENT_MODEL_API_KEY through the local environment or secret manager",
            "do not commit generated .env files",
            "bootstrap reports redact secret values",
        ],
        "runtime_configuration": [
            "IMAGE_AGENT_DOCKER_COMMAND",
            "IMAGE_AGENT_DEPLOYMENT_SCOPE",
            "IMAGE_AGENT_MODEL_PROVIDER",
            "IMAGE_AGENT_MODEL_NAME",
            "IMAGE_AGENT_MODEL_REVIEW_NAME",
            "IMAGE_AGENT_MODEL_BASE_URL",
            "IMAGE_AGENT_MODEL_WIRE_API",
            "IMAGE_AGENT_MODEL_TRUST_ENV_PROXY",
        ],
        "steps": [
            _step(step_id, command, cwd=cwd, mutates_state=mutates_state)
            for step_id, cwd, command, mutates_state in commands
        ],
    }


def _run(command: Sequence[str], *, cwd: Path, env_file: Path) -> subprocess.CompletedProcess:
    if command and command[0] == "write_env":
        if len(command) != 4:
            raise SystemExit(f"invalid write_env command: {_command_preview(command)}")
        _write_env_file(Path(command[1]), {str(command[2]): str(command[3])})
        return subprocess.CompletedProcess(list(command), 0, "", "")
    env = os.environ.copy()
    env["IMAGE_AGENT_ENV_FILE"] = str(env_file)
    api_dir = cwd if cwd.name == "api" else None
    if api_dir is not None:
        env["PYTHONPATH"] = str(api_dir)
    proc = subprocess.run(
        list(command),
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"bootstrap command failed: {_command_preview(command)}")
    return proc


def bootstrap_image_agent(
    *,
    repo_root: Path,
    image_agent_root: Path | None = None,
    env_file: Path,
    enable_elasticsearch_hybrid: bool,
    prepare_workflow_images: bool,
    prewarm_templateflow: bool = False,
    forward_templateflow_proxy_env: bool = False,
    templateflow_network_mode: str = "bridge",
    templateflow_download_method: str = "client",
    direct_templateflow_download: bool = False,
    templateflow_attempts: int = 3,
    templateflow_request_timeout: int = 120,
    setup_local_embedding_service: bool = False,
    embedding_model: str,
    embedding_base_url: str,
    skip_elasticsearch_trial_license: bool = False,
    production: bool = False,
    deployment_scope: str = "public_internet",
    production_cors_origins: str = "",
    production_public_base_url: str = "",
    strict_acceptance_json: Path | None = None,
    strict_acceptance_max_age_hours: float | None = None,
    strict_acceptance_now_utc: str = "",
    docker_command: str | None = None,
    verify_docker_command: bool = False,
    model_provider: str = "",
    model_name: str = "",
    model_review_name: str = "",
    model_base_url: str = "",
    model_wire_api: str = "",
    model_trust_env_proxy: bool = False,
    config_only: bool = False,
    apply_changes: bool,
) -> dict:
    image_agent_root = image_agent_root or repo_root
    plan = build_bootstrap_plan(
        repo_root=repo_root,
        image_agent_root=image_agent_root,
        env_file=env_file,
        enable_elasticsearch_hybrid=enable_elasticsearch_hybrid,
        prepare_workflow_images=prepare_workflow_images,
        prewarm_templateflow=prewarm_templateflow,
        forward_templateflow_proxy_env=forward_templateflow_proxy_env,
        templateflow_network_mode=templateflow_network_mode,
        templateflow_download_method=templateflow_download_method,
        direct_templateflow_download=direct_templateflow_download,
        templateflow_attempts=templateflow_attempts,
        templateflow_request_timeout=templateflow_request_timeout,
        setup_local_embedding_service=setup_local_embedding_service,
        embedding_model=embedding_model,
        embedding_base_url=embedding_base_url,
        skip_elasticsearch_trial_license=skip_elasticsearch_trial_license,
        production=production,
        deployment_scope=deployment_scope,
        production_cors_origins=production_cors_origins,
        production_public_base_url=production_public_base_url,
        strict_acceptance_json=strict_acceptance_json,
        strict_acceptance_max_age_hours=strict_acceptance_max_age_hours,
        strict_acceptance_now_utc=strict_acceptance_now_utc,
        docker_command=docker_command,
        verify_docker_command=verify_docker_command,
        model_provider=model_provider,
        model_name=model_name,
        model_review_name=model_review_name,
        model_base_url=model_base_url,
        model_wire_api=model_wire_api,
        model_trust_env_proxy=model_trust_env_proxy,
        config_only=config_only,
        apply_changes=apply_changes,
    )
    if not apply_changes:
        return plan
    results: list[dict[str, str]] = []
    for step in plan["steps"]:
        command = step["command"]
        _run(command, cwd=Path(step["cwd"]), env_file=env_file)
        results.append({"id": step["id"], "status": "completed"})
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply",
        "status": "completed",
        "repo_root": str(repo_root),
        "image_agent_root": str(image_agent_root),
        "env_file": str(env_file),
        "steps": results,
        "secrets_redacted": True,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Bootstrap Image Agent from a Git checkout.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--image-agent-root", default=None)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-workflow-images", action="store_true")
    parser.add_argument("--prewarm-templateflow", action="store_true")
    parser.add_argument("--forward-templateflow-proxy-env", action="store_true")
    parser.add_argument("--templateflow-network-mode", choices=["bridge", "host"], default="bridge")
    parser.add_argument("--templateflow-download-method", choices=["client", "curl"], default="client")
    parser.add_argument("--direct-templateflow-download", action="store_true")
    parser.add_argument("--templateflow-attempts", type=int, default=3)
    parser.add_argument("--templateflow-request-timeout", type=int, default=120)
    parser.add_argument("--skip-elasticsearch-hybrid", action="store_true")
    parser.add_argument("--skip-elasticsearch-trial-license", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument(
        "--deployment-scope",
        choices=["public_internet", "private_network"],
        default=os.environ.get("IMAGE_AGENT_DEPLOYMENT_SCOPE", "public_internet"),
    )
    parser.add_argument("--production-cors-origins", default=os.environ.get("IMAGE_AGENT_CORS_ORIGINS", ""))
    parser.add_argument("--production-public-base-url", default=os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""))
    parser.add_argument("--strict-acceptance-json", default=None)
    parser.add_argument("--strict-acceptance-max-age-hours", type=float, default=None)
    parser.add_argument("--strict-acceptance-now-utc", default="")
    parser.add_argument("--docker-command", default=None)
    parser.add_argument("--verify-docker-command", action="store_true")
    parser.add_argument("--model-provider", default="")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--model-review-name", default="")
    parser.add_argument("--model-base-url", default="")
    parser.add_argument("--model-wire-api", choices=["responses", "chat_completions"], default="")
    parser.add_argument("--model-trust-env-proxy", action="store_true")
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--setup-local-embedding-service", action="store_true")
    parser.add_argument("--embedding-model", default=os.environ.get("IMAGE_AGENT_RAG_EMBEDDING_MODEL", ""))
    parser.add_argument("--embedding-base-url", default=os.environ.get("IMAGE_AGENT_RAG_EMBEDDING_BASE_URL", ""))
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    image_agent_root = Path(args.image_agent_root).resolve() if args.image_agent_root else repo_root
    env_file = Path(args.env_file).resolve() if args.env_file else repo_root / ".env"
    strict_acceptance_json = Path(args.strict_acceptance_json).resolve() if args.strict_acceptance_json else None
    report = bootstrap_image_agent(
        repo_root=repo_root,
        image_agent_root=image_agent_root,
        env_file=env_file,
        enable_elasticsearch_hybrid=not args.skip_elasticsearch_hybrid,
        prepare_workflow_images=not args.skip_workflow_images,
        prewarm_templateflow=args.prewarm_templateflow,
        forward_templateflow_proxy_env=args.forward_templateflow_proxy_env,
        templateflow_network_mode=args.templateflow_network_mode,
        templateflow_download_method=args.templateflow_download_method,
        direct_templateflow_download=args.direct_templateflow_download,
        templateflow_attempts=args.templateflow_attempts,
        templateflow_request_timeout=args.templateflow_request_timeout,
        setup_local_embedding_service=args.setup_local_embedding_service,
        embedding_model=args.embedding_model,
        embedding_base_url=args.embedding_base_url,
        skip_elasticsearch_trial_license=args.skip_elasticsearch_trial_license,
        production=args.production,
        deployment_scope=args.deployment_scope,
        production_cors_origins=args.production_cors_origins,
        production_public_base_url=args.production_public_base_url,
        strict_acceptance_json=strict_acceptance_json,
        strict_acceptance_max_age_hours=args.strict_acceptance_max_age_hours,
        strict_acceptance_now_utc=args.strict_acceptance_now_utc,
        docker_command=args.docker_command,
        verify_docker_command=args.verify_docker_command,
        model_provider=args.model_provider,
        model_name=args.model_name,
        model_review_name=args.model_review_name,
        model_base_url=args.model_base_url,
        model_wire_api=args.model_wire_api,
        model_trust_env_proxy=args.model_trust_env_proxy,
        config_only=args.config_only,
        apply_changes=args.apply,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
