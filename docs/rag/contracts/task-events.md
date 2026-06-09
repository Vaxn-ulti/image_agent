# Task Events Contract RAG

## Purpose / 目的

Task events describe workflow lifecycle updates for users and for agent reasoning. This document is a curated target contract for RAG responses; backend task rows remain authoritative.

## Core Event Fields

- `event_type`: lifecycle, progress, output, warning, error, complete.
- `task_id`: numeric backend task id.
- `project_id`: numeric project id when available.
- `series_id`: source imaging series id when available.
- `workflow_type`: workflow name such as `t1_deepprep` or `bold_deepprep`.
- `status`: queued, running, completed, failed, cancelled, blocked.
- `progress`: integer 0-100 when known.
- `message`: short user-facing text.
- `timestamp`: ISO time when emitted.
- `artifact`: optional output path/type metadata.
- `error_code`: optional stable error category.

## Event Semantics / 语义

- `queued`: task exists but has not started.
- `running`: task is actively preparing data or executing a container.
- `completed`: task finished and outputs were discovered or registered.
- `failed`: task stopped because of a concrete error.
- `blocked`: preflight or validation found missing prerequisites.
- `cancelled`: user/system stopped the task before completion.

## Progress Milestones

Use milestone language when exact progress is not known:

- 0-10: task created, BIDS-like input staging.
- 10-30: validation/preflight and container command preparation.
- 30-80: workflow execution.
- 80-95: output discovery, result-summary generation, report rendering.
- 100: completed or validation-only complete.

## Agent Usage

When answering status questions:

1. Read backend task rows first.
2. Prefer latest event/log text for why the state changed.
3. Mention failed or blocked tasks with the first concrete error, not every log line.
4. Do not recommend launching another long workflow while a related task is running.

## Remote Script Wrapper Events

For remote script wrappers, task events and result-facing summaries must keep the public surface path-safe:

- Translate `TimeoutExpired` into a failed task event or log line that says the remote script timed out.
- Keep a redacted log tail for partial stdout retention only; script stdout/stderr must be redacted before it is stored or surfaced.
- Preflight and direct-run guards must enforce that script paths must be regular files, not directories.
- raised wrapper errors should use path-safe script labels rather than full host paths.
- success summaries use path-safe script labels, such as `run_fmriprep.sh` and `run_xcpd.sh`, rather than host paths.
- public preflight check summaries use path-safe labels instead of raw host paths.

## User-Facing Wording

Good:

- "Task 41 is completed at 100%, and the registered result-summary is available."
- "Task 115 is blocked because XCP-D needs fMRIPrep-compatible derivatives."

Avoid:

- "The scan is normal."
- "The workflow definitely failed because of disease."
