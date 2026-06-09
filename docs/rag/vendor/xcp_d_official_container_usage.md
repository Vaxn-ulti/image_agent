---
source_url: https://xcp-d.readthedocs.io/en/stable/usage.html, https://xcp-d.readthedocs.io/en/stable/installation.html
raw_source_ids: xcp_d_usage, xcp_d_installation
retrieved_date: 2026-06-06
status: curated_summary
---

# XCP-D Official Container Usage

## Purpose / 目的

XCP-D postprocesses preprocessed fMRI derivatives. It commonly consumes fMRIPrep outputs and produces denoised BOLD data, QC outputs, time series, and connectivity-related derivatives.

## Container/CLI Usage

Bare command pattern:

```bash
xcp_d /path/to/fmriprep /path/to/xcpd_out participant \
  --mode linc \
  --participant-label 01
```

Docker pattern:

```bash
docker run --rm -it \
  -v /path/to/fmriprep:/fmriprep:ro \
  -v /path/to/work:/work \
  -v /path/to/xcpd_out:/out \
  pennlinc/xcp_d:<version> \
  /fmriprep /out participant \
  --mode linc \
  --input-type fmriprep \
  --file-format nifti \
  -w /work
```

Wrapper-specific flags for the current image_agent remote XCP-D path:

- Use `--mode linc` for the linc-mode postprocessing profile.
- Use `--input-type fmriprep` when the input is fMRIPrep-compatible derivatives.
- Use `--file-format nifti` for NIfTI derivative input/output expectations.
- Use `--linc-qc y` and `--abcc-qc y` when the wrapper requires container-native XCP-D QC outputs from those QC paths.

Apptainer/Singularity pattern:

```bash
apptainer run --cleanenv -B /path/to/data:/data xcp_d-<version>.simg \
  /data/fmriprep /data/xcpd_out participant \
  --mode linc \
  --participant-label 01
```

## Important Inputs/Outputs

Inputs:

- fMRIPrep/Nibabies/HCP/DCAN/UKB-like derivatives, selected by `--input-type`.
- Preprocessed BOLD in supported spaces.
- Functional mask, boldref, confounds TSV/JSON.
- Anatomical mask and transforms between native and standard space.
- `dataset_description.json` in derivative directories.

Outputs:

- XCP-D derivative tree.
- Denoised BOLD, QC metrics, motion summaries, time series, and connectivity outputs depending on mode/settings.
- Logs and crash files under the output tree.

## image_agent Notes

- XCP-D is not a raw-BIDS preprocessing tool; it needs preprocessing derivatives and should be described as not raw BIDS.
- `--mode` is required in current XCP-D releases.
- If XCP-D fails with missing files, check fMRIPrep output spaces and derivative layout before blaming the raw scan.
- Connectivity and denoising outputs are research features, not clinical conclusions.
