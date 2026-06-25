# Security and Containers

## Mount Safety

- Resolve every host path before binding it.
- Reject writable mounts outside the configured project root.
- Allow read-only support mounts outside the project root only when at least one project-owned mount is present.
- Do not mount patient data into unrelated containers.
- Do not expose local absolute paths to frontend users.

When incubating a script-derived workflow, decompose each container bind into a structured mount record before promotion:

- `input_data`: BIDS/raw dataset mounts such as `/data` or `/bids`; must be read-only.
- `output_data`: derivative/report output mounts such as `/out` or `/output`; must be writable and scoped to the sandbox/project output root.
- `work_dir`: transient work mounts such as `/work`; must be writable and scoped to the sandbox/project work root.
- `templateflow_cache`: TemplateFlow cache mounts; may be writable but must be separated from patient data.
- `license_file`: FreeSurfer or other license mounts; must be read-only and the file contents must never be logged.
- `support`: non-patient support mounts; must be justified and reviewed.

Promotion requires validation checks named `input_mounts_are_read_only`, `license_mount_is_read_only`, and `output_and_work_mounts_are_sandbox_scoped` when those mount roles are present.

## Incubation Validation Plans

When a free-form toolchain is being incubated, require a `validation_plan` before discussing promotion. The plan should translate primitive checks into evidence requirements with:

- `name`
- `evidence_kind`
- `expected_evidence`
- `source_stages`

Use `artifact` for required HTML reports, metric tables, maps, logs, and result-summary files; `mount_audit` for read-only input and license mount checks; `runtime` for container exit codes and GPU readiness; `contract` for result-summary schema checks; and `parameter_audit` for participant labels or other backend-derived parameters.

The validation plan should require at least two passed sandbox runs, no production task side effects during incubation, redacted command/environment provenance, and human approval before a promotion suggestion can be considered.

## Container Image Inspection

For script-derived workflows, require a `container_inspection_plan` for every container primitive before sandbox execution. The plan must be executed by backend local/runtime tools, never directly by the LLM.

The inspection should capture image digest or image id, entrypoint, default command, user, working directory, labels, environment keys, version probes, and native report/output path probes. It must not mount patient data, log license contents, dump full environments, or create production tasks.

The validation plan must include `container_inspection` evidence for `container_image_inspected`, `container_digest_recorded`, `container_entrypoint_recorded`, `container_versions_recorded`, and `container_native_output_paths_verified`. Treat missing inspection evidence as a promotion blocker even when sandbox output artifacts exist.

When the backend runs inspection, use local/runtime tools such as `docker image inspect`, `podman image inspect`, `singularity inspect --json`, or `apptainer inspect --json`. This is still sandbox validation evidence; do not treat a successful image inspection as proof that the full workflow runs or that production execution is enabled.

Official RAG summaries for runtime-specific inspection behavior:

- `docs/rag/vendor/docker_official_image_inspect.md`
- `docs/rag/vendor/podman_official_image_inspect.md`
- `docs/rag/vendor/singularity_apptainer_official_inspect.md`

## Container Safety

Image Agent-owned containers should be labeled with:

- `image_agent.app=image_agent`
- `task_id`
- `project_id`
- `workflow_type`

Use labels for recovery and inspection. Never stop or remove unrelated containers. For historical unlabeled containers, inspect command, mounts, and logs before deciding whether they belong to a task.

## Remote Script Wrappers

Remote script wrappers are local/runtime tools owned by the backend. They are not exposed directly to the model.

- The model may request `create_workflow_task`; it may not call bash, Docker, SSH, or sudo.
- The backend wrapper must pass task paths through environment variables such as `IMAGE_AGENT_TASK_BIDS_DIR`, `IMAGE_AGENT_TASK_OUTPUT_DIR`, `IMAGE_AGENT_TASK_WORK_DIR`, and `IMAGE_AGENT_TASK_FS_LICENSE`.
- Production scripts must prefer task environment variables over hardcoded evidence-project paths.
- Preflight must reject missing scripts before the task starts; script paths must be regular files, not directories. It must also reject a missing license, inaccessible BIDS input, and unwritable output/work parents.
- Logs may include path-safe script labels and task directory paths, but not API keys, sudo passwords, license contents, or full environment dumps; raised wrapper errors should use path-safe script labels rather than full host paths, success summaries use path-safe script labels, and public preflight check summaries use path-safe labels.
- Helper scripts must not pipe literal passwords into `sudo -S`. If a backend-owned sudo helper is unavoidable, it may read the password from the backend-managed `IMAGE_AGENT_SUDO_PASSWORD` environment variable and must keep the value out of command previews, logs, docs, and RAG chunks.
- Remote wrappers must use `IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC` as the per-script timeout. On `TimeoutExpired`, report that the remote script timed out and retain only a redacted log tail for partial stdout retention. Pass only the safe child environment allowlist and task-specific `IMAGE_AGENT_TASK_*` variables; do not pass `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, or `IMAGE_AGENT_SUDO_PASSWORD` to child scripts. In other words, child workflow scripts must not receive `IMAGE_AGENT_SUDO_PASSWORD`. All script stdout/stderr must be redacted before it is logged.

## Log Safety

Logs should include enough evidence to reproduce command construction and failure diagnosis, but exclude:

- patient identifiers;
- DB credentials;
- tokens and API keys;
- license file contents;
- raw image data;
- full environment dumps.

## Runtime Conflict Checks

If task APIs return surprising 404s or empty results, verify server identity with `/health` before declaring data loss. A port conflict can make an unrelated API answer on the expected port.
