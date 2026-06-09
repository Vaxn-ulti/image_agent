---
source_url: https://fmriprep.org/en/stable/outputs.html
raw_source_ids: fmriprep_outputs
retrieved_date: 2026-06-06
status: curated_summary
---

# fMRIPrep Official Outputs

## Purpose / Mudi

Use this source when explaining what a completed fMRIPrep run should expose for result review, downstream XCP-D handoff, and container-native QC display.

## Container/CLI Usage

This page documents output products rather than launch syntax. Use it together with `fmriprep_official_container_usage.md` for the command contract.

Output tree pattern:

```text
<output_dir>/
  logs/
  sub-<label>/
  sub-<label>.html
  dataset_description.json
```

## Important Inputs/Outputs

fMRIPrep outputs are BIDS Derivatives and include three broad product families:

- visual QA reports, including one subject-level HTML report;
- preprocessed derivatives such as anatomical derivatives, functional derivatives, masks, transforms, and resampled BOLD data;
- confounds files used by later denoising and postprocessing steps.

The visual report is a first-class QC artifact. It should be shown or linked directly when available instead of replacing it with a hand-made summary figure.

## Image Agent Notes

- Treat `sub-<label>.html` as container-native QC evidence for fMRIPrep.
- A valid fMRIPrep derivative tree is the normal input boundary for XCP-D with `--input-type fmriprep`.
- For result summaries, classify fMRIPrep HTML as `artifact_role: qc_report` and `source_stage: fmriprep`.
- Do not claim preprocessing success from the existence of a raw BOLD file alone; require task status, registered outputs, or filesystem evidence.
