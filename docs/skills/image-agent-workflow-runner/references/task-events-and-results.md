# Task Events and Results

## Task Event Trail

Use event names that make lifecycle reconstruction possible:

- `queued`
- `preflight_started`
- `preflight_passed`
- `preflight_failed`
- `container_prepared`
- `running`
- `progress`
- `log`
- `output_discovered`
- `output_registered`
- `result_summary_written`
- `completed`
- `failed`
- `cancelled`

Events should include task id, project id, workflow type, timestamp, and safe concise details. Avoid patient identifiers and raw secrets.

## Result Summary Contract

Result summaries should expose:

- modality and workflow type;
- execution status and `validation_only`;
- provenance with runner, command metadata, runtime, and compatibility notes;
- feature groups;
- outputs with `relative_path`, `download_url`, `content_type`, `size_bytes`, and `exists`;
- report artifacts under `outputs.reports` when present.

Frontend consumers should use `/tasks/{task_id}/result-summary` and `/tasks/{task_id}/artifacts/{relative_path}` rather than local paths.

Frontend artifact panels should prefer `/tasks/{task_id}/artifact-manifest` for the stable preview/download list. The manifest contract is `contract_version=artifact_manifest_v1` and should return the matching `task_id`. Manifest items include safe `relative_path`, recomputed `download_url`, `preview_kind`, `content_type`, and positive `size_bytes` so HTML reports, image QC figures, tables, JSON, and download-only maps can be rendered without guessing from filenames. The manifest must provide no backend `path` leakage or backend absolute paths. The result-summary remains authoritative for completed workflow outputs and scientific interpretation.

## Output Registration

Register an output only after the file exists. Empty output paths are invalid; for metadata-only artifacts, write `metadata/<kind>_output.json` inside the task output directory and register that file.

Do not reuse validate-only placeholder summaries after a real run. Real summaries must be rebuilt from real files.

## Failure Summary

Failed tasks should retain:

- preflight result;
- command summary without secrets;
- latest useful log evidence;
- missing input/capability;
- partial outputs only if files actually exist and are safe to expose.

For remote script wrappers, TimeoutExpired should be translated into a failed task event/log line that says the remote script timed out. Keep a redacted log tail for partial stdout retention; script stdout/stderr must be redacted before it is stored or surfaced. Script paths must be regular files, not directories, raised wrapper errors should use path-safe script labels rather than full host paths, success summaries use path-safe script labels, and public preflight check summaries use path-safe labels.
