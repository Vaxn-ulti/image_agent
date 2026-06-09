---
source_url: https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/eddy/users_guide/index.html, https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/dtifit.html, https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/flirt/user_guide.html, https://fsl.fmrib.ox.ac.uk/fsl/docs/registration/fnirt/user_guide.html, https://fsl.fmrib.ox.ac.uk/fsl/docs/utilities/fslutils.html
raw_source_ids: fsl_eddy_users_guide, fsl_dtifit, fsl_flirt_user_guide, fsl_fnirt_user_guide, fsl_utils
retrieved_date: 2026-06-07
status: curated_summary
---

# FSL Official Fast DTI Tools

## Purpose / Scope

Use this source when maintaining or explaining `dwi_fast_gpu_dti`, the Image Agent production DWI path.

This is a host FSL tool contract. It is not evidence that full QSIPrep or QSIRecon ran.

## Container/CLI Usage

FSL is used from the configured host installation, not as the primary workflow container:

```text
IMAGE_AGENT_FSL_DIR=/home/yyf/project/MCI_project/tools/fsl
```

The runtime preflight checks these host FSL commands:

```text
eddy_cuda
dtifit
flirt
applywarp
fslmaths
```

The `applywarp probe` is grounded in the official FNIRT/applywarp registration surface and is a runtime availability check kept for compatibility and future registration work. The current `dwi_fast_gpu_dti` implementation applies affine MNI registration with `flirt` and falls back to header-based resampling when affine validation fails; do not claim that `applywarp` ran unless backend provenance says so.

The `fslmaths` check is grounded in the official FSL utilities surface. Current production DTI map delivery does not depend on `fslmaths`; treat it as a host-tool availability check unless task provenance records a concrete `fslmaths` operation.

The production runner calls FSL GPU eddy with the selected DTI subset, a backend-generated mask, `acqparams.txt`, `index.txt`, bvec/bval sidecars, and `--out=.../eddy_corrected`. It requires `eddy_cuda` when `--require-gpu-eddy` is set.

## Important Inputs/Outputs

Inputs:

- DWI NIfTI plus `.bval`, `.bvec`, and JSON sidecar;
- JSON metadata containing phase-encoding and readout timing sufficient to build eddy files;
- task-scoped output/work/resource directories;
- MNI template and atlas resources for registration and regional tables.

Outputs:

- eddy-corrected DWI and rotated b-vectors;
- affine registration artifacts from `flirt`;
- MNI152 metric maps when registration or fallback resampling succeeds;
- provenance recording host FSL path, GPU eddy path, registration method, and runtime.

## Image Agent Notes

- `dwi_fast_gpu_dti` is the production DWI path for bounded FA/MD/AD/RD output.
- Use host FSL for `eddy_cuda` and `flirt`; do not describe this workflow as a full QSIPrep or QSIRecon run.
- If backend provenance says `full_qsiprep_run: false` and `full_qsirecon_run: false`, preserve that boundary in answers and reports.
- `dtifit` is checked as part of the FSL DTI tool surface, but current scalar-map fitting is done through MRtrix `dwi2tensor` and `tensor2metric`; do not claim `dtifit` produced the delivered maps unless provenance shows it.
- `applywarp` and `fslmaths` are checked as part of the host FSL/FSL utilities surface; do not claim either command transformed or edited delivered maps unless backend logs or provenance show a concrete command.
- container-native DWI QC for this workflow means registered backend artifacts: `qc/qc_report.tsv`, `qc/dwi_fast_gpu_dti_provenance.json`, finite FA/MD/AD/RD maps, MNI maps, and regional TSVs. Do not replace them with synthetic figures.
- Raw source snapshots are traceability evidence only. Cite this curated summary plus backend task/result records for answer production.
- Do not expose patient identifiers, raw image contents, full host paths beyond documented deployment constants, license text, API keys, sudo passwords, or bearer tokens in prompts, RAG answers, logs, or tool outputs.
