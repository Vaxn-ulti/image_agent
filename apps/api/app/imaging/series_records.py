from __future__ import annotations

import json

from app.db.queries import fetch_rows
from app.workflows.eligibility import build_workflow_eligibility


def parse_series_row(row: dict) -> dict:
    item = dict(row)
    item["metadata"] = json.loads(item.pop("metadata_json"))
    item["supported_for_processing"] = bool(item.get("supported_for_processing", 1))
    file_rows = fetch_rows("SELECT storage_path, file_type FROM files WHERE id=?", (item.get("file_id"),))
    if file_rows:
        item["file_storage_path"] = file_rows[0]["storage_path"]
        item["file_type"] = file_rows[0]["file_type"]
    item["workflow_eligibility"] = build_workflow_eligibility(item)
    item.pop("file_storage_path", None)
    item.pop("file_type", None)
    return item
