# Concrete Examples and Evals

## Developer Example 1: Add DeepPrep BOLD Validate

Task: Implement validate-only `bold_deepprep_validate`.

Expected changes:

- Backend accepts workflow type.
- Eligibility requires BOLD series.
- BIDS-like func tree includes a `_bold.nii.gz` file.
- Validation returns Docker command and bind mounts without launching container.
- Tests cover eligible and missing-BOLD cases.
- Chat recommends DeepPrep BOLD for BOLD series.

## Developer Example 2: Prevent BIDS Collision

Task: Two BOLD runs map to the same subject/task.

Expected changes:

- Second file receives `run-2` or another deterministic unique entity.
- No overwrite occurs.
- Inventory reports both target paths.
- Test asserts stable naming across repeated ingest.

## Developer Example 3: DWI Without Gradients

Task: User uploads DWI NIfTI without `.bval`/`.bvec`.

Expected behavior:

- Series may be detected as DWI.
- QSIPrep eligibility is false.
- Reason identifies missing gradient files.
- Chat does not recommend running QSIPrep until gradients are present.

## Eval Checklist

- `SKILL.md` remains concise and references hold details.
- Workflow contracts are updated in `docs/workflows`.
- Tests cover concrete example behavior.
- QSIRecon commands include `--recon-spec`.
- No README or broad process document is added for skills.
