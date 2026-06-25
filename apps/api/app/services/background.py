from __future__ import annotations

from collections.abc import Callable
from threading import Thread
from typing import Any


def submit_background(target: Callable[..., Any], *args: Any) -> None:
    """Start background work behind a replaceable service boundary."""
    Thread(target=target, args=args, daemon=True).start()
