---
source_type: rag_vendor
source_url: https://rfmri.org/DPABI, https://rfmri.org/content/dpabidpabisurfdparsf-stand-alone-version, https://rfmri.org/DPABISurfSlurm, https://github.com/Chaogan-Yan/DPABI, https://raw.githubusercontent.com/Chaogan-Yan/DPABI/master/Dockerfile, https://hub.docker.com/v2/repositories/cgyan/dpabi/
raw_source_ids: dpabi_home, dpabi_standalone_docker, dpabisurfslurm_hpc_singularity, dpabi_github_repo, dpabi_dockerfile, dpabi_docker_hub
retrieved_date: 2026-06-08
status: curated_summary
---

# DPABI Official Container Boundary

## Purpose / Scope

Use this source when explaining DPABI/DPARSF as an external neuroimaging ecosystem reference, or when evaluating whether a future incubation proposal has official container evidence.

DPABI is an external ecosystem boundary for Image Agent. It is not a supported Image Agent workflow, not registered in WORKFLOW_REGISTRY, and not a current production task lane. Do not present DPABI as launchable or as a source of Image Agent result-summary artifacts unless a future backend workflow, output discovery, and real remote acceptance evidence are added.

## Container/CLI Usage

Official/maintainer sources provide container evidence for DPABI-family tooling:

- Stand-Alone Docker documentation for DPABI/DPABISurf/DPARSF.
- DPABISurfSlurm documentation for HPC/Singularity usage.
- The `Chaogan-Yan/DPABI` repository and Dockerfile.
- Docker Hub repository metadata for `cgyan/dpabi`.

These sources establish that DPABI has external container distribution evidence. They do not establish an Image Agent backend command contract, validated mounts, supported flags, result-summary schema, or artifact discovery policy.

An incubation proposal must decompose any DPABI container command into explicit runtime primitives before execution:

- input mounts read-only;
- output/work mounts task-scoped;
- no patient-data paths or credentials in model context;
- container image inspection before sandbox execution;
- validation plan with `production_task_created=false`;
- human approval before promotion.

## Important Inputs/Outputs

DPABI-family workflows may involve fMRI preprocessing, surface processing, and related analysis outputs in the external DPABI ecosystem. Image Agent currently has no production DPABI output contract.

For current Image Agent behavior:

- do not register DPABI native artifacts in `/tasks/{task_id}/result-summary`;
- do not add DPABI to container-native QC accepted source ids;
- do not infer that a DPABI Docker image can process the user's dataset through Image Agent;
- treat DPABI as external background unless a future backend workflow adds preflight, launch, output discovery, result-summary, and remote acceptance evidence.

## Image Agent Notes

- DPABI is not a production Image Agent workflow.
- DPABI is not a supported Image Agent workflow for current user task creation.
- Do not add DPABI to container-native QC accepted source ids until backend code and tests define a real DPABI workflow lane.
- If a user asks for DPABI processing, answer with the unsupported workflow boundary and list currently supported workflows instead.
- Use the exact boundary phrase `not a supported Image Agent workflow` in user-facing explanations when needed.
- Raw source snapshots are traceability evidence only. RAG answers should cite this curated summary and backend records, not quote raw HTML, repository pages, Dockerfiles, or registry JSON wholesale.
- Do not expose patient identifiers, raw image contents, full host paths, credentials, license text, API keys, sudo passwords, or bearer tokens in prompts, RAG answers, logs, or tool outputs.
