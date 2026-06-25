# BOLD fMRI Workflow Draft

## Purpose

Define first-round first release handling for fMRI/BOLD preprocessing. In this product, fMRI/BOLD preprocessing is performed by DeepPrep. ALFF/fALFF may be added later as downstream metric calculation after BOLD preprocessing.

## Workflow Types

Draft names:

- `bold_deepprep`
- `bold_deepprep_validate`

Keep these names consistent across backend workflow gating, chat recommendations, and frontend workflow controls once implemented.

## Eligibility

Required:

- BOLD/fMRI series.
- Existing BOLD NIfTI path.
- Minimal BIDS-like func path.
- Sidecar metadata when available, especially task name and repetition time.
- FreeSurfer license path when required by runtime.
- DeepPrep Docker image for validate or run.

Blocked when:

- No BOLD series exists.
- BIDS-like func target cannot be constructed.
- Required runtime binds are missing.
- Docker image is unavailable for validate/run.

## BIDS-like Input

Construct under:

`data/projects/{project_id}/derivatives/{task_id}/bids`

Preferred path:

`sub-01/func/sub-01_task-rest_bold.nii.gz`

If task metadata is known, use the known task label. If multiple BOLD runs collide, add deterministic `run-*` and/or `acq-*`.

Recommended sidecar:

`sub-01/func/sub-01_task-rest_bold.json`

Do not require a perfect full BIDS dataset for first release validation unless the implementation adds full BIDS-validator support.

## Docker

Image:

`pbfslab/deepprep:25.1.0`

Draft command pattern:

```text
docker run --rm -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pbfslab/deepprep:25.1.0 /data /output participant
```

Implementation may add DeepPrep-specific BOLD flags after confirming runtime requirements. Keep validate-only behavior side-effect-light: return command and bind mounts without launching the container.

## Progress

- 10: BIDS-like func input ready.
- 30: Container validated or started.
- 50: BOLD preprocessing started.
- 70: Processing.
- 100: Completed or validation complete.

## Outputs

Register known outputs when present:

- Preprocessed BOLD.
- Confounds.
- Brain mask/reference files.
- QC or HTML report.

Do not register ALFF/fALFF unless a separate implemented downstream metric step produces those files.

## Chat Behavior

When BOLD is present, recommend DeepPrep BOLD preprocessing as the supported first step.

When the user asks for ALFF/fALFF:

1. Check whether BOLD exists.
2. Check whether DeepPrep-BOLD preprocessing completed.
3. Explain that ALFF/fALFF are downstream metrics after BOLD preprocessing and require an implemented metric stage.

## Concrete Eval Cases

1. BOLD-only upload becomes eligible for `bold_deepprep_validate`.
2. T1 + BOLD upload offers both T1 DeepPrep and BOLD DeepPrep without conflating them.
3. Request for fALFF before preprocessing recommends DeepPrep-BOLD first.
4. Two resting-state runs generate unique BIDS-like func targets with no overwrite.
