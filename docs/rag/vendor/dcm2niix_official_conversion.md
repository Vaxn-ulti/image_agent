---
source_type: rag_vendor
source_url: https://raw.githubusercontent.com/rordenlab/dcm2niix/master/README.md
raw_source_ids: dcm2niix_readme
retrieved_date: 2026-06-07
status: curated_summary
---

# dcm2niix Official DICOM Conversion

## Purpose

Use this source when explaining DICOM to NIfTI conversion before Image Agent can stage BIDS-like inputs for T1, BOLD, or DWI workflows. Official source id: `dcm2niix_readme` from `rordenlab/dcm2niix`.

`dcm2niix` is a DICOM to NIfTI converter. In Image Agent it is an ingest/conversion dependency, not a scientific preprocessing container and not a substitute for BIDS validation.

## Container/CLI Usage

Typical command shape:

```text
dcm2niix -z y -o /path/to/output /path/to/dicom_or_folder
```

The backend may invoke dcm2niix during mixed upload ingest when a DICOM archive or folder is present. The converter writes converted NIfTI files and may write BIDS sidecar JSON files with metadata derived from DICOM headers.

## Important Inputs/Outputs

Inputs:

- DICOM files, DICOM folders, or archives expanded by the backend ingest layer.
- A writable conversion output directory scoped to the project/session.

Outputs:

- converted NIfTI files such as `.nii` or `.nii.gz`;
- BIDS sidecar JSON when metadata export is available;
- conversion logs or stderr/stdout captured by the backend;
- partial conversion failures when some DICOM series fail but other files convert successfully.

## Image Agent Notes

- DICOM archives are candidates for conversion and incubation, not direct production workflow launch.
- Do not launch T1/BOLD/DWI production workflows directly from raw DICOM contents. Convert or stage as BIDS-like NIfTI first.
- The agent may say that `dcm2niix executable not found` blocks DICOM conversion when backend inventory records that failure.
- Treat converted sidecar metadata as lower priority than an existing trusted BIDS sidecar, but higher priority than NIfTI header or filename token guesses.
- Do not expose raw DICOM contents, patient identifiers, full sensitive host paths, or conversion log tails containing PHI to the LLM or UI.
- Agent wording should include the boundary phrase "do not expose raw DICOM contents" when explaining privacy limits.
- A successful conversion does not prove that BIDS is validator-clean. Workflow preflight must still check modality, sidecars, naming, and required metadata.
- For DWI, conversion is not enough: the backend still needs `.bval`, `.bvec`, and JSON sidecar metadata required by the selected workflow.
