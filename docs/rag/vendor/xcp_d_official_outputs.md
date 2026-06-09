---
source_url: https://xcp-d.readthedocs.io/en/stable/outputs.html
raw_source_ids: xcp_d_outputs
retrieved_date: 2026-06-06
status: curated_summary
---

# XCP-D Official Outputs

## Purpose / Mudi

Use this source when explaining what XCP-D should contribute after fMRIPrep-compatible preprocessing and what the UI should surface as native QC/output evidence.

## Container/CLI Usage

This page documents outputs rather than launch syntax. Use it together with `xcp_d_official_container_usage.md` for command setup.

Representative report paths:

```text
xcp_d/
  sub-<label>.html
  sub-<label>[_ses-<label>]_executive_summary.html
```

## Important Inputs/Outputs

XCP-D writes BIDS-like derivatives. Output categories include:

- summary reports, including a NiPreps-style participant summary and an executive summary;
- parcellation and atlas outputs;
- anatomical outputs where supported by the selected workflow inputs;
- functional outputs such as denoised or residual BOLD data;
- time series, connectivity matrices, ALFF/ReHo derivatives, quality-control, framewise-displacement, and confounds files depending on options.

## Image Agent Notes

- Treat XCP-D HTML summaries and executive summaries as container-native QC artifacts.
- Treat linc/ABCC report assets produced by XCP-D as container-native XCP-D QC, not generated substitute imagery.
- Preserve XCP-D outputs as research derivatives; do not phrase connectivity, ALFF, ReHo, or denoising metrics as clinical findings.
- For result summaries, classify XCP-D reports, figures, tables, metrics, and maps with `source_stage: xcpd` when paths or log names indicate XCP-D.
- If expected XCP-D outputs are missing, first check input derivative layout, selected `--mode`, output spaces, and task logs.
