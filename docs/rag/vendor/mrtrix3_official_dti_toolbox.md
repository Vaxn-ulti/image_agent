---
source_url: https://userdocs.mrtrix.org/en/latest/reference/commands/mrinfo.html, https://userdocs.mrtrix.org/en/latest/reference/commands/dwi2mask.html, https://userdocs.mrtrix.org/en/latest/reference/commands/mrconvert.html, https://userdocs.mrtrix.org/en/latest/reference/commands/dwi2tensor.html, https://userdocs.mrtrix.org/en/latest/reference/commands/tensor2metric.html, https://userdocs.mrtrix.org/en/latest/reference/commands/mrstats.html, https://userdocs.mrtrix.org/en/latest/reference/commands/mrcalc.html
raw_source_ids: mrtrix3_mrinfo, mrtrix3_dwi2mask, mrtrix3_mrconvert, mrtrix3_dwi2tensor, mrtrix3_tensor2metric, mrtrix3_mrstats, mrtrix3_mrcalc
retrieved_date: 2026-06-07
status: curated_summary
---

# MRtrix3 Official DTI Toolbox Commands

## Purpose / Scope

Use this source when maintaining or explaining the MRtrix toolbox portion of `dwi_fast_gpu_dti`.

Image Agent runs MRtrix commands inside a toolbox image, currently `pennlinc/qsiprep:latest`, but it does not run the full QSIPrep pipeline for production fast DTI.

## Container/CLI Usage

The backend checks that the toolbox image exposes:

```text
mrinfo
mrconvert
dwi2mask
dwi2tensor
tensor2metric
mrstats
mrcalc
```

`mrinfo`, `mrstats`, and `mrcalc` are part of the checked MRtrix toolbox surface. Treat them as official command availability evidence unless backend logs or provenance show a concrete run. The delivered scalar maps are produced by the current `dwi2tensor` and `tensor2metric` path.

The production runner uses a Docker command shape like:

```text
docker run --rm --gpus all --network host \
  -v {bids}:/data:ro \
  -v {output}:/out \
  -v {work}:/work \
  --entrypoint bash \
  pennlinc/qsiprep:latest \
  -lc "{mrtrix_command}"
```

Current command roles:

- `mrinfo` is an availability/inspection command for MRtrix-compatible image metadata;
- `dwi2mask` creates the DWI brain mask when possible;
- `mrconvert` converts mask formats for later MRtrix use;
- `dwi2tensor` fits the tensor from eddy-corrected DWI using rotated b-vectors;
- `tensor2metric` emits FA/MD/AD/RD maps from the tensor.
- `mrstats` and `mrcalc` are checked toolbox utilities for summary statistics and image math, but current result production should only claim their use when provenance or logs record it.

## Important Inputs/Outputs

Inputs:

- selected DTI subset in the task work directory;
- corrected DWI from host FSL `eddy_cuda`;
- rotated b-vectors and subset b-values;
- MRtrix-compatible mask.

Outputs:

- `mask.mif` and `mask.nii.gz`;
- `dti_tensor.mif`;
- native FA/MD/AD/RD maps;
- MNI152 FA/MD/AD/RD maps after FSL registration or fallback resampling;
- regional FA/MD/AD/RD TSVs and combined region table.

## Image Agent Notes

- `dwi_fast_gpu_dti` uses MRtrix as a toolbox for scalar DTI map production. It is not a full QSIPrep or QSIRecon execution.
- Preserve provenance flags: `full_qsiprep_run: false` and `full_qsirecon_run: false`.
- Delivered scalar outputs should be described as FA/MD/AD/RD maps and atlas tables produced by the fast DTI workflow.
- `mrinfo`, `mrstats`, and `mrcalc` may appear in runtime/toolbox checks; do not turn availability checks into claims that these commands produced the delivered FA/MD/AD/RD maps.
- If `tensor2metric` outputs non-finite values, the backend sanitizes delivered maps and records replacement counts in provenance; answers should mention the recorded provenance rather than inventing image-quality claims.
- container-native DWI QC for this workflow is the backend-registered result summary, provenance JSON, QC TSV, metric maps, MNI maps, and regional TSVs. Do not replace them with decorative or synthetic images.
- Raw source snapshots are traceability evidence only. Cite this curated summary plus backend task/result records for answer production.
- Do not expose patient identifiers, raw image contents, full host paths beyond documented deployment constants, license text, API keys, sudo passwords, or bearer tokens in prompts, RAG answers, logs, or tool outputs.
