---
source_url: https://www.templateflow.org/python-client/master/installation.html, https://github.com/templateflow/templateflow
raw_source_ids: templateflow_installation, templateflow_archive
retrieved_date: 2026-06-06
status: curated_summary
---

# TemplateFlow Official Cache/Archive Client

## Purpose / 目的

TemplateFlow provides standardized neuroimaging templates used by tools such as fMRIPrep and XCP-D. Its Python client lazily downloads template resources and serves them from a local cache.

## Container/CLI Usage

Python client pattern:

```python
from templateflow import api as tflow

path = tflow.get(
    "MNI152NLin6Asym",
    desc=None,
    resolution=1,
    suffix="T1w",
    extension="nii.gz",
)
```

Cache configuration:

```bash
export TEMPLATEFLOW_HOME=/path/to/templateflow
```

For offline/HPC environments, prefetch templates on a node with internet access, then mount the cache into containers.

## Important Inputs/Outputs

Inputs:

- Template identifiers such as `MNI152NLin6Asym`.
- Query entities such as resolution, suffix, cohort, desc, extension.
- Writable local cache directory.

Outputs:

- Local template files returned as paths.
- Cached archive contents for reuse without repeated downloads.

## image_agent Notes

- TemplateFlow failures usually mean cache/network/mount problems, not scan pathology.
- When fMRIPrep or XCP-D reports missing templates, check `TEMPLATEFLOW_HOME` and container binds.
- If a compute node has no internet, recommend prefetching and mounting the cache.
