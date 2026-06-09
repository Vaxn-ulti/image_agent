---
source_url: https://qsiprep.readthedocs.io/en/stable/usage.html, https://qsiprep.readthedocs.io/en/stable/preprocessing.html
raw_source_ids: qsiprep_usage, qsiprep_preprocessing_outputs
retrieved_date: 2026-06-07
status: curated_summary
---

# QSIPrep Official Container Usage and Outputs

## Purpose / Scope

Use this source when maintaining legacy `dwi_qsiprep`, `dwi_qsiprep_validate`, and `dwi_qsi_full` paths, or when explaining why production Image Agent DWI currently prefers `dwi_fast_gpu_dti`.

This source documents QSIPrep container expectations and native QC/report artifacts. It does not make legacy QSIPrep the default production DWI path.

## Container/CLI Usage

Image Agent legacy QSIPrep uses a Docker image such as:

```text
pennlinc/qsiprep:latest
```

Backend command shape:

```text
docker run --rm --gpus all \
  -v {bids}:/data:ro \
  -v {output}:/output \
  -v {work}:/work \
  -v {fs_license}:/opt/freesurfer/license.txt:ro \
  -v {eddy_cuda_config}:/eddy_cuda_config.json:ro \
  pennlinc/qsiprep:latest \
  /data /output participant \
  --eddy-config /eddy_cuda_config.json
```

The backend must verify DWI BIDS-like inputs before launch: `.nii.gz`, `.bval`, `.bvec`, and JSON sidecar when required by the chosen workflow. For GPU runs, validate that an `eddy_cuda*` executable is available in the runtime image and that Docker GPU exposure is requested with `--gpus all`.

## Important Inputs/Outputs

Inputs:

- BIDS-like DWI tree mounted read-only at `/data`;
- task-scoped output and work directories mounted writable;
- FreeSurfer license mounted read-only;
- backend-generated `eddy_cuda_config.json` mounted read-only at `/eddy_cuda_config.json`;
- optional project T1/anat inputs when a workflow profile requires them.

Native outputs to discover and register when present:

- QSIPrep visual reports and HTML report assets;
- preprocessed DWI derivatives and masks;
- motion/eddy/confounds files;
- QC tables such as `desc-image_qc.tsv`;
- logs/provenance sufficient to determine whether CUDA eddy actually ran.

## Image Agent Notes

- Treat QSIPrep as a legacy/explicit DWI lane unless the user asks for it or existing task records make it relevant.
- `dwi_fast_gpu_dti` is the current production DWI path for bounded runtime scalar-map output; do not imply that a full QSIPrep run occurred for fast DTI outputs.
- `--eddy-config` is a backend-generated control file. The model may discuss the policy, but it must not invent per-subject eddy parameters without backend evidence.
- container-native DWI QC should use QSIPrep visual reports, QC TSVs, and derivative figures where available. Do not replace them with decorative or synthetic images.
- Raw source snapshots are traceability evidence only. RAG answers should cite this curated summary and backend task/output records, not quote raw HTML wholesale.
- Do not expose patient identifiers, raw image contents, full host paths, license text, API keys, sudo passwords, or bearer tokens in prompts, RAG answers, logs, or tool outputs.
