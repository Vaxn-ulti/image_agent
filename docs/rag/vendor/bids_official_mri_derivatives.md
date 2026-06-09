---
source_url: https://bids-specification.readthedocs.io/en/stable/modality-specific-files/magnetic-resonance-imaging-data.html, https://bids-specification.readthedocs.io/en/stable/derivatives/introduction.html
raw_source_ids: bids_mri, bids_derivatives
retrieved_date: 2026-06-06
status: curated_summary
---

# BIDS Official MRI and Derivatives Boundaries

## Purpose / Mudi

Use this source when explaining BIDS readiness, MRI sidecar boundaries, DWI sidecar requirements, and the distinction between raw BIDS and derivative datasets.

## Container/CLI Usage

BIDS is a data layout specification, not a container runtime. Validate layouts with an official validator before production workflow launch:

```bash
bids-validator <bids_dir>
```

Use `bids_validator_official_cli_docker.md` for validator CLI and Docker details.

## Important Inputs/Outputs

MRI BIDS readiness:

- MR modality metadata lives in sidecar JSON files whenever possible.
- Functional BOLD data belong under `func/` with `_bold` NIfTI files and matching JSON sidecars.
- DWI data belong under `dwi/` and require NIfTI plus `.bval`, `.bvec`, and JSON sidecar files for Image Agent processing.
- Required and recommended metadata depend on modality and acquisition; do not infer missing timing or phase-encoding values when the workflow needs them.

Derivative boundary:

- Raw BIDS is curated source data.
- A derivative dataset is produced from at least one valid BIDS dataset.
- Derivative outputs should preserve enough metadata for reuse and should follow derivative naming/storage conventions.

## Image Agent Notes

- BOLD fMRIPrep starts from raw BIDS; XCP-D starts from preprocessing derivatives.
- DICOM archives are candidates for conversion/incubation, not direct production BOLD/T1/DWI launch until staged as BIDS or a supported derivative input.
- When chaining derivatives, preserve mandatory JSON metadata where it remains valid.
- Explain missing BIDS requirements as workflow readiness blockers, not medical findings.
