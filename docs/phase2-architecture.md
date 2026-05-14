# Phase 2 Architecture

Phase 2 adds real Docker-based neuroimaging workflows (DeepPrep, QSIPrep, QSIRecon) behind the existing API, with validation modes for testing. Phase 1 upload/detection/task infrastructure is reused; only the workflow runtime and API surface are extended.

## Workflows

| workflow_type | Input | Pipeline |
|---|---|---|
| `t1_deepprep` | T1 NIfTI (.nii/.nii.gz) | minimal BIDS → `pbfslab/deepprep:25.1.0` anat_only |
| `dwi_qsiprep` | DWI NIfTI + .bval + .bvec | minimal BIDS → `pennlinc/qsiprep:latest` |
| `dwi_qsirecon` | existing QSIPrep output (task_id) | → `pennlinc/qsirecon:latest` |
| `dwi_qsi_full` | DWI NIfTI + .bval + .bvec | QSIPrep → QSIRecon (chained) |

Validation modes (`_validate` suffix, e.g. `t1_deepprep_validate`) only construct the docker command, check image availability via `docker image inspect`, and return the command string. No container is launched.

## Runtime Requirements

- Docker with `sudo -S` (password from env var `IMAGE_AGENT_SUDO_PASSWORD`; never written to disk, code, or logs).
- FreeSurfer license at `/home/yyf/codex/license.txt` (mounted read-only into containers).
- Docker images: `pbfslab/deepprep:25.1.0`, `pennlinc/qsiprep:latest`, `pennlinc/qsirecon:latest`.

## Storage

Phase 1 layout extended:
```
data/projects/{project_id}/
  raw/                          # uploads (unchanged)
  derivatives/{task_id}/
    bids/                       # minimal BIDS symlink farm
    output/                     # container output
    work/                       # container work dir
  logs/{task_id}.log
```

Minimal BIDS is constructed per-task under `derivatives/{task_id}/bids/` using symlinks to raw files. The BIDS tree follows:
```
sub-01/
  anat/
    sub-01_T1w.nii.gz          # for t1_deepprep
  dwi/
    sub-01_dwi.nii.gz          # for dwi_qsiprep
    sub-01_dwi.bval
    sub-01_dwi.bvec
dataset_description.json
```

## Agent Ownership

| Domain | Owner |
|---|---|
| API routes, schemas, DB, storage layout | Backend Agent |
| Imaging detection, workflow runners | Workflow Agent |
| `apps/desktop` UI, API client | Frontend Agent |
| Tests, smoke scripts, contract validation | Review/Test Agent |

Agents must not cross ownership boundaries without explicit cross-agent handoff in docs.

## Configuration

New env vars (not committed):
- `IMAGE_AGENT_SUDO_PASSWORD`: sudo password for docker commands.
- `IMAGE_AGENT_FS_LICENSE`: path to FreeSurfer license (default `/home/yyf/codex/license.txt`).

Backend `config.py` additions:
```python
import os
SUDO_PASSWORD = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD", "")
FS_LICENSE = Path(os.environ.get("IMAGE_AGENT_FS_LICENSE", "/home/yyf/codex/license.txt"))
DOCKER_IMAGES = {
    "deepprep": "pbfslab/deepprep:25.1.0",
    "qsiprep": "pennlinc/qsiprep:latest",
    "qsirecon": "pennlinc/qsirecon:latest",
}
```
