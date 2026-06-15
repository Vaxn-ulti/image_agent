from __future__ import annotations

from pathlib import Path

from app.db.database import connect, now_iso, row_to_dict
from app.services.runtime_overrides import main_projects_root


def _projects_root() -> Path:
    return main_projects_root()


def login(req):
    with connect() as conn:
        existing = conn.execute("SELECT * FROM users WHERE username=?", (req.username,)).fetchone()
        if existing is None:
            cur = conn.execute("INSERT INTO users(username, created_at) VALUES(?,?)", (req.username, now_iso()))
            user = {"id": cur.lastrowid, "username": req.username}
        else:
            user = {"id": existing["id"], "username": existing["username"]}
    return {"access_token": "mvp-token", "token_type": "bearer", "user": user}


def list_projects():
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()]


def create_project(req):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects(name, description, created_at) VALUES(?,?,?)",
            (req.name, req.description, now_iso()),
        )
        project_id = cur.lastrowid
        project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    for subdir in ("raw", "logs", "derivatives"):
        (_projects_root() / str(project_id) / subdir).mkdir(parents=True, exist_ok=True)
    return row_to_dict(project)
