---
source_type: rag_interpretation
status: current_guidance
retrieved_date: 2026-06-13
---

# BOLD Feature Interpretation RAG

## Scope / 范围

Use for explaining resting-state or task BOLD/fMRI outputs in non-diagnostic language.

## Common BOLD Features

- Preprocessed BOLD: motion-corrected and spatially transformed BOLD time series.
- Confounds: nuisance regressors such as motion, global signals, CompCor, and non-steady-state indicators.
- Framewise displacement (FD): volume-to-volume motion summary.
- DVARS: signal-change summary across voxels between volumes.
- ALFF: amplitude of low-frequency fluctuations.
- fALFF: ALFF normalized by broader frequency power.
- ReHo: local regional homogeneity of BOLD time series.
- tSNR: temporal signal-to-noise ratio.
- Seed-to-ROI connectivity: association between a seed time series and region/atlas time series.
- Connectivity matrix: pairwise association among regions.

## Interpretation Rules / 解释规则

- BOLD signals are indirect measures related to blood oxygenation, not direct neural firing.
- Connectivity metrics are sensitive to motion, denoising choices, temporal filtering, and atlas definitions.
- Single-subject values are usually descriptive unless compared with a validated normative or study-specific reference.
- QC comes before interpretation.

## Motion Language

Good:

- "Higher FD suggests more head motion and may reduce reliability."
- "Check censoring/scrubbing and confound outputs before interpreting connectivity."

Avoid:

- "The subject has impaired connectivity."
- "ALFF confirms disease."

## Agent Answer Pattern

1. State whether the workflow is preprocessing, postprocessing, or both.
2. Name the available BOLD feature groups.
3. Explain the main metrics in plain language.
4. Add QC and non-diagnostic caveats.
