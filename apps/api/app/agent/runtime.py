from __future__ import annotations

import os
import json
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from app.services.runtime_overrides import main_patch_attr

DOCKER_COMMAND_ENV = "IMAGE_AGENT_DOCKER_COMMAND"

try:
    from app.workflows.pipeline import inspect_runtime
    from app.workflows.recovery import list_image_agent_containers
except ImportError:

    def inspect_runtime() -> dict:
        return {"error": "pipeline runner missing", "workflows": {}}

    def list_image_agent_containers():
        return []


def list_elasticsearch_containers() -> list[dict]:
    output = subprocess.check_output(
        [*_docker_command_prefix(), "ps", "-a", "--format", "{{json .}}"],
        stderr=subprocess.STDOUT,
        timeout=10,
    )
    if isinstance(output, bytes):
        text = output.decode("utf-8", errors="replace")
    else:
        text = str(output)
    containers: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        image = str(row.get("Image") or "")
        name = str(row.get("Names") or row.get("Name") or "")
        labels = str(row.get("Labels") or "")
        if not _looks_like_elasticsearch_container(image=image, name=name, labels=labels):
            continue
        containers.append(
            {
                "name": name,
                "image": image,
                "state": str(row.get("State") or row.get("Status") or ""),
                "ports": str(row.get("Ports") or ""),
            }
        )
    return containers


def _docker_command_prefix() -> list[str]:
    configured = os.environ.get(DOCKER_COMMAND_ENV, "").strip()
    if not configured:
        return ["docker"]
    parts = shlex.split(configured)
    if not parts or parts[-1] != "docker":
        raise RuntimeError(f"{DOCKER_COMMAND_ENV} must end with docker")
    return parts


def _looks_like_elasticsearch_container(*, image: str, name: str, labels: str) -> bool:
    text = " ".join([image, name, labels]).lower()
    return "elasticsearch" in text or "elastic.co/elasticsearch" in text


def _workflow_probe(workflow_type: str, workflow: dict) -> dict:
    image = str(workflow.get("image") or "")
    return {
        "workflow_type": workflow_type,
        "available": workflow.get("available") is True,
        **({"image": image} if image else {}),
        **({"pull_attempted": workflow["pull_attempted"] is True} if isinstance(workflow.get("pull_attempted"), bool) else {}),
        **({"pull_status": str(workflow["pull_status"])} if workflow.get("pull_status") in {"not_required", "disabled", "pulled", "failed", "pulled_but_inspect_failed"} else {}),
    }


def _safe_runtime_status(status: dict) -> dict:
    safe = {
        key: value
        for key, value in status.items()
        if key not in {"fs_license_path", "workflows"}
    }
    safe["workflows"] = {
        workflow_type: _workflow_probe(workflow_type, workflow)
        for workflow_type, workflow in (status.get("workflows") or {}).items()
        if isinstance(workflow, dict)
    }
    return safe


def _resource_probe(status: dict) -> dict:
    disk = shutil.disk_usage(os.getcwd())
    total_gb = max(1, round(disk.total / (1024**3)))
    free_gb = max(0, round(disk.free / (1024**3)))
    return {
        "cpu_count": os.cpu_count() or 1,
        "disk_total_gb": total_gb,
        "disk_free_gb": free_gb,
        "fs_license_configured": "fs_license_exists" in status,
        "fs_license_exists": status.get("fs_license_exists") is True,
    }


def _runtime_preparation_probe(status: dict) -> dict:
    preparation = status.get("runtime_preparation") if isinstance(status.get("runtime_preparation"), dict) else {}
    setting = preparation.get("setting")
    safe_setting = (
        str(setting)
        if setting == "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES"
        else "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES"
    )
    return {
        "auto_pull_missing_images": preparation.get("auto_pull_missing_images") is True,
        "setting": safe_setting,
        "pull_attempted_count": _safe_nonnegative_int(preparation.get("pull_attempted_count")),
        "pull_succeeded_count": _safe_nonnegative_int(preparation.get("pull_succeeded_count")),
        "pull_failed_count": _safe_nonnegative_int(preparation.get("pull_failed_count")),
    }


def _safe_nonnegative_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _elasticsearch_probe() -> dict:
    url = os.environ.get("IMAGE_AGENT_ELASTICSEARCH_URL", "").strip()
    url_configured = bool(url)
    endpoint_probe = (
        _probe_elasticsearch_endpoint(
            url=url,
            api_key=os.environ.get("IMAGE_AGENT_ELASTICSEARCH_API_KEY", "").strip(),
        )
        if url_configured
        else {"status": "not_configured", "reachable": False, "proxy_env_trusted": False}
    )
    discovery = _elasticsearch_runtime_discovery()
    return {
        "configured": url_configured,
        "reachable": endpoint_probe.get("reachable") is True,
        "endpoint_configured": url_configured,
        "endpoint_source": "env_redacted" if url_configured else "not_configured",
        "endpoint_probe": endpoint_probe,
        "runtime_discovery": discovery,
    }


def _default_elasticsearch_opener():
    return build_opener(ProxyHandler({}))


