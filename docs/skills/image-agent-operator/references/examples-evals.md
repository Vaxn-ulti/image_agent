# Concrete Examples and Evals

Use these cases to test OpenAI SDK chat gateway operator behavior, including deterministic rule fallbacks and DeepSeek legacy fallback compatibility where applicable.

## Example 1: Mixed Upload With T1, BOLD, DWI

User: "I uploaded a subject with T1, resting fMRI, and DWI. What can I run?"

Expected behavior:

- Mention DeepPrep T1 for T1w.
- Mention DeepPrep BOLD for fMRI/BOLD.
- Mention `dwi_fast_gpu_dti` for production DWI only if `.bval`, `.bvec`, and JSON sidecar metadata exist.
- Explain the production DWI path as host FSL GPU eddy plus MRtrix toolbox mode when the user asks about execution details.
- Mention legacy QSIPrep/QSI only when explicitly selected or when backend records show those workflows are relevant.
- Mention QSIRecon only after QSIPrep completes.
- Do not say ALFF/fALFF are the preprocessing step.

## Example 2: BOLD Metrics Request

User: "Can you compute fALFF?"

Expected behavior:

- Check whether BOLD series exists and whether DeepPrep-BOLD preprocessing has completed.
- If not completed, recommend DeepPrep BOLD preprocessing first.
- Say ALFF/fALFF/ReHo/DMN/seed-to-ROI are single-subject downstream metrics after DeepPrep when backend output records show support.
- Do not call `bold_second_level` a group analysis; group analysis is a separate backend route.

## Example 3: Unsupported Sequence

User: "Run radiomics on SWI."

Expected behavior:

- Include exact sentence: `Current software does not support radiomics/processing for this sequence.`
- List currently supported workflows only.

## Example 4: Failed Docker Validation

User: "Why can't I run QSIPrep?"

Expected behavior:

- Report missing image or missing DWI gradient files from backend state.
- Do not invent installation status.

## Example 5: Production DWI Missing JSON

User: "I uploaded DWI with bval and bvec, can I run the fast DTI workflow?"

Expected behavior:

- Check backend metadata for JSON sidecar and `PhaseEncodingDirection`/`TotalReadoutTime`.
- If missing, say the production fast GPU DTI workflow is blocked by missing JSON sidecar metadata.
- Do not suggest fabricating phase-encoding values.
- Do not suggest running full QSIPrep/QSIRecon as the default replacement.

## Example 5b: Production DWI Runtime Question

User: "Will the DTI metrics run through QSIPrep?"

Expected behavior:

- Say the production DTI path does not run full QSIPrep or full QSIRecon.
- Say it uses host FSL GPU `eddy_cuda` for eddy correction and MRtrix tools from the QSIPrep image only as a toolbox.
- Mention the 35 minute target and that real task logs/output records are the source of truth for completion.

## Example 6: Placeholder Result Summary

User: "Are these T1 values final?"

Expected behavior:

- If provenance has `extraction_status=real_deepprep_freesurfer_stats`, say the backend parsed real DeepPrep/Freesurfer T1 feature tables.
- If provenance has `placeholder_outputs` or `extraction_status=placeholder_contract_pending_real_deepprep_parser`, say the backend has a frontend contract placeholder, not final extracted T1 features.
- Recommend the next real parser/DeepPrep output extraction step instead of presenting zeros as measurements.

## Eval Checklist

- Reply uses backend state rather than guessing.
- Triggered workflow names match product contracts.
- BOLD preprocessing is assigned to DeepPrep.
- BOLD downstream metrics are described as single-subject unless a group-analysis route/task is present.
- DWI fast GPU DTI requires JSON sidecar metadata in addition to `.bval`/`.bvec`.
- Production DWI is not described as full QSIPrep/QSIRecon.
- Placeholder provenance is surfaced honestly.
- QSIRecon dependency on completed QSIPrep and `--recon-spec` is explicit.
- Unsupported limitation text is exact.
