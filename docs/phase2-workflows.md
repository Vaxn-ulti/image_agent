# Phase 2 Workflow Contracts

Each workflow is a python module under `apps/backend/workflows/` with one entry-point function `run(task_id, series, task_record)`. Validation variants share the same module, gated by a `validate_only: bool` parameter.

## BIDS Construction (shared)

Before any container launch, construct a minimal BIDS tree under `derivatives/{task_id}/bids/`:

```
sub-01/
  anat/
    sub-01_T1w.nii.gz          # symlink → raw/ T1 NIfTI
  dwi/
    sub-01_dwi.nii.gz          # symlink → raw/ DWI NIfTI
    sub-01_dwi.bval            # symlink → raw/ .bval
    sub-01_dwi.bvec            # symlink → raw/ .bvec
dataset_description.json
```

`dataset_description.json` is minimal (Name, BIDSVersion, DatasetType). Symlinks are used — never copy raw files.
All paths are resolved to absolute before mounting into Docker.

## Shared Docker Wrapper

```python
def build_docker_cmd(image: str, bids_dir: str, output_dir: str, work_dir: str,
                     fs_license: str, extra_args: list[str]) -> list[str]:
    # Returns tokenized command list for subprocess; validation returns this as-is.
```

Mounts (read-only where applicable):
- `-v {bids_dir}:/data:ro`
- `-v {output_dir}:/output`
- `-v {work_dir}:/work`
- `-v {fs_license}:/opt/freesurfer/license.txt:ro`

## Workflow: t1_deepprep

| Field | Value |
|---|---|
| Module | `workflows/deepprep.py` |
| Docker image | `pbfslab/deepprep:25.1.0` |
| Input requirement | `series.modality == "T1"` |
| BIDS subdir | `sub-01/anat/sub-01_T1w.nii.gz` |

**Docker command:**
```
docker run --rm \
  -v {bids}:/data:ro \
  -v {output}:/output \
  -v {work}:/work \
  -v {fs_license}:/opt/freesurfer/license.txt:ro \
  {image} /data /output participant --anat_only
```

**Progress milestones:** 10 (BIDS ready), 30 (container started), 70 (processing), 100 (done).

**Outputs discovered post-run under `output/`:** `qc_report` (html/json), `segmentation` (nii.gz), `brain_mask` (nii.gz).

## Workflow: dwi_qsiprep

| Field | Value |
|---|---|
| Module | `workflows/qsiprep.py` |
| Docker image | `pennlinc/qsiprep:26.0.0` |
| Input requirement | `series.modality == "DWI"` AND `has_bval` AND `has_bvec` |
| BIDS subdir | `sub-01/dwi/sub-01_dwi.{nii.gz,bval,bvec}` |

**Docker command:**
```
docker run --rm \
  -v {bids}:/data:ro \
  -v {output}:/output \
  -v {work}:/work \
  -v {fs_license}:/opt/freesurfer/license.txt:ro \
  {image} /data /output participant
```

**Progress milestones:** 10 (BIDS ready), 30 (container started), 50 (preprocessing), 70 (eddy/fieldmap), 100 (done).

**Outputs:** `qc_report`, `preprocessed_dwi` (nii.gz), `confounds` (tsv), `html_report`.

## Workflow: dwi_qsirecon

| Field | Value |
|---|---|
| Module | `workflows/qsirecon.py` |
| Docker image | `pennlinc/qsirecon:26.0.0` |
| Input requirement | `qsiprep_task_id` must reference completed `dwi_qsiprep` task |
| BIDS subdir | Reuses QSIPrep output dir as BIDS input |

**Docker command:**
```
docker run --rm \
  -v {qsiprep_output}:/data:ro \
  -v {output}:/output \
  -v {work}:/work \
  -v {fs_license}:/opt/freesurfer/license.txt:ro \
  {image} /data /output participant
```

**Progress milestones:** 10 (QSIPrep output verified), 30 (container started), 70 (reconstruction), 100 (done).

**Outputs:** `dti_fa` (nii.gz), `dti_md` (nii.gz), `tractography` (tck), `connectome` (csv), `html_report`.

## Workflow: dwi_qsi_full

| Field | Value |
|---|---|
| Module | `workflows/qsi_full.py` |
| Input requirement | Same as `dwi_qsiprep` |
| Behavior | Chains QSIPrep → QSIRecon sequentially. Creates two task records internally. |

**Chain logic:** Run QSIPrep to completion. On success, extract its task_id, then run QSIRecon with `qsiprep_task_id` pointing to it. If QSIPrep fails, QSIRecon is skipped and the full task is marked `failed`.

**Progress milestones:** 0-50 covers QSIPrep phase, 50-100 covers QSIRecon phase (scaled).

**Outputs:** Union of `dwi_qsiprep` and `dwi_qsirecon` outputs.

## Validation Variants (`_validate`)

Suffix `_validate` on any workflow_type. Shared validation entry-point:

```python
def validate(workflow_type: str, series, qsiprep_task_id: int | None) -> dict:
    # 1. Check Docker image exists via `docker image inspect {image}`
    # 2. Construct full docker command (do NOT launch)
    # 3. Return { image_available, command, bind_mounts }
```

Validation tasks:
- Skip BIDS construction (but verify paths exist).
- Set progress to 100 immediately.
- Return `output_type: "command"` with the resolved docker command string.
- Status is `completed` if image exists and command resolves; `failed` otherwise.
- No sudo, no subprocess launch.

## Output Discovery (post-run)

After a real container run completes, scan `derivatives/{task_id}/output/` for known file patterns and insert rows into the `outputs` table with `output_type` inferred from filename conventions (see phase2-api.md line 120 for the mapping). Unknown files are logged but not registered as outputs.
