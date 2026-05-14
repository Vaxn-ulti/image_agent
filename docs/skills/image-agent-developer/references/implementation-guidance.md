# Implementation Guidance

## Change Order

1. Update backend models/contracts first.
2. Implement deterministic imaging/workflow behavior.
3. Add or update tests.
4. Wire frontend controls and status views.
5. Update DeepSeek chat grounding and templates.
6. Update workflow docs.

## Mixed Ingest

Implement ingest as status-driven for normal uploads. Tiny synchronous behavior is acceptable only when persisted inventory remains the source of truth.

Inventory should expose:

- Upload/session id.
- Lifecycle state.
- Input counts.
- Converted counts.
- Detected modalities.
- Unsupported recognized sequences.
- Partial conversion failures.
- BIDS-like target paths.
- Workflow eligibility flags and reasons.

## BOLD Support

Treat fMRI/BOLD as supported for DeepPrep preprocessing. Add workflow gating and tests equivalent to T1 and DWI paths.

At minimum, BOLD support should cover:

- Detection or metadata mapping to BOLD modality.
- BIDS-like func target construction.
- `bold_deepprep` workflow eligibility.
- validate-only Docker command construction.
- chat response recommendation.

ALFF/fALFF should remain a separate downstream metric contract until implemented.

## Docker Workflows

Use tokenized command lists for subprocess calls. Validation must resolve image availability and command/bind mounts without launching long-running containers.

No sudo in workflow code. Do not run destructive cleanup during validation.

## Tests

Prefer focused unit tests for naming, metadata precedence, and workflow gating. Add integration tests for ingest lifecycle and validate-only workflow paths.

Run tests from the repo root using the venv pytest:

```text
apps/api/.venv/bin/pytest -q apps/api/tests
```

Do not use repo-root `pytest` or `cd apps/api && pytest`; the venv has all required dependencies.
