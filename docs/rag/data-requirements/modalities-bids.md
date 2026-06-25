---
source_type: rag_data_requirement
status: current_contract
retrieved_date: 2026-06-13
---

# Modalities and BIDS Requirements RAG

## Purpose / 目的

Use this for preflight explanations about whether uploaded MRI data are ready for T1, BOLD, or DWI workflows.

## BIDS Basics

A BIDS dataset should contain:

- `dataset_description.json`
- subject folders like `sub-01/`
- modality folders such as `anat/`, `func/`, `dwi/`, `fmap/`
- NIfTI images with matching JSON sidecars where required

## DICOM Conversion Boundary

Official dcm2niix grounding: `docs/rag/vendor/dcm2niix_official_conversion.md`.

- DICOM archives are candidates for conversion, not direct production workflow launch.
- Convert DICOM to converted NIfTI plus BIDS sidecar JSON where possible before staging T1, BOLD, or DWI workflows.
- Existing BIDS sidecar JSON outranks converted metadata; converted DICOM-derived metadata outranks NIfTI header and filename-token guesses.
- Record partial conversion failures from backend inventory instead of claiming that the whole upload failed or succeeded.
- Do not expose raw DICOM contents, patient identifiers, full sensitive host paths, or PHI-bearing conversion logs to the LLM; in short, do not expose raw DICOM contents.

## T1w Anatomy

Typical path:

```text
sub-01/anat/sub-01_T1w.nii.gz
sub-01/anat/sub-01_T1w.json
```

Use for:

- T1 DeepPrep.
- Anatomical reference for fMRIPrep-style BOLD preprocessing.
- FreeSurfer/recon-all structural features.

## BOLD fMRI

Typical path:

```text
sub-01/func/sub-01_task-rest_bold.nii.gz
sub-01/func/sub-01_task-rest_bold.json
```

Important JSON fields:

- `TaskName`
- `RepetitionTime` or valid equivalent timing metadata
- `SliceTiming` when applicable
- phase-encoding fields when fieldmap/distortion correction is expected

Use for:

- BOLD preprocessing.
- XCP-D-style postprocessing after fMRIPrep-compatible derivatives exist.
- ALFF/fALFF/ReHo/connectivity metrics after preprocessing.

## DWI

Typical path:

```text
sub-01/dwi/sub-01_dwi.nii.gz
sub-01/dwi/sub-01_dwi.bval
sub-01/dwi/sub-01_dwi.bvec
sub-01/dwi/sub-01_dwi.json
```

Use for:

- DWI tensor workflows.
- QSIPrep/QSIRecon-like workflows when supported.

## Source Priority For Metadata

Recommended priority:

1. Existing BIDS sidecar JSON.
2. DICOM tags from conversion.
3. NIfTI header metadata.
4. Filename/protocol tokens.

## Registered Data Candidate Selection

The agent should use backend tools such as `list_data_candidates` and `select_incubation_dataset` before proposing sandbox validation on real data. These tools read registered `imaging_series`, `files`, task state, and safe filesystem existence signals; they must not read raw image contents or expose sensitive absolute paths to the model.

Selection priority:

1. Series modality matches the workflow modality.
2. `supported_for_processing` is true and no unsupported reason is present.
3. BIDS-ready data or sidecar-complete data ranks above raw or ambiguous data.
4. DWI requires `.json`, `.bval`, and `.bvec`; fast GPU DTI also needs phase-encoding/readout metadata.
5. DICOM archives can be candidates for conversion/incubation, but not direct BOLD/T1 production workflow launch until converted or staged.
6. Storage existence and project-root scope are evidence, but raw patient image contents are never returned to the LLM.

The selected candidate is for sandbox validation or confirmation preparation only. Selecting a candidate must keep `production_task_created: false`.

## Agent Preflight Language

"This series is eligible for `<workflow>` because it is detected as `<modality>` and has the required sidecars."  
"This series is blocked because `<missing requirement>`."
