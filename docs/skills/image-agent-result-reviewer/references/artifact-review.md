# Artifact Review

## Review Sources

Use these sources in priority order:

1. `/tasks/{task_id}/result-summary`.
2. `/tasks/{task_id}/artifact-manifest` as the preferred frontend-readiness source for preview/download rows.
3. Registered output records.
4. Report manifest and scientific report summary artifacts.
5. Task output directory listing.
6. Task logs.

Screenshots and chat summaries are secondary evidence. They can point you to a problem but should not be the only proof of completion.

## Completeness Checks

For each artifact family, check:

- file exists;
- `relative_path` is non-empty and inside task output;
- `download_url` resolves through the artifact endpoint;
- `content_type` matches file type;
- `size_bytes` is present and nonzero where expected;
- the manifest envelope uses `contract_version=artifact_manifest_v1`; artifact items carry a valid `preview_kind`, safe `relative_path`, recomputed `download_url`, `content_type`, `size_bytes`, and no backend `path` leakage;
- feature group, modality, atlas, and space match the artifact content;
- reports include `reports/index.html` and a manifest when the report layer is expected.

## Modality Reminders

- T1 real summaries should identify real DeepPrep/Freesurfer stats rather than placeholder extraction.
- BOLD downstream summaries should identify MNI152 voxelwise metrics, connectivity/QC tables, and matching mask provenance.
- DWI fast DTI summaries should include FA, MD, AD, RD maps, MNI152 maps, regional DTI tables, finite-map provenance, and `full_qsiprep_run: false`.

## Common Failures

- Validate-only placeholder files presented as real analysis outputs.
- Empty registered output path.
- Local absolute path exposed instead of artifact URL.
- Result summary says one atlas while tables were generated with another.
- Report HTML exists but is not registered under `outputs.reports`.
