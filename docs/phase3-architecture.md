# Phase 3 Architecture — DICOM Ingestion, BOLD Workflows, Export/Visualization

## Overview

Phase 3 extends the image_agent platform with three capabilities layered on Phase 2’s T1/DWI workflows:

1. **DICOM Archive Upload & Conversion** — accept `.zip`/`.tar.gz` archives containing DICOM slices, organize by SeriesInstanceUID, and convert to NIfTI-1 via `dcm2niix`.
2. **BOLD Detection & Functional Workflows** — detect BOLD/fMRI NIfTI from header dimensionality, then run fMRIPrep / DeepPrep and downstream ALFF/fALFF computation.
3. **Output Export & Visualization Contract** — download single outputs, export task/project bundles, and generate preview thumbnails for 3D/4D volumes.

## Storage Layout (additions)

```
data/projects/{project_id}/
  raw/                          # existing NIfTI uploads
  dicom/                        # NEW
    {dicom_series_id}/          # one dir per DICOM series extracted from archive
      *.dcm                     # individual DICOM slices
  derivatives/{task_id}/
    bids/                       # existing
    output/                     # existing + new BOLD outputs
    work/                       # existing
    previews/                   # NEW — generated thumbnails/pngs
```

## Database Changes

### Modified tables

**`files`** — add column:
```sql
ALTER TABLE files ADD COLUMN dicom_series_uid TEXT;
```

**`imaging_series`** — add columns:
```sql
ALTER TABLE imaging_series ADD COLUMN dicom_series_uid TEXT;
ALTER TABLE imaging_series ADD COLUMN source TEXT DEFAULT 'nifti';  -- 'nifti' | 'dicom'
```

### New table: `dicom_archives`

```sql
CREATE TABLE dicom_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    file_id INTEGER REFERENCES files(id),
    original_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    series_count INTEGER DEFAULT 0,
    extraction_status TEXT DEFAULT 'pending',  -- pending|extracting|extracted|failed
    error_message TEXT,
    created_at TEXT NOT NULL
);
```

### New table: `dicom_series`

```sql
CREATE TABLE dicom_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archive_id INTEGER NOT NULL REFERENCES dicom_archives(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    series_uid TEXT NOT NULL,
    series_description TEXT,
    series_number INTEGER,
    modality TEXT,               -- MR, CT, PT, etc.
    slice_count INTEGER,
    conversion_status TEXT DEFAULT 'pending',  -- pending|converting|converted|failed|skipped
    nifti_file_id INTEGER REFERENCES files(id),
    imaging_series_id INTEGER REFERENCES imaging_series(id),
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
```

### Modified `tasks` — no schema change; new `workflow_type` values only.

### Modified `outputs` — no schema change; new `output_type` values only.

## Workflow Type Registry (new entries)

| workflow_type | Label | Modality | Depends On |
|---|---|---|---|
| `bold_fmriprep` | BOLD fMRIPrep | BOLD | — |
| `bold_fmriprep_validate` | BOLD fMRIPrep Validate | BOLD | — |
| `bold_deepprep` | BOLD DeepPrep | BOLD | — |
| `bold_deepprep_validate` | BOLD DeepPrep Validate | BOLD | — |
| `bold_alff` | BOLD ALFF | BOLD | fmriprep or deepprep task |
| `bold_falff` | BOLD fALFF | BOLD | fmriprep or deepprep task |
| `bold_alff_validate` | BOLD ALFF Validate | BOLD | fmriprep or deepprep task |
| `bold_falff_validate` | BOLD fALFF Validate | BOLD | fmriprep or deepprep task |
| `bold_full` | BOLD fMRIPrep + ALFF/fALFF | BOLD | — |
| `bold_full_validate` | BOLD Full Validate | BOLD | — |

## Docker Images (new)

| Image | Tag | Purpose |
|---|---|---|
| `nipreps/fmriprep` | `24.1.1` | fMRIPrep BOLD preprocessing |
| `pbfslab/deepprep` | `25.1.0` | DeepPrep BOLD (same image, different args vs T1) |
| `pbfslab/alfp` | `0.2.0` | ALFF/fALFF computation |

## DICOM-to-NIfTI Conversion Contract

Uses `dcm2niix` (bundled in a minimal Docker image or host binary). The conversion:

1. Scans `data/projects/{p}/dicom/{series_id}/` for `.dcm` files.
2. Runs: `dcm2niix -z y -f sub-{project_id}_%p -o <output_dir> <dicom_dir>`
3. Picks up the resulting `.nii.gz`, `.bval`, `.bvec`, `.json` sidecars.
4. Creates an `imaging_series` row with `source='dicom'` and detected modality.
5. If DWI is detected from DICOM tags (b-value > 0), `.bval`/`.bvec` are linked as sidecars.
6. If BOLD is detected (multi-volume 4D), modality is set to `BOLD`.

## BOLD Detection Logic

