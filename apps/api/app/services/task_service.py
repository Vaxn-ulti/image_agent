from __future__ import annotations

import sys

from fastapi import HTTPException

from app.services.compat import legacy


def _rows(sql: str, params=()):
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, "rows"):
        return getattr(main, "rows")(sql, params)
    return legacy().rows(sql, params)


def _parse_series_row(row: dict):
    main = sys.modules.get("app.main")
    if main is not None and hasattr(main, "parse_series_row"):
        return getattr(main, "parse_series_row")(row)
    return legacy().parse_series_row(row)


def list_project_tasks(project_id):
    return _rows("SELECT * FROM tasks WHERE project_id=? ORDER BY id DESC", (project_id,))


def get_series(series_id):
    found = _rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
    if not found:
        raise HTTPException(404, "Series not found")
    return _parse_series_row(found[0])


def validate_run_request(series, req):
    return legacy().validate_run_request(series, req)


def create_series_task(series_id, req):
    return legacy().create_series_task(series_id, req)


def run_series(series_id, req):
    return create_series_task(series_id, req)


def get_task(task_id):
    found = _rows("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not found:
        raise HTTPException(404, "Task not found")
    return found[0]
