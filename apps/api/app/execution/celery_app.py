from __future__ import annotations

import os

from app.execution.queueing import EXECUTION_QUEUES


def build_celery_app():
    try:
        from celery import Celery
        from kombu import Queue
    except ImportError as exc:
        raise RuntimeError("Celery is not installed. Install apps/api requirements before starting workers.") from exc

    broker_url = os.environ.get("IMAGE_AGENT_CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend = os.environ.get("IMAGE_AGENT_CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    app = Celery("image_agent", broker=broker_url, backend=result_backend)
    app.conf.update(
        task_queues=[Queue(name) for name in sorted(set(EXECUTION_QUEUES.values()))],
        task_default_queue=EXECUTION_QUEUES[next(iter(EXECUTION_QUEUES))],
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )
    return app


celery_app = build_celery_app()
