"""Shared API helpers kept out of route modules.

This module is a transitional compatibility surface during the main.py split.
Domain logic is moving into services; helpers are re-exported here so new
routes do not reach into the FastAPI app entrypoint.
"""

from app.services.compat import legacy


def __getattr__(name: str):
    return getattr(legacy(), name)
