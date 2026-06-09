# Grounding and Confirmation

## Evidence Priority

Use this order when sources disagree:

1. Current backend DB records, task state, registered outputs, result summaries, and logs.
2. Persisted ingest inventory and BIDS-like placement.
3. Sidecar JSON, DICOM tags, NIfTI headers, filename tokens.
4. Repository docs and RAG snippets.
5. User recollection from chat.

When RAG says a workflow exists but backend eligibility says it cannot run, report the backend state and the exact blocker. Do not let retrieved text override task/output records.

## Confirmation Pattern

Before recommending a workflow, confirm:

- Project id and series id when available.
- Detected modality and source of detection.
- Required sidecars or derivatives.
- Existing task state for the same workflow.
- Registered output or result-summary evidence if claiming completion.

If one fact is missing, ask for that fact only or suggest the endpoint/tool that can inspect it.

## Workflow Grounding

- T1w preprocessing: `t1_deepprep`, requires T1w input.
- BOLD preprocessing: `bold_deepprep`, requires BOLD input and BIDS-like func placement.
- BOLD downstream metrics: `bold_second_level`, requires completed BOLD DeepPrep outputs and remains single-subject.
- Production DWI: `dwi_fast_gpu_dti`, requires DWI NIfTI, `.bval`, `.bvec`, JSON sidecar, `PhaseEncodingDirection`, and `TotalReadoutTime`.
- Legacy QSI: `dwi_qsiprep`, `dwi_qsirecon`, and `dwi_qsi_full` only when explicitly selected or when existing task records make them relevant.

## User Confirmation

Ask for confirmation before a potentially expensive or long-running workflow launch. Confirmation should summarize the series, workflow type, expected inputs, and whether this is validate-only or real execution.
