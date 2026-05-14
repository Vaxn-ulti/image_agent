# Output Discovery

## Principles

- Register outputs only after real execution completes.
- Keep unknown files in logs but do not invent output types.
- Store relative and absolute paths consistently with existing backend schema.
- Preserve task failure evidence in logs before raising or returning failure.

## Expected Output Types

DeepPrep T1:

- QC report.
- Segmentation.
- Brain mask.
- HTML report where present.

DeepPrep BOLD:

- Preprocessed BOLD.
- Confounds.
- Brain mask/reference outputs where present.
- QC or HTML report.

QSIPrep:

- Preprocessed DWI.
- Confounds.
- QC report.
- HTML report.

QSIRecon (depends on `--recon-spec`):

- DTI FA.
- DTI MD.
- Tractography.
- Connectome.
- HTML report.
- Pipeline-specific derivatives per the selected recon spec.

Downstream BOLD metrics:

- ALFF/fALFF outputs should be registered only if a separate implemented metric workflow creates them.
