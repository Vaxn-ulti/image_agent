# Concrete Examples and Evals

## Developer Example 1: Add DeepPrep BOLD Validate

Task: Implement validate-only `bold_deepprep_validate`.

Expected changes:

- Backend accepts workflow type.
- Eligibility requires BOLD series.
- BIDS-like func tree includes a `_bold.nii.gz` file.
- Validation returns Docker command and bind mounts without launching container.
- Tests cover eligible and missing-BOLD cases.
- Chat recommends DeepPrep BOLD for BOLD series.

## Developer Example 2: Prevent BIDS Collision

Task: Two BOLD runs map to the same subject/task.

Expected changes:

- Second file receives `run-2` or another deterministic unique entity.
- No overwrite occurs.
- Inventory reports both target paths.
- Test asserts stable naming across repeated ingest.

## Developer Example 3: DWI Without Gradients

Task: User uploads DWI NIfTI without `.bval`/`.bvec`.

Expected behavior:

- Series may be detected as DWI.
- QSIPrep eligibility is false.
- Reason identifies missing gradient files.
- Chat does not recommend running QSIPrep until gradients are present.

## Developer Example 4: Production DWI Missing JSON

Task: User uploads DWI NIfTI with `.bval` and `.bvec` but no JSON sidecar.

Expected behavior:

- `dwi_fast_gpu_dti` and `dwi_fast_gpu_dti_validate` are rejected before task launch.
- Error names the missing JSON sidecar fields `PhaseEncodingDirection` and `TotalReadoutTime`.
- QSIPrep/QSI legacy workflows may still use `.bval`/`.bvec` rules, but the production DWI path must not fabricate `acqparams.txt`.
- Tests cover upload metadata, run-request validation, and BIDS staging of `sub-01_dwi.json` from `json_file_id`.

## Developer Example 5: Validate Placeholder Versus Real Summary

Task: A real `dwi_fast_gpu_dti` run finishes after validate-only checks were added.

Expected behavior:

- Validate-only summaries set `validation_only: true` or `placeholder_outputs: true`.
- Real DWI summaries are built from existing FA/MD/AD/RD native maps, MNI152 maps, and atlas regional tables.
- Real DWI summaries set `validation_only: false`.
- T1 placeholder contract summaries remain machine-readable via `extraction_status=placeholder_contract_pending_real_deepprep_parser`.
- Real T1 summaries parse DeepPrep/Freesurfer `brainvol.stats` and `lh/rh.aparc.stats`, write frontend-ready TSVs, and use `extraction_status=real_deepprep_freesurfer_stats`.
- The production command path uses the backend lightweight runner, host FSL GPU `eddy_cuda`, and MRtrix toolbox commands from `pennlinc/qsiprep:latest`.
- The command path does not contain full `qsiprep /data /out participant` or full QSIRecon execution.
- Runtime/provenance records the 35 minute target or the measured bottleneck when it misses that target.

## Developer Example 6: BOLD Workflow Naming

Task: A user asks whether `bold_second_level` is a group-level analysis.

Expected behavior:

- Preserve workflow type for compatibility.
- Label and docs describe it as single-subject downstream metrics after BOLD DeepPrep.
- Group-level analysis remains under `/projects/{project_id}/bold/group-analysis`.

## Developer Example 7: BOLD Historical Descriptive Review

Task: A developer uses the old `bold_descriptive_review_20260521` reports to improve current BOLD outputs.

Expected behavior:

- Treat the historical reports as descriptive-only examples, not second-level inference.
- Preserve remote real `bold_descriptive_review.py`, `bold_group_analysis.py`, and `bold_metrics.py` implementations when syncing local work.
- Reuse useful conventions such as MNI152NLin6Asym res-02 outputs, EPI-derived masks, PCC seed-FC maps, Schaefer 200 / 7-network heatmaps, and motion QC overlays.
- Keep `bold_second_level` as the single-subject downstream metric workflow after DeepPrep.

## Eval Checklist

- `SKILL.md` remains concise and references hold details.
- Workflow contracts are updated in `docs/workflows`.
- Tests cover concrete example behavior.
- QSIRecon commands include `--recon-spec`.
- Production DWI fast GPU DTI requires JSON sidecar metadata and never hard-codes phase encoding.
- Production DWI fast GPU DTI uses host FSL plus MRtrix toolbox mode and does not run full QSIPrep/QSIRecon.
- BOLD downstream metrics are not described as group-level second-level analysis.
- Historical BOLD descriptive review outputs are not represented as inference.
- Placeholder summaries are machine-readable and not confused with real extracted features.
- No README or broad process document is added for skills.
