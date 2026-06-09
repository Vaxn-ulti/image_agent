# Container-Native QC Artifacts

Use this reference when reviewing result-summary reports, frontend display readiness, or user-facing explanations of workflow outputs.

## Review Rules

1. Prefer container-native QC artifacts over generated substitutes.
2. Check that fMRIPrep HTML report, XCP-D HTML report, DeepPrep QC, and FreeSurfer snapshots/stats are registered when expected for the workflow.
3. Confirm native reports appear under `outputs.reports`; native figures under `outputs.figures`; TSV/CSV/JSON metrics under `outputs.tables` or `outputs.metrics`; NIfTI/CIFTI/GIFTI maps under `outputs.maps`; logs under `outputs.logs`.
4. Treat generated HTML indexes, report-builder PNGs, or galleries as derived presentation aids over native artifacts, not replacements for the container-native QC.
5. If native QC is missing, report an artifact-readiness gap and recommend rerun, output discovery repair, or registration repair.
6. Keep all interpretation non-diagnostic.

For final real-output report acceptance, run `python apps/api/scripts/verify_scientific_reports.py` with `--projects-root data/projects --task-ids 41 111 114 --require-modalities T1 BOLD DWI --require-container-native-qc --min-native-qc-images 1` or equivalent explicit output directories. The verifier checks derived presentation reports while also requiring container-native QC; generated report assets do not replace native QC. Remote strict smoke may also include `--require-scientific-report-artifacts`; treat `scientific_report_artifacts_status=passed` as report-layer evidence for `reports/index.html`, `reports/report_manifest.json`, PNG assets, and derived provenance, not as native-QC proof. In short, derived presentation does not replace native QC.

## Evidence To Cite

Use exact task id and artifact paths:

- `outputs.reports[].relative_path`
- `outputs.figures[].relative_path`
- `outputs.tables[].relative_path`
- `outputs.maps[].relative_path`
- `outputs.logs[].relative_path`
- `provenance.pipeline`
- `provenance.container_images`
- `artifact_role`
- `native_artifact`
- `provenance.replaces_native_qc`
- `validation_only`

## Safe Wording

Good: "Task 118 has fMRIPrep native report assets registered, but XCP-D report assets are not present yet."

Bad: "The QC proves this subject is normal."
