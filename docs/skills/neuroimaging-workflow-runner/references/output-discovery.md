# Output Discovery

## Principles

- Register outputs only after real execution completes.
- Keep unknown files in logs but do not invent output types.
- Store relative and absolute paths consistently with existing backend schema.
- Preserve task failure evidence in logs before raising or returning failure.
- Never register an empty output path. For command/validate metadata without a natural artifact, write `metadata/<output_type>_output.json` under the task output directory and register that file.
- Result-summary output items should expose `relative_path`, `download_url`, `content_type`, and `size_bytes` for frontend consumption.
- Artifact HTTP responses should agree with summary metadata. In particular, `.nii.gz` files served through `/tasks/{task_id}/artifacts/{relative_path}` should use `application/gzip`.

## Expected Output Types

DeepPrep T1:

- QC report.
- Segmentation.
- Brain mask.
- HTML report where present.
- Real FreeSurfer stats inventory:
  - `t1_brain_measures.tsv`;
  - `t1_t1w_regions.tsv`;
  - `t1_freesurfer_stats_inventory.tsv`;
  - copied raw stats text under `tables/freesurfer_stats/*.tsv`.
- Known-good real T1 references: tasks `40` and `41`, each with 16 brain measures, 68 cortical regions, 9 stats files, 5 T1w maps, and 2 transform references.
- MNI152 should be represented by real transform/map references unless a real MNI-space regional feature table is produced.

DeepPrep BOLD:

- Preprocessed BOLD.
- Confounds.
- Brain mask/reference outputs where present.
- QC or HTML report.

Fast GPU DTI (`dwi_fast_gpu_dti`):

- FA, MD, AD, and RD maps.
- MNI152-space DTI maps.
- Atlas regional DTI tables.
- QC/provenance that records host FSL path, MRtrix toolbox image, `full_qsiprep_run: false`, `full_qsirecon_run: false`, and measured or configured runtime limit where available.
- Real runs must register a result summary from existing output files with `validation_only: false`.
- Validate-only runs may create placeholder maps/tables only when provenance marks `validation_only: true` and `placeholder_outputs: true`.
- Validate-only summaries must preserve their actual workflow type, for example `dwi_fast_gpu_dti_validate`.
- Known-good real references:
  - task `107` on project 22 / series 38 completed with `runtime_sec=1156`;
  - task `112` on project 23 / series 39 completed with `runtime_sec=1042`;
  - task `114` on mixed project 13 / series 24 completed with `runtime_sec=1021`.
  All used 28-volume DTI subsets, native and MNI152 FA/MD/AD/RD maps, HarvardOxford regional TSVs, and `validation_only=false`.
- Legacy BIDS-ingested DWI records may have sidecar paths in `metadata.sidecars` instead of newer uploaded sidecar file IDs. Stage and validate those sidecars when the series is BIDS-like, but keep ordinary `/upload-dwi` records strict about requiring an explicit JSON sidecar.
- Delivered DTI metric maps must be finite. If `tensor2metric` emits NaN/inf values, sanitize the native and MNI maps and record `metric_sanitization` counts in provenance. Task `112` records `114` native and `142` MNI replacements per metric, with delivered maps verified at `0` non-finite voxels.
- The result summary atlas must match the actual prepared atlas metadata in `mni152_resources/dwi_dti_mni_atlas.json`.

Legacy QSIPrep:

- Preprocessed DWI.
- Confounds.
- QC report.
- HTML report.

QSIRecon (depends on `--recon-spec`):

- DTI FA.
- DTI MD.
- Tractography.
- Connectome.
- HTML report.
- Pipeline-specific derivatives per the selected recon spec.

Downstream BOLD metrics:

- `bold_second_level` is a single-subject downstream package after completed BOLD DeepPrep, not the group-analysis endpoint.
- Expected MNI152 outputs include ALFF, fALFF, ReHo, tSNR/RSFA, DMN/network tables, 15-seed seed-to-ROI tables, seed timeseries, and `summary/bold_result_summary.json` when the metric workflow completes.
- Real downstream BOLD should register the unified BOLD result summary as `kind=result_summary`; legacy `bold_metrics_summary` is a compatibility artifact.
- If DeepPrep provides MNI BOLD but no matching MNI mask, the runner may generate a MNI/EPI mask from finite, nonzero, dynamic BOLD voxels. Never use a T1w mask with MNI BOLD metric maps.
- Known-good real references:
  - task `110` on project 14 / series 25 from DeepPrep task `45`;
  - task `111` on project 13 / series 23 from DeepPrep task `64`.
  Both produced MNI152 maps with shape `91 x 109 x 91`, 15-seed seed-to-ROI TSVs with 226 lines, DMN summaries, seed time-series tables, and API result summaries with BOLD feature groups.
- Group-level BOLD analysis remains a separate `/projects/{project_id}/bold/group-analysis` route.
- Historical descriptive review outputs can include per-subject ALFF, PCC seed-FC, Schaefer 200 / 7-network FC heatmaps, and motion QC overlays. Register or report them as descriptive review artifacts, not statistical inference.
