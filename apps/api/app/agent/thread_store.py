from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.db.database import connect
from app.db.database import now_iso


DEFAULT_CONFIRMATION_TTL_SECONDS = 60 * 60
CONFIRMATION_ENVELOPE_KEYS = {"fingerprint", "confirmation_fingerprint"}


def _canonical_confirmation_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_confirmation_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if item is not None and str(key) not in CONFIRMATION_ENVELOPE_KEYS
        }
    if isinstance(value, list):
        return [_canonical_confirmation_value(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_confirmation_value(item) for item in value]
    return value


def confirmation_fingerprint(confirmation: dict[str, Any]) -> str:
    raw = json.dumps(_canonical_confirmation_value(confirmation), sort_keys=True, ensure_ascii=False)
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
        self._persist_sqlite(record)
        return record

    def is_expired(self, record: dict[str, Any]) -> bool:
        expires_at = _parse_iso(record.get("expires_at"))
        if expires_at is None:
            return False
        return datetime.now(timezone.utc) >= expires_at

    def load(self, thread_id: str) -> dict[str, Any] | None:
        path = self._path(thread_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return self._load_sqlite(thread_id)

    def mark(self, thread_id: str, *, status: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self.load(thread_id)
        if record is None:
            raise KeyError(thread_id)
        record["status"] = status
        record["updated_at"] = now_iso()
        if extra:
            record.update(extra)
        self._path(thread_id).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        self._mark_sqlite(thread_id, status=status, extra=extra or {}, updated_at=record["updated_at"])
        return record

    def _persist_sqlite(self, record: dict[str, Any]) -> None:
        fields = _confirmation_fields(record.get("confirmation") or {})
        try:
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_confirmations(
                      thread_id, status, project_id, series_id, workflow_type,
                      qsiprep_task_id, action_lane, confirmation_fingerprint,
                      confirmation_json, decision_json, selected_skill,
                      retrieved_context_json, extra_json, expires_at, created_at,
                      updated_at, safe_metadata_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(thread_id) DO UPDATE SET
                      status=excluded.status,
                      project_id=excluded.project_id,
                      series_id=excluded.series_id,
                      workflow_type=excluded.workflow_type,
                      qsiprep_task_id=excluded.qsiprep_task_id,
                      action_lane=excluded.action_lane,
                      confirmation_fingerprint=excluded.confirmation_fingerprint,
                      confirmation_json=excluded.confirmation_json,
                      decision_json=excluded.decision_json,
                      selected_skill=excluded.selected_skill,
                      retrieved_context_json=excluded.retrieved_context_json,
                      extra_json=excluded.extra_json,
                      expires_at=excluded.expires_at,
                      updated_at=excluded.updated_at,
                      safe_metadata_json=excluded.safe_metadata_json
                    """,
                    (
                        record["thread_id"],
                        record["status"],
                        fields.get("project_id"),
                        fields.get("series_id"),
                        fields.get("workflow_type"),
                        fields.get("qsiprep_task_id"),
                        fields.get("action_lane"),
                        record["confirmation_fingerprint"],
                        _json(record.get("confirmation") or {}),
                        _json(record.get("decision") or {}),
                        record.get("selected_skill"),
                        _json(record.get("retrieved_context") or {}),
                        _json(_extra_fields(record)),
                        record["expires_at"],
                        record["created_at"],
                        record["updated_at"],
                        _json({"schema_version": 1, "storage": "sqlite_agent_confirmations"}),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO agent_confirmation_events(
                      thread_id, event_type, from_status, to_status, metadata_json, created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        record["thread_id"],
                        "confirmation_created",
                        None,
                        record["status"],
                        "{}",
                        record["created_at"],
                    ),
                )
        except sqlite3.OperationalError:
            return

    def _load_sqlite(self, thread_id: str) -> dict[str, Any] | None:
        try:
            with connect() as conn:
                row = conn.execute(
                    "SELECT * FROM agent_confirmations WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        record = {
            "thread_id": row["thread_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
            "confirmation": _loads_dict(row["confirmation_json"]),
            "confirmation_fingerprint": row["confirmation_fingerprint"],
            "decision": _loads_dict(row["decision_json"]),
            "selected_skill": row["selected_skill"],
            "retrieved_context": _loads_dict(row["retrieved_context_json"]),
        }
        record.update(_loads_dict(row["extra_json"]))
        return record

    def _mark_sqlite(self, thread_id: str, *, status: str, extra: dict[str, Any], updated_at: str) -> None:
        try:
            with connect() as conn:
                row = conn.execute(
                    "SELECT status, extra_json FROM agent_confirmations WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()
                if row is None:
                    return
                previous_status = row["status"]
                merged_extra = {**_loads_dict(row["extra_json"]), **extra}
                consumed_at = updated_at if previous_status == "pending_confirmation" and status != "pending_confirmation" else None
                conn.execute(
                    """
                    UPDATE agent_confirmations
                    SET status=?,
                        extra_json=?,
                        updated_at=?,
                        consumed_at=COALESCE(consumed_at, ?)
                    WHERE thread_id=?
                    """,
                    (status, _json(merged_extra), updated_at, consumed_at, thread_id),
                )
                conn.execute(
                    """
                    INSERT INTO agent_confirmation_events(
                      thread_id, event_type, from_status, to_status, metadata_json, created_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        thread_id,
                        "confirmation_marked",
                        previous_status,
                        status,
                        _json({"extra_keys": sorted(extra)} if extra else {}),
                        updated_at,
                    ),
                )
        except sqlite3.OperationalError:
            return


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


def _confirmation_fields(confirmation: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": _int_or_none(confirmation.get("project_id")),
        "series_id": _int_or_none(confirmation.get("series_id")),
        "workflow_type": _str_or_none(confirmation.get("workflow_type")),
        "qsiprep_task_id": _int_or_none(confirmation.get("qsiprep_task_id")),
        "action_lane": _str_or_none(confirmation.get("action_lane")),
    }


def _extra_fields(record: dict[str, Any]) -> dict[str, Any]:
    base_keys = {
        "thread_id",
        "status",
        "created_at",
        "updated_at",
        "expires_at",
        "confirmation",
        "confirmation_fingerprint",
        "decision",
        "selected_skill",
        "retrieved_context",
    }
    return {key: value for key, value in record.items() if key not in base_keys}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads_dict(value: Any) -> dict[str, Any]:
    try:
        loaded = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None
