# Claude Test Agent Report — Real Neuroimaging Sample Tests

**Date**: 2026-05-13  
**API**: http://localhost:8000 (Brain Image Agent v0.2.0)  
**Source data**: F:\MCI患者データ (uploaded via orchestrator)

---

## Executive Summary

| # | Test | Result | Real Data? | Details |
|---|------|--------|------------|---------|
| 1 | Extension preservation (.nii vs .nii.gz) | PASS | Mixed | Both uncompressed `.nii` and compressed `.nii.gz` preserved in BIDS paths |
| 2 | BOLD/fMRI bold_deepprep_validate | PASS | YES (227 MB) | Real MCI BOLD 128×128×33×210, int16, `.nii` validated successfully |
| 3 | T1 t1_deepprep_validate | PASS | No (synthetic) | T1 256×256×176 validated; real MCI T1 sample NOT AVAILABLE |
| 4 | DWI dwi_qsiprep_validate | PASS | No (synthetic) | DWI 128×128×60×30 + bval/bvec validated; real MCI DWI sample NOT AVAILABLE |
| 5 | Dataset ingest BIDS path preservation | PASS | Mixed | Mixed extensions in zip ingest produce correct BIDS paths |
| 6 | Negative: wrong modality rejection | PASS | — | bold_deepprep_validate on T1 → 400 |
| 7 | Negative: DWI without bval/bvec | PASS | — | dwi_qsiprep_validate on solo DWI → 400 |
| 8 | Negative: unsupported sequence | PASS | — | t1_deepprep_validate on FLAIR → 400 |
| 9 | Container image availability | PASS | — | deepprep, qsiprep, qsirecon all present |
| 10 | FS license | PASS | — | /home/yyf/codex/license.txt exists |

**Overall**: 10/10 passing. 1 critical gap: only BOLD has a real MCI sample.

---

## Real MCI Data Inventory

### Available (uploaded from F:\MCI患者データ)

| Modality | File | Size | Shape | Format | Project | Series ID |
|----------|------|------|-------|--------|---------|-----------|
| BOLD/fMRI | `52090000_ep2d_pace_moco_p2_2mm_20230911154621_2.nii` | 227 MB (216.6 MB payload) | 128×128×33×210 | int16, uncompressed `.nii` | 12 | 21 |

**NIfTI header details**:
- sizeof_hdr: 348 (valid NIfTI-1)
- datatype: 4 (int16), bitpix: 16
- pixdim: [1.875, 1.875, 3.5, 2.0] mm
- TR: 2.0 s, 210 timepoints = 7 min acquisition
- magic: `n+1` (single-file .nii)

### Missing (not yet uploaded from F:\MCI患者データ)

| Modality | Needed for | Priority |
|----------|-----------|----------|
| T1w (MPRAGE) | t1_deepprep_validate, anatomical reference | HIGH |
| DWI + bval + bvec | dwi_qsiprep_validate, diffusion processing | HIGH |

**Next fix**: Copy T1 MPRAGE and DWI samples from `F:\MCI患者データ` to the orchestrator upload directory, then re-run tests 3 and 4 against real data.

---

## Test Details

### Test 1: Extension Preservation

**Setup**: Project 16 (`test-ext-preservation`). Uploaded uncompressed `.nii` T1 and compressed `.nii.gz` DWI via individual endpoints, plus a mixed dataset zip with both extensions.

**Individual upload results**:

| Upload method | File | Storage path ends with |
|--------------|------|----------------------|
| POST /upload | sub-test_T1w.nii | `.nii` ✓ |
| POST /upload-dwi | sub-test_dwi.nii.gz | `.nii.gz` ✓ |
| POST /upload-dwi | sub-test_dwi.bval | `.bval` ✓ (sidecar preserved) |
| POST /upload-dwi | sub-test_dwi.bvec | `.bvec` ✓ (sidecar preserved) |

**Dataset ingest BIDS paths**:

| Source | BIDS path | Extension correct? |
|--------|-----------|-------------------|
| subj2_T1w.nii | bids/rawdata/sub-01/anat/sub-01_T1w.nii | YES (.nii preserved) |
| subj2_task-rest_bold.nii.gz | bids/rawdata/sub-01/func/sub-01_bold.nii.gz | YES (.nii.gz preserved) |

**On-disk verification**:
```
bids/rawdata/
  dataset_description.json
  participants.tsv
  sub-01/anat/sub-01_T1w.nii          ← .nii, not .nii.gz
  sub-01/func/sub-01_bold.json        ← sidecar linked
  sub-01/func/sub-01_bold.nii.gz      ← .nii.gz preserved
```

**API responses recorded**:
- `POST /projects/16/upload` → 200, file_type=NIFTI, storage_path ends `.nii`
- `POST /projects/16/upload-dwi` → 200, files[0].file_type=NIFTI, storage_path ends `.nii.gz`
- `POST /projects/16/datasets/8/ingest` → 200, inventory_status=completed

