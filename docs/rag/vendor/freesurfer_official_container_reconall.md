---
source_url: https://surfer.nmr.mgh.harvard.edu/fswiki/recon-all, https://surfer.nmr.mgh.harvard.edu/fswiki/ReconAllOutputFiles
raw_source_ids: freesurfer_recon_all, freesurfer_recon_all_outputs
retrieved_date: 2026-06-07
status: curated_summary
---

# FreeSurfer recon-all Official Usage

## Purpose / 目的

`recon-all` performs FreeSurfer cortical reconstruction and volumetric segmentation. It is often used directly or indirectly by T1 preprocessing workflows such as DeepPrep and fMRIPrep with FreeSurfer enabled.

## Container/CLI Usage

Typical direct command:

```bash
export SUBJECTS_DIR=/path/to/subjects
recon-all -subject sub-01 -i /path/to/sub-01_T1w.nii.gz -all
```

Equivalent subject id flags:

- `-subject`
- `-subjid`
- `-sid`
- `-s`

Stepwise directives:

- `-autorecon1`: early processing through skull strip.
- `-autorecon2`: segmentation/surface construction stages.
- `-autorecon3`: spherical morph and parcellation statistics.
- `-all` or `-autorecon-all`: full automated stream.

## Important Inputs/Outputs

Inputs:

- One or more T1 MRI inputs as DICOM, NIfTI, MGH/MGZ.
- Optional T2/FLAIR inputs for pial surface refinement.
- `SUBJECTS_DIR` destination.

Outputs:

- `$SUBJECTS_DIR/<subject>/mri/`
- `$SUBJECTS_DIR/<subject>/surf/`
- `$SUBJECTS_DIR/<subject>/label/`
- `$SUBJECTS_DIR/<subject>/stats/`
- Logs under `$SUBJECTS_DIR/<subject>/scripts/`.

Official output source id: `freesurfer_recon_all_outputs`.

The official `ReconAllOutputFiles` page is the source-grounded boundary for delivered FreeSurfer artifacts. Use it to identify real output families rather than inventing new report names.

Structural maps and volumes:

- `mri/orig.mgz`, `mri/rawavg.mgz`, `mri/brainmask.mgz`, `mri/aseg.mgz`, and related normalization/segmentation volumes are FreeSurfer anatomical outputs.
- Register previewable or downloadable MGZ/NIfTI-converted structural maps in `outputs.maps` only after files exist.
- Treat segmentation volumes as preprocessing/morphometry evidence, not as clinical findings.

Surfaces and labels:

- `surf/lh.white`, `surf/rh.white`, `surf/lh.pial`, `surf/rh.pial`, and related inflated/spherical surfaces are reconstruction outputs.
- `label/lh.aparc.annot`, `label/rh.aparc.annot`, and other annotation/label files identify parcellations used by stats tables.
- Surface and annotation files are provenance and derivative artifacts. Do not summarize them as diagnostic anatomy.

Statistics and tables:

- `stats/aseg.stats`, `stats/lh.aparc.stats`, `stats/rh.aparc.stats`, and related `*.stats` files are the primary FreeSurfer morphometry tables.
- Parsed or copied stats belong in `outputs.tables` or `outputs.metrics`, with provenance showing which original `stats/*.stats` file was parsed.
- If the backend reports `placeholder_outputs=true`, do not present expected stats filenames as measured values.

Logs and QC:

- `scripts/recon-all.log`, `scripts/recon-all-status.log`, and related script records belong in `outputs.logs`.
- FreeSurfer-native QC should use available surfaces, segmentation images, snapshots, stats, and logs from the derivative tree. Register generated views or snapshots in `outputs.figures` only when they are derived from these native artifacts.
- Use container-native FreeSurfer QC for display. Do not replace missing FreeSurfer snapshots or stats with decorative images.

## image_agent Notes

- FreeSurfer stats are morphometry features, not diagnoses.
- Surface failures or skull-strip errors should be treated as QC problems.
- If DeepPrep result-summary reports `real_deepprep_freesurfer_stats`, the agent may explain parsed FreeSurfer-derived features.
- Do not infer disease from cortical thickness or volume values without a validated clinical context.
