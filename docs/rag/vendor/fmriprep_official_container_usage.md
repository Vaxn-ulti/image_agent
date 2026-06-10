---
source_type: rag_vendor
source_url: https://fmriprep.org/en/stable/usage.html, https://fmriprep.org/en/stable/installation.html
raw_source_ids: fmriprep_usage, fmriprep_installation
retrieved_date: 2026-06-06
status: curated_summary
---

# fMRIPrep Official Container Usage

## Purpose / 目的

fMRIPrep is a BIDS App for preprocessing fMRI/BOLD data and associated anatomical references. It expects a BIDS-valid input dataset and writes derivatives plus visual reports.

## Container/CLI Usage

Bare command pattern:

```bash
fmriprep <bids_dir> <output_dir> participant -w <work_dir>
```

Container pattern:

```bash
docker run --rm -it \
  -v /path/to/bids:/data:ro \
  -v /path/to/out:/out \
  -v /path/to/work:/work \
  -v /path/to/license.txt:/license.txt:ro \
  nipreps/fmriprep:<version> \
  /data /out participant \
  -w /work \
  --fs-license-file /license.txt
```

Common options:

- `--participant-label <label>`
- `--task-id <task>`
- `--skip-bids-validation` only when the operator accepts the risk.
- `--fs-license-file <path>` when FreeSurfer is enabled.

## Important Inputs/Outputs

Inputs:

- BIDS root with `sub-*` folders.
- At least one T1w structural image and BOLD series for standard fMRI preprocessing.
- Valid BOLD timing/task metadata.

Outputs:

- fMRIPrep derivatives under output directory.
- Preprocessed BOLD, masks, confounds, transforms, anatomical derivatives.
- HTML reports and logs/crash files.

## image_agent Notes

- Treat fMRIPrep outputs as the normal input family for XCP-D.
- Do not claim XCP-D-ready derivatives exist until registered outputs or filesystem checks confirm them.
- If BIDS validation fails, recommend fixing BIDS before bypassing validation.
- FreeSurfer license issues are common and should be explained as runtime configuration, not data pathology.
