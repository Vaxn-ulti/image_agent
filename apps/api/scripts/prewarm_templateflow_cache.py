from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


PLAN_ID = "templateflow_cache_prewarm_v1"
DEFAULT_FMRIPREP_IMAGE = "nipreps/fmriprep:25.2.5"
DEFAULT_TEMPLATES = ("MNI152NLin2009cAsym", "MNI152NLin6Asym", "OASIS30ANTs")
DEFAULT_TEMPLATEFLOW_HOME = "cache/templateflow"
DEFAULT_ATTEMPTS = 3
DEFAULT_REQUEST_TIMEOUT = 120
TEMPLATEFLOW_S3_BASE_URL = "https://templateflow.s3.amazonaws.com"
DOCKER_COMMAND_ENV = "IMAGE_AGENT_DOCKER_COMMAND"
SUDO_PASSWORD_ENV = "IMAGE_AGENT_SUDO_PASSWORD"
RUNTIME_PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
)
LOOPBACK_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1"}
DEFAULT_TEMPLATEFLOW_QUERY_SPECS = (
    {"resolution": 1, "suffix": "T1w", "extension": "nii.gz"},
    {"resolution": 2, "suffix": "T1w", "extension": "nii.gz"},
    {"resolution": 1, "desc": "brain", "suffix": "mask", "extension": "nii.gz"},
    {"resolution": 2, "desc": "brain", "suffix": "mask", "extension": "nii.gz"},
)
TEMPLATEFLOW_QUERY_SPECS_BY_TEMPLATE = {
    "MNI152NLin2009cAsym": (
        *DEFAULT_TEMPLATEFLOW_QUERY_SPECS,
        {"resolution": 2, "desc": "fMRIPrep", "suffix": "boldref", "extension": "nii.gz"},
        {"resolution": 1, "label": "brain", "suffix": "probseg", "extension": "nii.gz"},
        {"resolution": 1, "desc": "carpet", "suffix": "dseg", "extension": "nii.gz"},
        {"from": "MNI152NLin6Asym", "mode": "image", "suffix": "xfm", "extension": "h5"},
    ),
    "MNI152NLin6Asym": (
        *DEFAULT_TEMPLATEFLOW_QUERY_SPECS,
        {"from": "MNI152NLin2009cAsym", "mode": "image", "suffix": "xfm", "extension": "h5"},
    ),
    "OASIS30ANTs": (
        {"resolution": 1, "suffix": "T1w", "extension": "nii.gz"},
        {"resolution": 1, "desc": "brain", "suffix": "T1w", "extension": "nii.gz"},
        {"resolution": 1, "desc": "brain", "suffix": "mask", "extension": "nii.gz"},
    ),
}


def _reject_floating_image(image: str) -> str:
    value = (image or "").strip()
    tail = value.rsplit("/", 1)[-1]
    if not value or ":" not in tail or value.lower().endswith(":latest"):
        raise SystemExit("TemplateFlow prewarm image must be version-pinned and must not use latest")
    return value


def _safe_symbol(value: str) -> bool:
    return bool(value) and len(value) <= 120 and all(char.isalnum() or char in "_.-" for char in value)


def _templates(values: Sequence[str]) -> list[str]:
    templates = [item.strip() for item in values if item and item.strip()]
    if not templates:
        raise SystemExit("at least one TemplateFlow template is required")
    for item in templates:
        if not _safe_symbol(item):
            raise SystemExit("TemplateFlow template names must be privacy-safe symbols")
    return templates


