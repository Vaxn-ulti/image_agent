# Database

SQLite file defaults to `data/app.db`.

## Tables

`users`: `id, username, created_at`.

`projects`: `id, name, description, created_at`.

`files`: `id, project_id, original_name, storage_path, file_type, size, sha256, created_at`.

`imaging_series`: `id, project_id, file_id, modality, format, confidence, metadata_json, status, created_at`.

`tasks`: `id, project_id, series_id, workflow_type, status, progress, log_path, error_message, created_at, started_at, finished_at`.

`outputs`: `id, task_id, output_type, path, preview_path, metadata_json, created_at`.

`chat_messages`: `id, project_id, role, content, created_at`.