---

### Test 2: BOLD/fMRI DeepPrep Validate (Real MCI Data)

**Setup**: Project 12, series 21. Real MCI BOLD file: 227 MB uncompressed `.nii`, 128×128×33×210, int16, 7-min resting-state fMRI.

**Detection** (from inventory):
```json
{
  "modality": "BOLD",
  "sequence_label": "task_fMRI_BOLD",
  "confidence": 0.9,
  "supported_for_processing": true,
  "shape": [128, 128, 33, 210],
  "datatype": 4, "bitpix": 16
}
```

**Validation run (task 36)**:
- `POST /series/21/run` with `workflow_type: bold_deepprep_validate` → 200
- Task transition: queued → running → completed (100%)
- Docker image: `pbfslab/deepprep:25.1.0` — available ✓
- FS license: `/home/yyf/codex/license.txt` — exists ✓

**Command generated**:
```
docker run --rm --network host \
  -v <derivatives/36/bids>:/data:ro \
  -v <derivatives/36/output>:/output \
  -v <derivatives/36/work>:/work \
  -v /home/yyf/codex/license.txt:/opt/freesurfer/license.txt:ro \
  pbfslab/deepprep:25.1.0 \
  /data /output participant \
  --fs_license_file /opt/freesurfer/license.txt \
  --skip_bids_validation --bold_task_type rest --cpus 8 --memory 24
```

**BIDS workspace layout** (symlinks to rawdata):
```
derivatives/36/bids/
  dataset_description.json
  sub-01/func/
    sub-01_task-rest_bold.json  → rawdata symlink
    sub-01_task-rest_bold.nii   → rawdata symlink  (.nii preserved ✓)
```

**Log tail**:
```
[2026-05-13T13:33:52.685388] Workspace ready: .../derivatives/36
[2026-05-13T13:33:52.737752] COMMAND docker run --rm --network host ...
```

---

### Test 3: T1 DeepPrep Validate

**Setup**: Project 17. Synthetic T1 256×256×176, float32, `.nii.gz`.

**Detection**:
```json
{
  "modality": "T1",
  "sequence_label": "T1w_MPRAGE",
  "confidence": 0.9,
  "supported_for_processing": true
}
```

**Validation run (task 37)**:
- `POST /series/32/run` with `workflow_type: t1_deepprep_validate` → 200
- Status: completed (100%)
- Docker image: `pbfslab/deepprep:25.1.0` — available ✓

**Command generated**:
```
docker run --rm --network host \
  -v <bids>:/data:ro -v <output>:/output -v <work>:/work \
  -v /home/yyf/codex/license.txt:/opt/freesurfer/license.txt:ro \
  pbfslab/deepprep:25.1.0 \
  /data /output participant \
  --fs_license_file /opt/freesurfer/license.txt \
  --skip_bids_validation --anat_only --cpus 8 --memory 24
```

**Negative test**: `POST /series/32/run` with `workflow_type: bold_deepprep_validate` → 400 "BOLD DeepPrep requires a BOLD/fMRI series" ✓

**Gap**: Real MCI T1 sample not available. Synthetic data used (256×256×176 header only, no real voxel data).

---

### Test 4: DWI QSIPrep Validate

**Setup**: Project 18. Synthetic DWI 128×128×60×30, float32, `.nii.gz` + bval + bvec.

**Detection**:
```json
{
  "modality": "DWI",
  "sequence_label": "DWI_multi_shell",
  "confidence": 0.95,
  "supported_for_processing": true,
  "has_bval": true,
  "has_bvec": true
}
```

**Uploaded files**:
| File type | Path |
|-----------|------|
| NIFTI | projects/18/raw/sub-mci_dwi.nii.gz |
| BVAL | projects/18/raw/sub-mci_dwi.bval |
| BVEC | projects/18/raw/sub-mci_dwi.bvec |

**Validation run (task 38)**:
- `POST /series/33/run` with `workflow_type: dwi_qsiprep_validate` → 200
- Status: completed (100%)
- Docker image: `pennlinc/qsiprep:latest` — available ✓

**Command generated**:
```
docker run --rm --gpus all --network host \
  -e TEMPLATEFLOW_HOME=/templateflow \
  -v <bids>:/data:ro -v <output>:/out -v <work>:/work \
  -v /home/yyf/codex/license.txt:/opt/freesurfer/license.txt:ro \
  pennlinc/qsiprep:latest \
  /data /out participant --participant-label 01 \
  --fs-license-file /opt/freesurfer/license.txt \
  --skip-bids-validation --output-resolution 2 \
  --nthreads 8 --omp-nthreads 4 --mem 24000 -w /work --notrack
```

