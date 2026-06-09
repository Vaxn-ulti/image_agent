# Neuroimaging Terms

## BIDS-like

The MVP may construct a minimal BIDS-like tree sufficient for container validation and execution. It is not necessarily a full BIDS-validator-clean dataset unless the implementation adds full validation.

Typical paths:

- T1w: `sub-01/anat/sub-01_T1w.nii.gz`
- BOLD: `sub-01/func/sub-01_task-rest_bold.nii.gz`
- DWI: `sub-01/dwi/sub-01_dwi.nii.gz`, `.bval`, `.bvec`

## DeepPrep

Use for:

- T1w/anatomical preprocessing.
- fMRI/BOLD preprocessing in this product scope.

Do not claim DeepPrep calculates every downstream statistic unless a separate metric step is implemented and completed.

## QSIPrep

Use for DWI preprocessing. Requires gradient sidecars `.bval` and `.bvec`.

## QSIRecon

Use after QSIPrep completes. It consumes QSIPrep-compatible output, not raw DWI directly. Requires `--recon-spec` to select the reconstruction pipeline (e.g. `dipy`, `mrtrix`, `dsi_studio`).

## ALFF/fALFF

ALFF and fALFF are resting-state fMRI amplitude metrics. In this MVP, discuss them as single-subject BOLD downstream outputs after DeepPrep-BOLD preprocessing when backend output records show them. Other supported downstream outputs may include ReHo, DMN, and seed-to-ROI. Group-level BOLD analysis is a separate backend route.
