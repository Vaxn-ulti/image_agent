---
source_url: https://docs.docker.com/reference/cli/docker/image/inspect/
raw_source_ids: docker_image_inspect
retrieved_date: 2026-06-06
status: curated_summary
---

# Docker Official Image Inspect

## Purpose / Mudi

Use this source for backend-only Docker image metadata inspection during workflow incubation and promotion validation.

## Container/CLI Usage

Official command pattern:

```bash
docker image inspect [OPTIONS] IMAGE [IMAGE...]
```

Useful option:

```bash
docker image inspect --format json <image>
```

The command displays detailed information for one or more images. It can return JSON or Go-template-formatted output.

## Important Inputs/Outputs

Input:

- a local Docker image name, tag, digest, or image id.

Useful output fields for Image Agent:

- image id and repo digests;
- architecture and OS;
- config entrypoint and command;
- config environment keys;
- labels, working directory, exposed ports, user, and volumes.

## Image Agent Notes

- The LLM must not execute Docker directly. It requests inspection through backend local/runtime tools.
- Redact secret-like environment values and never surface tokens, license content, or private host paths.
- Use inspection evidence for `container_image_inspected`, `container_digest_recorded`, `container_entrypoint_recorded`, and related validation checks.
- `docker image inspect` is metadata inspection, not a proof that the workflow runs or that outputs are valid.
