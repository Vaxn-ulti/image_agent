# T1 Feature Interpretation RAG

## Scope / 范围

Use for explaining T1 structural MRI features in non-diagnostic language.

## Common T1 Features

- Cortical thickness: estimated thickness of cortical gray matter by region.
- Surface area: regional cortical surface area estimates.
- Segmentation volumes: estimated volumes for tissue classes or anatomical labels.
- Subcortical volumes: volumes for structures such as ventricles, hippocampus, thalamus, or basal ganglia when available.
- Brain mask: binary mask identifying brain voxels for downstream processing.
- Transform: spatial mapping between subject T1w space and a template space such as MNI152.
- QC report: visual and numeric checks for registration, skull stripping, segmentation, and surface reconstruction.

## How To Explain / 如何解释

Say:

- "This is a structural summary derived from T1w preprocessing."
- "Regional values are research/analysis features and depend on pipeline settings, atlas, image quality, and subject population."
- "QC should be reviewed before interpreting morphometry."

Do not say:

- "Low hippocampal volume proves dementia."
- "Cortical thinning proves a diagnosis."
- "The scan is normal/abnormal" without a clinical report.

## Quality Flags

Mention these when present:

- Motion or ringing artifacts.
- Poor skull stripping.
- Failed pial or white matter surfaces.
- Missing FreeSurfer stats.
- Placeholder provenance.

## Good Short Answer

"The T1 summary contains FreeSurfer-derived structural features such as cortical thickness, surface area, and segmentation volumes. These are useful for research-style morphometry and QC review, but they are not diagnostic by themselves."

