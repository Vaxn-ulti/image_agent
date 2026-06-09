---
source_url: https://docs.sylabs.io/guides/latest/user-guide/cli/singularity_inspect.html, https://apptainer.org/docs/user/latest/cli/apptainer_inspect.html
raw_source_ids: singularityce_inspect, apptainer_inspect
retrieved_date: 2026-06-06
status: curated_summary
---

# SingularityCE and Apptainer Official Inspect

## Purpose / Mudi

Use this source for backend-only metadata inspection of SIF images in HPC or rootless runtime environments.

## Container/CLI Usage

SingularityCE pattern:

```bash
singularity inspect [inspect options...] <image path>
singularity inspect --json <image path>
```

Apptainer pattern:

```bash
apptainer inspect [inspect options...] <image path>
apptainer inspect --json <image path>
```

Both inspect commands show image metadata such as labels, environment variables, apps, and scripts; JSON output is available through `--json`.

## Important Inputs/Outputs

Input:

- a SIF image path or runtime-supported image reference.

Useful output fields for Image Agent:

- labels and image metadata;
- environment variable keys;
- application list and script metadata when present;
- definition/bootstrap hints when exposed by the image.

## Image Agent Notes

- Use SingularityCE or Apptainer inspection for SIF/HPC workflows, not Docker-specific assumptions.
- Inspection may expose image environment scripts; summarize keys and runtime hints but do not copy secret values.
- Treat `singularity inspect --json` and `apptainer inspect --json` as metadata evidence for incubation validation.
- Inspection does not replace sandbox execution, native QC artifact discovery, or human approval.
