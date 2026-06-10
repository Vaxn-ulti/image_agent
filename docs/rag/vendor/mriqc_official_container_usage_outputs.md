---
source_type: rag_vendor
source_url: https://mriqc.readthedocs.io/en/latest/usage.html, https://mriqc.readthedocs.io/en/latest/reports.html, https://mriqc.readthedocs.io/en/latest/install.html, https://www.nipreps.org/apps/docker/, https://www.nipreps.org/apps/singularity/
raw_source_ids: mriqc_usage, mriqc_reports, mriqc_installation, nipreps_docker_guidelines, nipreps_singularity_guidelines
retrieved_date: 2026-06-08
status: curated_summary
---

# MRIQC Official Container Usage and Outputs

## Purpose / Scope

Use this source when explaining MRIQC as an official NiPreps quality-control workflow, when comparing Image Agent native QC expectations with external MRIQC reports, or when evaluating a future incubation proposal for MRIQC.

This document does not make MRIQC a current Image Agent production workflow. MRIQC is not registered in WORKFLOW_REGISTRY, and Image Agent must not claim MRIQC task launch, MRIQC result-summary output, or MRIQC artifact registration unless a future backend workflow and real remote evidence are added.

## Container/CLI Usage

MRIQC follows the BIDS-app command shape:

```text
mriqc /data /out participant
```

A Docker-style Image Agent incubation command would need to preserve the same primitive boundaries:

```text
docker run --rm \
  -v {bids}:/data:ro \
  -v {output}:/out \
  nipreps/mriqc:latest \
  /data /out participant
```

NiPreps also documents Docker and Singularity/Apptainer usage patterns for applications in the ecosystem. Those container guidelines are grounding for runtime decomposition and image inspection, not proof that Image Agent has production MRIQC orchestration.

MRIQC can also be run in group mode after participant-level outputs exist:

```text
mriqc /data /out group
```

The `--no-sub` option disables subject-level report generation. If Image Agent ever incubates MRIQC, the preflight must preserve this flag's consequence: no subject visual report should be promised when `--no-sub` was used.

## Important Inputs/Outputs

Inputs:

- BIDS dataset mounted read-only.
- Task-scoped writable output directory.
- Optional work/cache directories if a backend incubation plan adds them.

Native outputs to discover and register only if a future backend workflow exists:

- individual visual reports for participant runs;
- group visual report for group runs;
- IQMs and related tabular/JSON quality metrics;
- logs/provenance sufficient to identify MRIQC version, runtime image, participant/group level, and options such as `--no-sub`.

## Image Agent Notes

- MRIQC is an official external QC workflow, not a production Image Agent workflow today.
- It is not registered in WORKFLOW_REGISTRY and should not be shown as launchable in current user-facing workflow eligibility.
- Use `production_task_created=false unless a future backend workflow is added` when describing MRIQC incubation or validation-only planning.
- Do not add MRIQC artifacts to result summaries without backend output discovery, result contract coverage, and real remote evidence.
- If a user asks for MRIQC now, explain that it can be discussed as external QC/RAG context, but current production result images come from supported workflow outputs and container-native artifacts already registered by Image Agent.
- Raw source snapshots are traceability evidence only. RAG answers should cite this curated summary and backend records, not quote raw HTML wholesale.
- Do not expose patient identifiers, raw image contents, full host paths, credentials, license text, API keys, sudo passwords, or bearer tokens in prompts, RAG answers, logs, or tool outputs.
