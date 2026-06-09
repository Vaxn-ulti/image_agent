# Sensitive Exclusion

## Always Exclude

- Patient names, MRNs, dates of birth, accession numbers, and other identifiers.
- Raw medical images, private image paths, or file listings that reveal patient identity.
- DB files, dumps, credentials, tokens, API keys, cookies, and environment secret values.
- FreeSurfer license contents or other license secrets.
- Full raw logs when they include paths, identifiers, credentials, or environment dumps.
- Screenshots that contain identifiers or private file paths.

## Safe to Include After Review

- Workflow type names.
- Required sidecar field names.
- Sanitized task ids and project ids when already part of product evidence.
- Relative artifact path patterns.
- Command patterns with secrets and private paths removed.
- Error categories and missing requirement messages.

## Redaction Pattern

Replace sensitive details with stable placeholders:

- `<project-root>`
- `<task-id>`
- `<project-id>`
- `<subject-label>`
- `<license-path>`
- `<token-redacted>`

Prefer summarizing sensitive logs over copying them. If redaction would remove the core evidence, block ingestion and ask for a sanitized source.
