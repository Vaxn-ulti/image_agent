---
source_type: rag_vendor
source_url: https://surfer.nmr.mgh.harvard.edu/registration.html
raw_source_ids: freesurfer_license_registration
retrieved_date: 2026-06-07
status: curated_summary
---

# FreeSurfer Official License Boundary

## Purpose

FreeSurfer registration is the official route for obtaining a `license.txt` key file. The license file is a runtime configuration requirement for FreeSurfer-dependent workflows such as recon-all, fMRIPrep with FreeSurfer enabled, DeepPrep anatomical processing, QSIPrep, and QSIRecon. Official raw evidence is tracked by source id `freesurfer_license_registration`.

## Container/CLI Usage

FreeSurfer and downstream BIDS Apps commonly look for a license key file through one of these runtime paths:

```bash
export FS_LICENSE=/path/to/license.txt
```

```bash
fmriprep /data /out participant --fs-license-file /opt/freesurfer/license.txt
```

```bash
deepprep-docker /data /out participant --fs_license_file /fs_license.txt
```

Container mount examples:

```bash
-v /host/license.txt:/opt/freesurfer/license.txt:ro
-v /host/license.txt:/fs_license.txt:ro
```

Official fMRIPrep usage also documents `$FREESURFER_HOME/license.txt` as the default FreeSurfer search path after `FS_LICENSE` in manually prepared environments. In this repo, prefer an explicit read-only support mount such as `/opt/freesurfer/license.txt:ro` plus `--fs-license-file /opt/freesurfer/license.txt` or the workflow-specific equivalent.

## Important Inputs/Outputs

Inputs:

- A valid FreeSurfer `license.txt` key file obtained through FreeSurfer registration.
- A configured host path, normally `IMAGE_AGENT_FS_LICENSE` or the backend `FS_LICENSE` setting.
- A read-only support mount into the container when the workflow requires FreeSurfer tools.

Outputs:

- The license file is not a workflow output and must never be copied into result summaries, RAG chunks, task logs, screenshots, or report artifacts.
- A missing, unreadable, or unmounted license is a configuration blocker, not data pathology and not a subject-level imaging finding.

## image_agent Notes

- Treat FreeSurfer license failures as runtime configuration blockers. Say the workflow needs a valid FreeSurfer license path and a readable read-only container mount.
- Do not expose license file contents, registration personal information, e-mail addresses, full sensitive host paths, or copied license text.
- For fMRIPrep/QSI style commands, use `--fs-license-file` with the in-container path.
- For DeepPrep style commands, use `--fs_license_file` with the in-container path.
- A read-only support mount outside `PROJECTS_ROOT` is allowed only with at least one project-scoped mount, and it must remain read-only.
- Do not retry long container workflows until the license preflight confirms that the configured file exists and is mounted at the path used by the command.
