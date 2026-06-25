# Workflow State

Allowed states: `queued`, `running`, `completed`, `failed`, `cancelled`.

Transitions:

- `queued -> running`
- `running -> completed`
- `running -> failed`
- `queued|running -> cancelled`

Mock T1 DeepPrep steps:

1. Create task and log file.
2. Set state `running` and progress 10.
3. Validate input series exists.
4. Write synthetic QC/report/output placeholders.
5. Register outputs.
6. Set progress 100 and state `completed`.

Real DeepPrep integration must only replace `apps/api/app/workflows/deepprep.py` execution internals and preserve task/output contracts.

## Agent Confirmation State

Pending workflow confirmations are separate from task state. They describe the
server-side gate between an agent proposal and backend task creation.

Allowed confirmation states:

- `pending_confirmation`
- `ready_to_launch`
- `task_created`
- `expired`
- `cancelled`

Transitions:

- `pending_confirmation -> ready_to_launch`
- `pending_confirmation -> task_created`
- `pending_confirmation -> expired`
- `pending_confirmation -> cancelled`

Confirmation source of truth:

- SQLite table `agent_confirmations` is the durable source when the backend DB
  has been initialized.
- SQLite table `agent_confirmation_events` audits `confirmation_created` and
  `confirmation_marked` transitions with `from_status`, `to_status`, and
  redacted metadata.
- JSON files under the agent thread store are compatibility mirrors/fallbacks,
  not the product source of truth.

Single-use rule:

- A successful approved resume must move the confirmation out of
  `pending_confirmation`.
- A second approved resume for the same thread must return blocked and must not
  create another production task.
- Expired confirmations return blocked with `production_task_created=false`.
