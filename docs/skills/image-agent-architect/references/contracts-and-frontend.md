# Contracts and Frontend

## Contract First Checklist

Before implementation, define:

- Endpoint path and method.
- Request body and validation errors.
- Task state transitions.
- Workflow type and validation variant names.
- Result-summary modality, feature groups, provenance, and output items.
- Artifact `relative_path`, `download_url`, `content_type`, and `size_bytes`.
- Backward-compatible behavior for existing task/output records.

## Result Summary Rules

Result summaries should be generated from real output files after execution. Validate-only summaries must mark `validation_only: true` or `placeholder_outputs: true`.

Machine-readable result summaries are the source of truth for the UI. Scientific report pages and figures are presentation artifacts layered on top of the same data.

## Frontend Rules

The React/Vite UI should:

- call backend endpoints rather than rebuilding workflow eligibility locally;
- render registered artifact download URLs instead of local absolute paths;
- show report artifacts as previews where media type allows;
- keep NIfTI maps as downloadable source artifacts unless a real viewer exists;
- show blocked states and validation errors without pretending the workflow ran.

## Compatibility Choices

When renaming or superseding an old workflow, keep legacy names readable in historical tasks and use a wrapper/adaptor if necessary. Avoid breaking `/tasks/{id}/result-summary` for already completed tasks.