Extends `apps/api/app/imaging/detect.py`:

- Check NIfTI header: dim[4] > 1 and dim[0] >= 4 → candidate 4D (time series)
- Reject DWI: if sidecar `.bval` exists with b > 0 values → DWI, not BOLD
- Reject structural: if dim[4] == 1 and dim[0] == 3 → T1/T2, not BOLD
- Filename heuristics: tokens `bold`, `fmri`, `rest`, `task` increase confidence
- Sidecar `.json` RepetitionTime < 3.0 seconds → boosts BOLD confidence

## Output Export & Visualization Contract

### Export formats

| Scope | Endpoint | Format |
|---|---|---|
| Single output | `GET /outputs/{id}/download` | Raw file (Content-Disposition: attachment) |
| Task bundle | `GET /tasks/{id}/export` | `.tar.gz` of all outputs + log + metadata.json |
| Project bundle | `GET /projects/{id}/export` | `.tar.gz` of raw + derivatives + manifest.json |

### Visualization (preview) contract

| output_type | Preview method | Format |
|---|---|---|
| `bold_brain` | Middle-slice mosaic (time avg + 3 orthogonal slices) | PNG |
| `brain_mask` | 3-slice overlay on T1 or BOLD mean | PNG |
| `alff_map` | Glass brain (3-view maximum intensity projection) | PNG |
| `falff_map` | Glass brain (3-view maximum intensity projection) | PNG |
| `tractography` (existing) | 3D render snapshot (already supported) | PNG |
| `html_report` | Serve raw HTML (Content-Type: text/html) | HTML |
| `qc_report` | Serve raw HTML | HTML |
| `connectome` | Matrix heatmap thumbnail | PNG |

Preview generation runs post-task via a lightweight `nibabel` + `matplotlib` script. Previews are stored at `derivatives/{task_id}/previews/` and registered in `outputs.preview_path`.

## Progress Milestones (new workflows)

### bold_fmriprep
10 BIDS → 30 container → 50 anatomical → 70 functional → 85 surface → 100 done

### bold_alff / bold_falff
10 verify input → 30 bandpass filter → 60 compute ALFF → 80 z-score → 100 done

### bold_full (chained)
0–60 fMRIPrep phase → 60–100 ALFF/fALFF phase

## Test Plan

### DICOM upload & conversion
1. `POST /projects/{id}/upload-dicom` with a synthetic DICOM archive (.zip containing 3 series: T1, DWI, BOLD)
2. `GET /projects/{id}/dicom-series` returns 3 series with correct modalities
3. `POST /dicom-series/{id}/convert` triggers conversion for each series
4. Poll `GET /dicom-series/{id}/status` until `converted`
5. Verify `imaging_series` rows created with `source='dicom'`
6. Verify NIfTI files exist in `data/projects/{p}/raw/`

### BOLD detection
7. Upload a synthetic 4D NIfTI (64×64×30×150) → detect as BOLD
8. Upload a synthetic 4D NIfTI with .bval (b>0) → detect as DWI, not BOLD
9. Upload a 3D NIfTI → detect as T1, not BOLD

### fMRIPrep workflow
10. `POST /series/{id}/run` with `workflow_type=bold_fmriprep` → task queued
11. Poll task → progress advances through 5 milestones → completed
12. `GET /tasks/{id}/outputs` returns `preprocessed_bold`, `confound_timeseries`, `brain_mask`, `html_report`

### ALFF/fALFF workflow
13. `POST /series/{id}/run` with `workflow_type=bold_alff` → requires `preprocessed_bold` output from fMRIPrep task
14. Poll → completed with `alff_map`, `alff_zscore`
15. Repeat for `bold_falff` → outputs include `falff_map`, `falff_zscore`

### Export & visualization
16. `GET /outputs/{id}/download` → returns file with correct Content-Type
17. `GET /tasks/{id}/export` → returns .tar.gz containing all outputs + metadata
18. For each BOLD output_type with preview contract, verify `preview_path` is populated and file exists

### Validation mode (no Docker)
19. `POST /series/{id}/run` with `workflow_type=bold_fmriprep_validate` → immediate progress 100, returns command string
20. Same for `bold_alff_validate`, `bold_falff_validate`, `bold_full_validate`

### Chained workflow
21. `POST /series/{id}/run` with `workflow_type=bold_full` → fMRIPrep runs first (0–60), then ALFF + fALFF (60–100)
22. Outputs include fMRIPrep outputs + both ALFF and fALFF maps

### DICOM conversion error cases
23. Upload a non-DICOM .zip → extraction fails with clear error
24. Upload a DICOM archive with 0 recognizable series → series_count=0, status=extracted but conversion skipped
25. Cancel a conversion in progress → status=cancelled

### Preview generation edge cases
26. 4D BOLD with >1000 volumes → only first 10 volumes used for mean image
27. ALFF map with NaN values → replace with 0 before rendering
