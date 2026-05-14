# Concrete Examples and Evals

Use these cases to test DeepSeek operator behavior.

## Example 1: Mixed Upload With T1, BOLD, DWI

User: "I uploaded a subject with T1, resting fMRI, and DWI. What can I run?"

Expected behavior:

- Mention DeepPrep T1 for T1w.
- Mention DeepPrep BOLD for fMRI/BOLD.
- Mention QSIPrep for DWI only if `.bval` and `.bvec` exist.
- Mention QSIRecon only after QSIPrep completes.
- Do not say ALFF/fALFF are the preprocessing step.

## Example 2: BOLD Metrics Request

User: "Can you compute fALFF?"

Expected behavior:

- Check whether BOLD series exists and whether DeepPrep-BOLD preprocessing has completed.
- If not completed, recommend DeepPrep BOLD preprocessing first.
- Say ALFF/fALFF are downstream metrics that may require an implemented metric stage.

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

## Eval Checklist

- Reply uses backend state rather than guessing.
- Triggered workflow names match product contracts.
- BOLD preprocessing is assigned to DeepPrep.
- QSIRecon dependency on completed QSIPrep and `--recon-spec` is explicit.
- Unsupported limitation text is exact.
