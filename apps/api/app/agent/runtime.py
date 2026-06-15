from __future__ import annotations

from app.services.runtime_overrides import main_patch_attr

try:
    from app.workflows.pipeline import inspect_runtime
    from app.workflows.recovery import list_image_agent_containers
except ImportError:

    def inspect_runtime() -> dict:
        return {"error": "pipeline runner missing", "workflows": {}}

    def list_image_agent_containers():
        return []


def runtime_containers():
    runtime_inspector = main_patch_attr("inspect_runtime", inspect_runtime)
    return runtime_inspector()


def admin_containers():
    container_lister = main_patch_attr("_list_agent_containers", list_image_agent_containers)
    containers = container_lister()
    return {"containers": containers, "count": len(containers)}
