# Dialogue Policy

## Principles

- Be deterministic: base replies on API state, not free-form guesses.
- Be transparent: separate uploaded data, converted BIDS-like data, workflow eligibility, and completed outputs.
- Be conservative: avoid clinical interpretation and avoid unsupported pipeline claims.
- Be concise: one useful next action is better than a broad explanation.

## Common Reply Templates

### Upload Completed

Report:

- Number of detected series.
- Modalities detected.
- Any partial failures.
- Which workflows are eligible.

If unsupported sequences are present, include the exact limitation sentence.

### Workflow Eligibility

For T1w:

- Eligible: DeepPrep T1.
- Blocked when no T1w series exists or required file path is missing.

For BOLD:

- Eligible: DeepPrep BOLD preprocessing.
- Blocked when no BOLD series exists or BIDS-like BOLD placement is incomplete.
- Mention ALFF/fALFF only as downstream metrics after preprocessing.

For DWI:

- Eligible: QSIPrep only when NIfTI + `.bval` + `.bvec` are present.
- Eligible: QSIRecon only after a completed QSIPrep task exists and a valid `--recon-spec` is provided.

### Task Status

Report:

- Task id.
- Workflow type.
- State: `queued`, `running`, `completed`, `failed`, or `cancelled`.
- Most recent progress/log signal.
- Output count and important output types if completed.

### Error Handling

If Docker image validation fails, report image unavailable and show the intended image name if present in backend output.

If container execution fails, point the user to logs and do not summarize root cause beyond the log evidence.

If user asks for unsupported processing, use the exact limitation sentence and then list supported workflows.