def _command_preview(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def _templateflow_python(templates: Sequence[str]) -> str:
    query_specs = {template: _templateflow_query_specs(template) for template in templates}
    return (
        "import os\n"
        "import requests\n"
        "from templateflow import api as tflow\n"
        "request_timeout = int(os.environ.get(\"IMAGE_AGENT_TEMPLATEFLOW_REQUEST_TIMEOUT\", \"120\"))\n"
        "_original_request = requests.sessions.Session.request\n"
        "def _request_with_timeout(self, method, url, **kwargs):\n"
        "    kwargs[\"timeout\"] = max(int(kwargs.get(\"timeout\") or 0), request_timeout)\n"
        "    return _original_request(self, method, url, **kwargs)\n"
        "requests.sessions.Session.request = _request_with_timeout\n"
        f"queries_by_template = {query_specs!r}\n"
        "for template, queries in queries_by_template.items():\n"
        "    for query in queries:\n"
        "        path = tflow.get(template, **query)\n"
        "        print(path)\n"
    )


def _templateflow_query_specs(template: str) -> list[dict[str, object]]:
    specs = TEMPLATEFLOW_QUERY_SPECS_BY_TEMPLATE.get(template, DEFAULT_TEMPLATEFLOW_QUERY_SPECS)
    return [dict(item) for item in specs]


def _docker_command_prefix() -> list[str]:
    configured = os.environ.get(DOCKER_COMMAND_ENV, "").strip()
    if not configured:
        return ["docker"]
    parts = shlex.split(configured)
    if not parts or parts[-1] != "docker":
        raise SystemExit(f"{DOCKER_COMMAND_ENV} must end with docker")
    return parts


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


def _docker_command(
    *,
    templateflow_home: Path,
    image: str,
    templates: Sequence[str],
    forward_proxy_env: bool,
    network_mode: str,
    request_timeout: int,
) -> list[str]:
    use_host_network = network_mode == "host"
    if network_mode not in {"bridge", "host"}:
        raise SystemExit("network mode must be bridge or host")
    py = _templateflow_python(templates)
    proxy_env, uses_host_gateway = _container_proxy_env(rewrite_loopback=not use_host_network)
    host_gateway_args = ["--add-host", "host.docker.internal:host-gateway"] if forward_proxy_env and uses_host_gateway and not use_host_network else []
    network_args = ["--network", "host"] if use_host_network else []
    proxy_args: list[str] = []
    if forward_proxy_env:
        for name in proxy_env:
            proxy_args.extend(["-e", name])
    return [
        *_docker_command_prefix(),
        "run",
        "--rm",
        *host_gateway_args,
        *network_args,
        *proxy_args,
        "-v",
        f"{templateflow_home}:/templateflow",
        "-e",
        "TEMPLATEFLOW_HOME=/templateflow",
        "-e",
        f"IMAGE_AGENT_TEMPLATEFLOW_REQUEST_TIMEOUT={request_timeout}",
        "--entrypoint",
        "python",
        image,
        "-c",
        py,
    ]


def _templateflow_target_files(templates: Sequence[str]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for template in templates:
        for spec in _templateflow_query_specs(template):
            suffix = str(spec["suffix"])
            extension = str(spec["extension"])
            if "from" in spec:
                from_space = str(spec["from"])
                mode = str(spec.get("mode", "image"))
                filename = f"tpl-{template}_from-{from_space}_mode-{mode}_{suffix}.{extension}"
                targets.append(
                    (
                        f"{TEMPLATEFLOW_S3_BASE_URL}/tpl-{template}/{filename}",
                        f"tpl-{template}/{filename}",
                    )
                )
                continue
            resolution = int(spec["resolution"])
            desc = spec.get("desc")
            label = spec.get("label")
            desc_part = f"_desc-{desc}" if desc else ""
            label_part = f"_label-{label}" if label else ""
            filename = f"tpl-{template}_res-{resolution:02d}{desc_part}{label_part}_{suffix}.{extension}"
            targets.append(
                (
                    f"{TEMPLATEFLOW_S3_BASE_URL}/tpl-{template}/{filename}",
                    f"tpl-{template}/{filename}",
                )
            )
    return targets


def _curl_commands(*, templateflow_home: Path, templates: Sequence[str], request_timeout: int) -> list[list[str]]:
    commands: list[list[str]] = []
    for url, relative_path in _templateflow_target_files(templates):
        commands.append(
            [
                "curl",
                "--fail",
                "--location",
                "--create-dirs",
                "-C",
                "-",
                "--retry",
                "5",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--speed-limit",
                "1",
                "--speed-time",
                str(request_timeout),
                "--output",
                str(templateflow_home / relative_path),
                url,
            ]
        )
    return commands


def _redact(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9._-]{8,}", "[redacted-secret]", text or "")
    text = re.sub(r"(?i)(api[_-]?key|token|password|secret)=\S+", r"\1=[redacted-secret]", text)
    for name in RUNTIME_PROXY_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted-proxy]")
    return text


def _sudo_stdin(command: Sequence[str]) -> str | None:
    if "sudo" not in command or "-S" not in command:
        return None
    password = os.environ.get(SUDO_PASSWORD_ENV)
    if not password:
        return None
    return password + "\n"


def _delete_zero_size_files(root: Path) -> int:
    if not root.exists():
        return 0
    deleted = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_size != 0:
                continue
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def _download_env(*, direct_download: bool, forward_proxy_env: bool, network_mode: str) -> dict[str, str]:
    env = os.environ.copy()
    if direct_download:
        for name in RUNTIME_PROXY_ENV_NAMES:
            env.pop(name, None)
        return env
    if forward_proxy_env:
        proxy_env, _uses_host_gateway = _container_proxy_env(rewrite_loopback=network_mode != "host")
        env.update(proxy_env)
    return env


def _curl_output_path(command: Sequence[str]) -> Path | None:
    try:
        index = list(command).index("--output")
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return Path(command[index + 1])


def _filter_existing_curl_commands(commands: Sequence[Sequence[str]]) -> tuple[list[list[str]], int]:
    pending: list[list[str]] = []
    skipped = 0
    for command in commands:
        output_path = _curl_output_path(command)
        if output_path is not None and output_path.exists():
            try:
                if output_path.stat().st_size > 0:
                    skipped += 1
                    continue
            except OSError:
                pass
        pending.append(list(command))
    return pending, skipped


def _write_env_value(env_file: Path, key: str, value: str) -> None:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    rendered = f"{key}={value}"
    replaced = False
    output = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            output.append(rendered)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(rendered)
    env_file.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def build_prewarm_plan(
    *,
    templateflow_home: Path,
    image: str,
    templates: Sequence[str],
    env_file: Path,
    apply_changes: bool,
    forward_proxy_env: bool = False,
    network_mode: str = "bridge",
    attempts: int = DEFAULT_ATTEMPTS,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    download_method: str = "client",
    direct_download: bool = False,
) -> dict:
    resolved_home = Path(templateflow_home).expanduser()
    image = _reject_floating_image(image)
    template_names = _templates(templates)
    use_host_network = network_mode == "host"
    if network_mode not in {"bridge", "host"}:
        raise SystemExit("network mode must be bridge or host")
    if attempts < 1:
        raise SystemExit("attempts must be at least 1")
    if request_timeout < 10:
        raise SystemExit("request timeout must be at least 10 seconds")
    if download_method not in {"client", "curl"}:
        raise SystemExit("download method must be client or curl")
    proxy_env, uses_host_gateway = _container_proxy_env(rewrite_loopback=not use_host_network)
    proxy_env_names = list(proxy_env) if forward_proxy_env else []
    command = _docker_command(
        templateflow_home=resolved_home,
        image=image,
        templates=template_names,
        forward_proxy_env=forward_proxy_env,
        network_mode=network_mode,
        request_timeout=request_timeout,
    )
    curl_commands = _curl_commands(
        templateflow_home=resolved_home,
        templates=template_names,
        request_timeout=request_timeout,
    )
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply" if apply_changes else "dry_run",
        "templateflow_home": str(resolved_home),
        "env_file": str(env_file),
        "env_updates": {"IMAGE_AGENT_TEMPLATEFLOW_HOME": str(resolved_home)},
        "image": image,
        "templates": template_names,
        "network_mode": network_mode,
        "attempts": attempts,
        "request_timeout_seconds": request_timeout,
        "download_method": download_method,
        "direct_download": direct_download,
        "command": command,
        "command_preview": _command_preview(command),
        "curl_commands": curl_commands,
        "curl_command_previews": [_command_preview(item) for item in curl_commands],
        "runtime_configuration": [DOCKER_COMMAND_ENV],
        "container_proxy_forwarding": {
            "enabled": bool(proxy_env_names),
            "environment_names": proxy_env_names,
            "uses_host_gateway": bool(forward_proxy_env and uses_host_gateway and not use_host_network),
            "values_redacted": True,
        },
        "official_sources": [
            "docs/rag/vendor/templateflow_official_cache_archive_client.md",
            "docs/rag/vendor/fmriprep_official_container_usage.md",
        ],
        "secret_handling": [
            "no API keys are required for TemplateFlow cache prewarm",
            "do not write proxy URLs into scripts, env files, reports, or git",
        ],
    }


