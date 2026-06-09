from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.db.database import now_iso


DEFAULT_CONFIRMATION_TTL_SECONDS = 60 * 60


def confirmation_fingerprint(confirmation: dict[str, Any]) -> str:
    relevant = {
        key: confirmation.get(key)
        for key in ("type", "action_lane", "project_id", "series_id", "workflow_type", "qsiprep_task_id")
    }
    raw = json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AgentThreadStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, thread_id: str) -> Path:
        safe_id = "".join(ch for ch in thread_id if ch.isalnum() or ch in {"-", "_"})[:120]
        return self.root / f"{safe_id}.json"

    def create_pending_confirmation(
        self,
        *,
        confirmation: dict[str, Any],
        decision: dict[str, Any],
        selected_skill: str,
        retrieved_context: dict[str, Any],
        ttl_seconds: int = DEFAULT_CONFIRMATION_TTL_SECONDS,
    ) -> dict[str, Any]:
        thread_id = f"agent_{uuid.uuid4().hex}"
        created_at = now_iso()
        record = {
            "thread_id": thread_id,
            "status": "pending_confirmation",
            "created_at": created_at,
            "updated_at": created_at,
            "expires_at": _expires_at(ttl_seconds),
            "confirmation": confirmation,
            "confirmation_fingerprint": confirmation_fingerprint(confirmation),
            "decision": decision,
            "selected_skill": selected_skill,
            "retrieved_context": retrieved_context,
        }
        self._path(thread_id).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return record

    def is_expired(self, record: dict[str, Any]) -> bool:
        expires_at = _parse_iso(record.get("expires_at"))
        if expires_at is None:
            return False
        return datetime.now(timezone.utc) >= expires_at

    def load(self, thread_id: str) -> dict[str, Any] | None:
        path = self._path(thread_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def mark(self, thread_id: str, *, status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self.load(thread_id)
        if record is None:
            raise KeyError(thread_id)
        record["status"] = status
        record["updated_at"] = now_iso()
        if extra:
            record.update(extra)
        self._path(thread_id).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return record


def _expires_at(ttl_seconds: int) -> str:
    ttl = max(int(ttl_seconds), 0)
    return (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
