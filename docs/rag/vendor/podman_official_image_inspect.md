---
source_url: https://docs.podman.io/en/latest/markdown/podman-image-inspect.1.html
raw_source_ids: podman_image_inspect
retrieved_date: 2026-06-06
status: curated_summary
---

# Podman Official Image Inspect

## Purpose / Mudi

Use this source for backend-only Podman image metadata inspection in environments where Podman replaces Docker.

## Container/CLI Usage

Official command pattern:

```bash
podman image inspect [options] image [image ...]
```

Useful option:

```bash
podman image inspect --format '{{ .Id }}' <image>
```

By default, Podman image inspect returns low-level image information in a JSON array. The `--format` flag can use returned JSON keys.

## Important Inputs/Outputs

Input:

- a Podman-accessible image name or id.

Useful output fields for Image Agent:

- id, digest, names, labels, annotations, architecture, OS, history;
- config command, entrypoint, exposed ports, environment keys, user, and working directory.

## Image Agent Notes

- Prefer Podman inspection only when the backend runtime is configured for Podman or Docker is unavailable.
- Treat output as metadata evidence; still require sandbox validation runs and output discovery before promotion.
- Redact secret-like values and do not pass model-generated shell strings directly to the runtime.
- Normalize Podman output into the same `container_inspection` shape used for Docker.
