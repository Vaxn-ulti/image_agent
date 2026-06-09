---
source_url: https://deepprep.readthedocs.io/en/latest/outputs.html, https://deepprep.readthedocs.io/en/24.1.0/usage_local.html, https://deepprep.readthedocs.io/en/latest/usage_cluster.html
raw_source_ids: deepprep_outputs, deepprep_usage_local, deepprep_usage_cluster
retrieved_date: 2026-06-06
status: curated_summary
---

# DeepPrep Official Container Usage

## Purpose / 目的

DeepPrep is a deep-learning empowered preprocessing workflow for anatomical and functional MRI data in BIDS format. It can run anatomical-only, BOLD-only, or combined preprocessing, and it requires a FreeSurfer license.

## Container/CLI Usage

Docker pattern:

```bash
docker run --rm -it --gpus all \
  -v /path/to/bids:/input:ro \
  -v /path/to/output:/output \
  -v /path/to/license.txt:/fs_license.txt:ro \
  pbfslab/deepprep:<version> \
  /input /output participant \
  --fs_license_file /fs_license.txt
```

T1/anatomical-only pattern:

```bash
docker run --rm --gpus all \
  -v /path/to/bids:/input:ro \
  -v /path/to/output:/output \
  -v /path/to/license.txt:/fs_license.txt:ro \
  pbfslab/deepprep:<version> \
  /input /output participant \
  --anat_only \
  --fs_license_file /fs_license.txt
```

BOLD task example:

```bash
docker run --rm --gpus all \
  -v /path/to/bids:/input:ro \
  -v /path/to/output:/output \
  -v /path/to/license.txt:/fs_license.txt:ro \
  pbfslab/deepprep:<version> \
  /input /output participant \
  --bold_task_type rest \
  --fs_license_file /fs_license.txt
```

## Important Inputs/Outputs

Inputs:

- BIDS dataset.
- T1w anatomy for anatomical preprocessing.
- BOLD runs with task labels for functional preprocessing.
- FreeSurfer license file.

Outputs:

- DeepPrep output directory with anatomical reconstruction and functional derivatives according to selected flags.
- Recon/FreeSurfer-style directories for anatomical processing.
- BOLD confounds, volume/surface outputs, and reports when functional processing is enabled.

Official output source id: `deepprep_outputs`.

Anatomical derivatives:

- DeepPrep stores FreeSurfer-aligned anatomical derivatives under `Recon/`, including `mri/`, `surf/`, `label/`, `stats/`, scripts/log-like processing records, segmentation/parcellation outputs, morphometry statistics, and registration files.
- Image Agent should treat these as structural preprocessing and morphometry artifacts. They support QC and research summaries, not clinical diagnosis.

Functional derivatives:

- DeepPrep stores functional derivatives under `BOLD/` in a BIDS-like layout, including preprocessed BOLD, BOLD reference images, masks, motion transforms, registration transforms, confounds TSV/JSON, tSNR, and optional surface/CIFTI outputs.
- BOLD derivative outputs should be registered as maps, tables, metrics, or logs only after files exist. Downstream BOLD metrics remain separate Image Agent result-summary evidence.

Visual reports:

- DeepPrep writes visual reports under `QC/`, including subject/session HTML report files, figures, logs, `report.html`, and `timeline.html`.
- Register DeepPrep HTML report artifacts in `outputs.reports`.
- Register previewable DeepPrep PNG/SVG/JPEG/WebP report figures in `outputs.figures`.
- Use container-native DeepPrep QC and report files for display. Do not replace missing DeepPrep visual reports with generated or decorative images.

## image_agent Notes

- In this repo, `t1_deepprep` and `bold_deepprep` may use the same image with different flags.
- GPU is recommended but CPU mode may be possible with `--device cpu`; do not promise acceptable runtime.
- Explain missing license as a configuration blocker.
- Use backend `provenance` to distinguish real parsed FreeSurfer stats from placeholder result contracts.
- `placeholder_outputs=true` means the result summary is a contract or validation placeholder, not real parsed DeepPrep/FreeSurfer output.
