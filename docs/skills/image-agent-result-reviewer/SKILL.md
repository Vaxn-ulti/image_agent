---
name: image-agent-result-reviewer
description: Use when reviewing Image Agent task outputs, result summaries, scientific reports, artifact completeness, provenance, frontend display readiness, non-diagnostic wording, or evidence quality for T1, BOLD, DWI, DeepPrep, fast DTI, QSIPrep, or QSIRecon results.
---

# Image Agent Result Reviewer

Review results as product artifacts and research pipeline outputs, not as clinical findings.

## Trigger Rules

Use this skill for acceptance checks, artifact review, scientific report review, result-summary validation, UI-readiness checks, output completeness, provenance audits, and user-facing result wording.

Use `image-agent-workflow-runner` when the task still needs execution or output registration.

## Operating Rules

1. Review only artifacts that exist in task outputs, registered outputs, result summaries, or verified report manifests.
2. Separate artifact completeness from scientific validity and from clinical meaning.
3. Keep wording non-diagnostic: do not infer disease, prognosis, treatment, or clinical normality from metrics.
4. Check provenance before trusting values: workflow type, validation-only flag, placeholder flag, runtime, source files, parser status, atlas, space, and feature group.
5. Prefer result-summary and registered outputs over screenshots or informal file lists.
6. Evidence must be specific: task id, artifact relative path, table/map/report name, provenance field, or log line.
7. Flag frontend-readiness issues such as missing `download_url`, wrong media type, empty `relative_path`, or report artifacts not listed under `outputs.reports`.

## Reference Loading

- Read `references/artifact-review.md` before checking completeness or frontend display readiness.
- Read `references/container-qc-artifacts.md` before judging HTML/QC/image display readiness.
- Read `references/non-diagnostic-evidence.md` before writing user-facing review text or discussing metric meaning.
- Read existing `../neuroimaging-workflow-runner/references/output-discovery.md` for expected modality outputs.
- Read existing `../image-agent-developer/references/contracts.md` when result-summary shape or artifact serving rules matter.

## Output Shape

Return:

1. Verdict: pass, pass with caveats, blocked, or fail.
2. Evidence reviewed.
3. Missing or inconsistent artifacts.
4. Provenance and validation-only status.
5. Frontend/report readiness.
6. Container-native QC/HTML/image artifact readiness.
7. Safe user-facing summary.

Keep recommendations actionable and limited to verification, rerun, parser/report fix, or artifact registration.

## Eval Hints

Good evals include validate-only summaries mistaken for real outputs, missing report manifests, clinical interpretation pressure, inconsistent atlas metadata, and artifact links with unsafe paths. Passing reviews cite concrete evidence and refuse diagnostic claims.
