# Conflicts and Script Extraction

## Conflict Handling

When sources disagree, record:

- the conflicting claims;
- source ids and dates/versions;
- which source has higher priority;
- the accepted product fact;
- whether the lower-priority source should be deprecated, revised, or kept as historical context.

Do not average conflicting claims. For example, if old docs say DWI production runs full QSIPrep but current backend scripts run fast GPU DTI, curate the current fast DTI behavior and mark the old QSIPrep claim as legacy or stale.

## Script Extraction Checklist

From scripts or code, extract:

- workflow name and modality;
- required inputs and sidecars;
- command or tool sequence;
- Docker images and host tools;
- environment variables;
- mounts and path assumptions;
- output files and summaries;
- runtime limits;
- validation-only behavior;
- failure conditions.

Do not extract:

- secrets;
- license text;
- patient identifiers;
- raw absolute paths that would expose private data;
- temporary debug dumps;
- credentials or tokens.

## Snippet Shape

Curated snippets should be short and declarative:

- Product fact.
- Evidence source.
- Applicability or boundary.
- Conflict note when needed.

Avoid long pasted code. Link to source metadata instead.