**Negative test**: DWI uploaded without bval/bvec sidecars → `dwi_qsiprep_validate` rejected with 400 "DWI workflows require DWI series with bval and bvec" ✓

**Gap**: Real MCI DWI + bval + bvec samples not available. Synthetic data used.

---

### Test 5: Dataset Ingest with Mixed Extensions

**Setup**: Project 16, upload session 8. Zip archive containing:
- `subj2/anat/subj2_T1w.nii` (uncompressed)
- `subj2/func/subj2_task-rest_bold.nii.gz` (compressed)
- `subj2/func/subj2_task-rest_bold.json` (sidecar)

**Ingest result**: `inventory_status: completed`

**BIDS output**:
| Source | BIDS path | Extension |
|--------|-----------|-----------|
| subj2_T1w.nii | bids/rawdata/sub-01/anat/sub-01_T1w.nii | `.nii` ✓ |
| subj2_task-rest_bold.nii.gz | bids/rawdata/sub-01/func/sub-01_bold.nii.gz | `.nii.gz` ✓ |
| subj2_task-rest_bold.json | bids/rawdata/sub-01/func/sub-01_bold.json | `.json` ✓ |

---

## Container Runtime

All required Docker images are available:

| Workflow | Image | Available |
|----------|-------|-----------|
| t1_deepprep | pbfslab/deepprep:25.1.0 | ✓ |
| bold_deepprep | pbfslab/deepprep:25.1.0 | ✓ |
| dwi_qsiprep | pennlinc/qsiprep:latest | ✓ |
| dwi_qsirecon | pennlinc/qsirecon:latest | ✓ |
| dwi_qsi_full | pennlinc/qsiprep:latest | ✓ |

FS license: `/home/yyf/codex/license.txt` exists ✓

---

## Pass/Fail Matrix

```
TEST                              RESULT    DATA SOURCE
─────────────────────────────────────────────────────────
Extension .nii preserved          PASS      Mixed synthetic/real
Extension .nii.gz preserved       PASS      Synthetic
BOLD bold_deepprep_validate       PASS      ✓ REAL MCI (227 MB)
T1 t1_deepprep_validate           PASS      ✗ Synthetic only
DWI dwi_qsiprep_validate          PASS      ✗ Synthetic only
Dataset ingest extensions         PASS      Synthetic
Wrong modality rejection          PASS      —
DWI w/o bval/bvec rejection       PASS      —
Unsupported sequence rejection    PASS      —
Container images present          PASS      —
FS license present                PASS      —
─────────────────────────────────────────────────────────
TOTAL                             10/10
```

---

## Exact Next Fixes

### Critical

1. **Upload real MCI T1w (MPRAGE) sample**
   - Source: `F:\MCI患者データ\<patient>\anat\` or DICOM series
   - Upload via `POST /projects/{id}/upload` or dataset ingest
   - Re-run `t1_deepprep_validate` and verify command against real 3D anatomical data
   - Expected: 3D shape (e.g., 256×256×176), float32/int16, `.nii` or `.nii.gz`

2. **Upload real MCI DWI + bval + bvec samples**
   - Source: `F:\MCI患者データ\<patient>\dwi\` (NIfTI + gradient tables)
   - Upload via `POST /projects/{id}/upload-dwi` (3 files) or dataset ingest
   - Re-run `dwi_qsiprep_validate` and verify command against real multi-shell DWI
   - Expected: 4D shape, bval multi-shell (b=0, b=1000, b=2000+), bvec coordinate triplets

### Recommended

3. **Test real BOLD execution (not just validation)**
   - Run `bold_deepprep` (non-validate) on series 21
   - Requires: `IMAGE_AGENT_SUDO_PASSWORD` env var set, Docker + GPU available
   - 227 MB input, ~30–60 min runtime expected
   - Verify outputs registered in `derivatives/{task_id}/`

4. **Add missing real BOLD sidecars**
   - The real MCI BOLD has a `.json` sidecar but check for `*_bold.json` with TaskName, RepetitionTime, etc.
   - BIDS validation may fail without complete metadata

5. **Test dataset ingest with real multi-subject MCI data**
   - Package multiple subjects from F:\MCI患者データ into a single zip
   - Verify BIDS participant labeling (sub-01, sub-02, …)
   - Verify inventory counts match expected modalities per subject

### Observations (non-blocking)

6. The BOLD file from project 11 (3.5 MB) appears to be a truncated/incomplete upload of the same real MCI file — the full copy is 227 MB in project 12. Delete or re-upload project 11.
7. FLAIR sequences are correctly detected as unsupported and rejected. If FLAIR processing is needed, add it to `sequence_support()` in `apps/api/app/imaging/detect.py`.
8. The `_nifti_ext()` helper in pipeline.py at `apps/api/app/workflows/pipeline.py:75` correctly handles both `.nii` and `.nii.gz` — no changes needed.