def prewarm_templateflow_cache(
    *,
    templateflow_home: Path,
    image: str,
    templates: Sequence[str],
    env_file: Path,
    apply_changes: bool,
    forward_proxy_env: bool = False,
    network_mode: str = "bridge",
    attempts: int = DEFAULT_ATTEMPTS,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    download_method: str = "client",
    direct_download: bool = False,
) -> dict:
    plan = build_prewarm_plan(
        templateflow_home=templateflow_home,
        image=image,
        templates=templates,
        env_file=env_file,
        apply_changes=apply_changes,
        forward_proxy_env=forward_proxy_env,
        network_mode=network_mode,
        attempts=attempts,
        request_timeout=request_timeout,
        download_method=download_method,
        direct_download=direct_download,
    )
    if not apply_changes:
        return plan
    Path(plan["templateflow_home"]).mkdir(parents=True, exist_ok=True)
    _write_env_value(env_file, "IMAGE_AGENT_TEMPLATEFLOW_HOME", plan["templateflow_home"])
    env = _download_env(
        direct_download=direct_download,
        forward_proxy_env=forward_proxy_env,
        network_mode=plan["network_mode"],
    )
    last_proc = None
    deleted_zero_size_files = 0
    skipped_existing_files = 0
    if download_method == "curl":
        commands, skipped_existing_files = _filter_existing_curl_commands(plan["curl_commands"])
    else:
        commands = [plan["command"]]
    completed_commands = 0
    if not commands:
        return {
            "plan_id": PLAN_ID,
            "schema_version": 1,
            "mode": "apply",
            "status": "completed",
            "templateflow_home": plan["templateflow_home"],
            "env_file": str(env_file),
            "image": plan["image"],
            "templates": plan["templates"],
            "network_mode": plan["network_mode"],
            "attempts": attempts,
            "request_timeout_seconds": request_timeout,
            "download_method": download_method,
            "direct_download": direct_download,
            "completed_commands": completed_commands,
            "skipped_existing_files": skipped_existing_files,
            "deleted_zero_size_files": deleted_zero_size_files,
            "container_proxy_forwarding": plan["container_proxy_forwarding"],
            "secrets_redacted": True,
        }
    for command in commands:
        for _attempt in range(1, attempts + 1):
            deleted_zero_size_files += _delete_zero_size_files(Path(plan["templateflow_home"]))
            last_proc = subprocess.run(
                command,
                env=env,
                input=_sudo_stdin(command),
                text=True,
                capture_output=True,
                check=False,
            )
            if last_proc.returncode == 0:
                completed_commands += 1
                break
        if last_proc is None or last_proc.returncode != 0:
            break
    if last_proc is None or last_proc.returncode != 0:
        deleted_zero_size_files += _delete_zero_size_files(Path(plan["templateflow_home"]))
        raise SystemExit(
            "TemplateFlow prewarm failed: "
            + _redact(((last_proc.stdout if last_proc else "") or "")[-500:] + "\n" + ((last_proc.stderr if last_proc else "") or "")[-500:])
        )
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply",
        "status": "completed",
        "templateflow_home": plan["templateflow_home"],
        "env_file": str(env_file),
        "image": plan["image"],
        "templates": plan["templates"],
        "network_mode": plan["network_mode"],
        "attempts": attempts,
        "request_timeout_seconds": request_timeout,
        "download_method": download_method,
        "direct_download": direct_download,
        "completed_commands": completed_commands,
        "skipped_existing_files": skipped_existing_files,
        "deleted_zero_size_files": deleted_zero_size_files,
        "container_proxy_forwarding": plan["container_proxy_forwarding"],
        "secrets_redacted": True,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Prewarm the shared TemplateFlow cache with local Docker.")
    parser.add_argument("--templateflow-home", default=os.environ.get("IMAGE_AGENT_TEMPLATEFLOW_HOME", DEFAULT_TEMPLATEFLOW_HOME))
    parser.add_argument("--image", default=DEFAULT_FMRIPREP_IMAGE)
    parser.add_argument("--template", action="append", dest="templates", default=[])
    parser.add_argument("--write-env", dest="env_file", required=True)
    parser.add_argument("--forward-proxy-env", action="store_true")
    parser.add_argument("--network-mode", choices=["bridge", "host"], default="bridge")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--request-timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT)
    parser.add_argument("--download-method", choices=["client", "curl"], default="client")
    parser.add_argument("--direct-download", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)

    report = prewarm_templateflow_cache(
        templateflow_home=Path(args.templateflow_home),
        image=args.image,
        templates=args.templates or list(DEFAULT_TEMPLATES),
        env_file=Path(args.env_file),
        apply_changes=args.apply,
        forward_proxy_env=args.forward_proxy_env,
        network_mode=args.network_mode,
        attempts=args.attempts,
        request_timeout=args.request_timeout,
        download_method=args.download_method,
        direct_download=args.direct_download,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
