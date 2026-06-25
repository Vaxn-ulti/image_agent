# T1 DeepPrep Workflow

## Purpose

Run or validate DeepPrep anatomical preprocessing for eligible T1w series.

## Workflow Types

- `t1_deepprep`
- `t1_deepprep_validate`

## Eligibility

Required:

- T1w series.
- Existing NIfTI path.
- Minimal BIDS-like anatomical path.
- FreeSurfer license path when required by runtime.
- DeepPrep Docker image for real run or validate pass.

## BIDS-like Input

Construct under:

`data/projects/{project_id}/derivatives/{task_id}/bids`

Required path:

`sub-01/anat/sub-01_T1w.nii.gz`

Add `dataset_description.json`.

Use symlinks when possible. Resolve absolute mount paths before Docker.

## Docker

Image:

`pbfslab/deepprep:25.1.0`

Command pattern:

```text
docker run --rm -v {bids}:/data:ro -v {output}:/output -v {work}:/work -v {fs_license}:/opt/freesurfer/license.txt:ro pbfslab/deepprep:25.1.0 /data /output participant --anat_only
```

Validation builds and returns the command without launching long-running processing.

## Progress

- 10: BIDS-like input ready.
- 30: Container validated or started.
- 70: Processing.
- 100: Completed or validation complete.

## Outputs

Register known outputs when present:

- QC/HTML report.
- Segmentation.
- Brain mask.
- Other known DeepPrep anatomical derivatives.

Unknown files may be logged but should not receive invented output types.

## Concrete Eval Cases

1. Eligible T1 validates with absolute Docker bind mounts.
2. Missing T1 series is rejected before command construction.
3. Missing license path fails validation before container launch.
4. Completed run registers report and mask outputs when files exist.
