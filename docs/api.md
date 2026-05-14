# API Contract

Base URL: `http://<server>:8000`.

## Auth

`POST /auth/login`
Request: `{ "username": "demo", "password": "demo" }`
Response: `{ "access_token": "mvp-token", "token_type": "bearer", "user": {"id": 1, "username": "demo"} }`

## Projects

`GET /projects`
Response: `[{ "id": 1, "name": "Project", "description": "", "created_at": "..." }]`

`POST /projects`
Request: `{ "name": "Project", "description": "optional" }`
Response: project object.

## Upload/Series

`POST /projects/{project_id}/upload` multipart field `file`.
Response: `{ "file": {...}, "series": {...} }`.

`GET /projects/{project_id}/series`
Response: list of series objects.

`GET /series/{series_id}`
Response: one series object.

Series fields: `id, project_id, file_id, modality, format, confidence, metadata, status, created_at`.

## Tasks

`POST /series/{series_id}/run`
Request: `{ "workflow_type": "t1_deepprep_mock" }`
Response: task object.

`GET /tasks/{task_id}` returns task.
`GET /tasks/{task_id}/logs` returns `{ "task_id": 1, "text": "..." }`.
`GET /tasks/{task_id}/outputs` returns output list.

Task states: `queued`, `running`, `completed`, `failed`, `cancelled`.

## Chat

`POST /chat`
Request: `{ "project_id": 1, "message": "task status 1" }`
Response: `{ "reply": "...", "references": [{"type":"task", "id":1}] }`.
