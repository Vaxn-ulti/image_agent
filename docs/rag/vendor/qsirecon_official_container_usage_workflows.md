---
source_type: rag_vendor
source_url: https://qsirecon.readthedocs.io/en/stable/quickstart.html, https://qsirecon.readthedocs.io/en/stable/builtin_workflows.html, https://qsirecon.readthedocs.io/en/stable/building_workflows.html
raw_source_ids: qsirecon_quickstart, qsirecon_builtin_workflows, qsirecon_custom_workflows
retrieved_date: 2026-06-08
status: curated_summary
---

# QSIRecon Official Container Usage and Workflows

## Purpose / Scope

Use this source when maintaining legacy `dwi_qsirecon`, `dwi_qsirecon_validate`, and `dwi_qsi_full` paths, especially dependency checks and `--recon-spec` handling.

QSIRecon consumes completed QSIPrep output. It is not a direct raw-DWI preprocessing entrypoint.

## Container/CLI Usage

Image Agent legacy QSIRecon uses a Docker image such as:

```text
pennlinc/qsirecon:latest
```

Backend command shape:

```text
docker run --rm --gpus all \
  -v {qsiprep_output}:/data:ro \
  -v {output}:/out \
  -v {work}:/work \
  -v {fs_license}:/opt/freesurfer/license.txt:ro \
  pennlinc/qsirecon:latest \
  /data /out participant \
  --participant-label sub-01 \
  --input-type qsiprep \
  --recon-spec {recon_spec}
```

`--recon-spec` selects the reconstruction workflow. The backend must fail fast when it is missing, undefined, or unsupported.

QSIRecon custom workflow coverage is manifest-backed by `qsirecon_custom_workflows`. Official custom specs are YAML authoring references: `Custom Reconstruction Workflows` says QSIRecon workflows are defined in YAML files. Pipeline-level metadata lives at the root-level `name`, `anatomical`, and `nodes` fields. A node in the QSIRecon `nodes` list represents a unit of processing. All nodes must have a name element.

Current Image Agent profiles:

- `dki`: `--recon-spec dipy_dki --skip-odf-reports --notrack`
- `tractography`: `--recon-spec mrtrix_multishell_msmt_noACT`
- custom YAML spec: official custom-workflow documentation explains the YAML format, but Image Agent production is policy-limited to backend-approved profiles; it is not arbitrary user-supplied custom specs in production.

## Important Inputs/Outputs

Inputs:

- completed QSIPrep output mounted read-only;
- task-scoped output and work directories mounted writable;
- FreeSurfer license mounted read-only;
- a valid reconstruction spec selected by backend policy.

Native outputs to discover and register when present:

- QSIRecon visual reports and HTML report assets;
- scalar maps such as FA/MD or DKI outputs selected by the recon spec;
- tractography/connectome outputs when the selected workflow emits them;
- reconstruction provenance and logs identifying the `--recon-spec` used.

## Image Agent Notes

- QSIRecon requires completed QSIPrep output. Do not launch or recommend it directly against raw DWI files.
- Keep the dependency visible in agent answers: `dwi_qsirecon` follows a completed `dwi_qsiprep` task, while `dwi_qsi_full` runs QSIPrep before QSIRecon.
- Preserve the official YAML boundary for custom workflows. Do not call custom QSIRecon specs JSON, and do not imply arbitrary user-authored YAML specs are production-runnable unless backend policy explicitly supports them.
- No CUDA-specific QSIRecon CLI flag is assumed. Image Agent records Docker GPU visibility instead of inventing undocumented CUDA switches.
- container-native DWI QC should use QSIRecon report artifacts and derivative figures when present. Do not replace them with decorative or synthetic images.
- If backend task records and RAG disagree, backend task/output records are authoritative for whether QSIPrep completed and which QSIRecon profile ran.
- Raw source snapshots are traceability evidence only. RAG answers should cite this curated summary and backend task/output records, not quote raw HTML wholesale.
- Do not expose patient identifiers, raw image contents, full host paths, license text, API keys, sudo passwords, or bearer tokens in prompts, RAG answers, logs, or tool outputs.
