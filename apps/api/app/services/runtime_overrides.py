from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from app.core import config


def main_patch_attr(name: str, default: Any) -> Any:
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, name):
        return getattr(main, name)
    return default


def main_patch_attr_if_changed(name: str, initial: Any, current: Any) -> Any:
    if current is not initial:
        return current
    value = main_patch_attr(name, initial)
    if value is not initial:
        return value
    return current


def main_projects_root(default: str | Path = config.PROJECTS_ROOT, *, require_override: bool = False) -> Path:
    default_path = Path(default)
    patched_path = Path(main_patch_attr("PROJECTS_ROOT", default_path))
    if require_override and patched_path == default_path:
        return default_path
    return patched_path
