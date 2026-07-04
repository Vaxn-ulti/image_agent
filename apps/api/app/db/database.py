import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.core.config import DB_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN qsiprep_task_id INTEGER")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE tasks ADD COLUMN runtime_workflow_type TEXT")
        except Exception:
            pass
        for column, ddl in {
            "upload_session_id": "ALTER TABLE imaging_series ADD COLUMN upload_session_id INTEGER",
            "bids_path": "ALTER TABLE imaging_series ADD COLUMN bids_path TEXT",
            "sequence_label": "ALTER TABLE imaging_series ADD COLUMN sequence_label TEXT",
            "supported_for_processing": "ALTER TABLE imaging_series ADD COLUMN supported_for_processing INTEGER NOT NULL DEFAULT 1",
            "unsupported_reason": "ALTER TABLE imaging_series ADD COLUMN unsupported_reason TEXT",
        }.items():
            try:
                conn.execute(ddl)
            except Exception:
                pass


def row_to_dict(row):
    return dict(row) if row is not None else None