def _probe_elasticsearch_endpoint(
    *,
    url: str,
    api_key: str,
    timeout_seconds: float = 2.0,
    opener_factory: Callable[[], Any] = _default_elasticsearch_opener,
) -> dict:
    target = _elasticsearch_probe_target(url)
    if not target:
        return {
            "status": "unreachable",
            "reachable": False,
            "error_type": "InvalidURL",
            "proxy_env_trusted": False,
        }
    request = Request(target, headers={"User-Agent": "image-agent-elasticsearch-runtime-probe/1"})
    if api_key:
        request.add_header("Authorization", f"ApiKey {api_key}")
    opener = opener_factory()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", 0) or 0)
    except HTTPError as exc:
        status_code = int(exc.code)
    except (OSError, URLError) as exc:
        return {
            "status": "unreachable",
            "reachable": False,
            "error_type": type(exc).__name__,
            "proxy_env_trusted": False,
        }
    reachable = 100 <= status_code < 500
    return {
        "status": "reachable" if reachable else "unreachable",
        "reachable": reachable,
        "http_status": status_code,
        "proxy_env_trusted": False,
    }


def _elasticsearch_probe_target(url: str) -> str | None:
    text = (url or "").strip()
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return text.rstrip("/") + "/"


def _elasticsearch_runtime_discovery() -> dict:
    lister = main_patch_attr("list_elasticsearch_containers", list_elasticsearch_containers)
    try:
        containers = lister()
    except Exception:
        return {
            "scope": "local_docker_elasticsearch",
            "status": "unavailable",
            "count": 0,
            "running_count": 0,
            "container_running": False,
        }
    safe_containers = [container for container in containers if isinstance(container, dict)]
    running = [
        container
        for container in safe_containers
        if str(container.get("state") or "").lower() == "running"
        or str(container.get("status") or "").lower().startswith("up")
    ]
    candidate_endpoint = _candidate_elasticsearch_endpoint(running or safe_containers)
    return {
        "scope": "local_docker_elasticsearch",
        "status": "available",
        "count": len(safe_containers),
        "running_count": len(running),
        **({"candidate_endpoint": candidate_endpoint} if candidate_endpoint else {}),
        **({"candidate_endpoint_source": "container_port_mapping"} if candidate_endpoint else {}),
        "container_running": bool(running),
    }


def _candidate_elasticsearch_endpoint(containers: list[dict]) -> str | None:
    for container in containers:
        ports = container.get("ports")
        values = ports if isinstance(ports, list) else [ports]
        for value in values:
            text = str(value or "")
            if "9200" not in text:
                continue
            match = re.search(r"(?P<host>(?:127\.0\.0\.1|0\.0\.0\.0|localhost)):(?P<port>\d+)->9200/tcp", text)
            if match:
                port = match.group("port")
                return f"http://127.0.0.1:{port}"
            if re.search(r"(^|[^\d])9200/tcp", text):
                return "http://127.0.0.1:9200"
    return None


def _container_probe() -> dict:
    container_lister = main_patch_attr("_list_agent_containers", list_image_agent_containers)
    try:
        containers = container_lister()
    except Exception:
        return {
            "scope": "image_agent_labeled",
            "count": 0,
            "running_count": 0,
            "exited_count": 0,
            "status": "unavailable",
        }
    running = 0
    exited = 0
    for container in containers:
        state = str(container.get("state") or "").lower() if isinstance(container, dict) else ""
        if state == "running":
            running += 1
        elif state == "exited":
            exited += 1
    return {
        "scope": "image_agent_labeled",
        "count": len(containers),
        "running_count": running,
        "exited_count": exited,
    }


def _runtime_probe_from_status(status: dict) -> dict:
    workflows = {
        workflow_type: _workflow_probe(workflow_type, workflow)
        for workflow_type, workflow in (status.get("workflows") or {}).items()
        if isinstance(workflow, dict)
    }
    unavailable = [name for name, workflow in workflows.items() if workflow.get("available") is not True]
    docker_requires_sudo = status.get("docker_requires_sudo") is True
    blocking_codes = []
    if docker_requires_sudo:
        blocking_codes.append("docker_requires_sudo")
    if status.get("fs_license_exists") is not True:
        blocking_codes.append("fs_license_missing")
    blocking_codes.extend(f"workflow_{name}_unavailable" for name in unavailable)
    elasticsearch = _elasticsearch_probe()
    if elasticsearch["configured"] is not True:
        blocking_codes.append("elasticsearch_url_not_configured")
    if elasticsearch["reachable"] is not True:
        blocking_codes.append("elasticsearch_not_reachable")
    container_probe = _container_probe()
    if container_probe.get("status") == "unavailable":
        blocking_codes.append("container_probe_unavailable")
    ready = not blocking_codes
    return {
        "schema_version": 1,
        "status": "ready" if ready else "blocked",
        "portable": True,
        "machine_binding": "runtime_discovered",
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "docker": {
            "available": bool(workflows),
            "accessible": not docker_requires_sudo,
            "requires_sudo": docker_requires_sudo,
        },
        "runtime_preparation": _runtime_preparation_probe(status),
        "resources": _resource_probe(status),
        "elasticsearch": elasticsearch,
        "containers": container_probe,
        "workflows": workflows,
        "workflow_count": len(workflows),
        "available_workflow_count": len(workflows) - len(unavailable),
        "blocking_codes": blocking_codes,
    }


def runtime_probe() -> dict:
    runtime_inspector = main_patch_attr("inspect_runtime", inspect_runtime)
    return _runtime_probe_from_status(runtime_inspector())


def runtime_containers():
    runtime_inspector = main_patch_attr("inspect_runtime", inspect_runtime)
    status = runtime_inspector()
    return {**_safe_runtime_status(status), "runtime_probe": _runtime_probe_from_status(status)}


def runtime_probe_status():
    return runtime_probe()


def admin_containers():
    container_lister = main_patch_attr("_list_agent_containers", list_image_agent_containers)
    containers = container_lister()
    return {"containers": containers, "count": len(containers)}
