---
source_url: https://bids-validator.readthedocs.io/en/latest/user_guide/command-line.html, https://hub.docker.com/r/bids/validator
raw_source_ids: bids_validator_cli, bids_validator_docker
retrieved_date: 2026-06-07
status: curated_summary
---

# BIDS Validator Official CLI/Docker Usage

## Purpose

BIDS Validator checks whether a dataset follows the Brain Imaging Data Structure. It is useful before launching BIDS Apps such as fMRIPrep, DeepPrep, QSIPrep, or XCP-D-compatible flows. Official raw evidence is tracked by source ids `bids_validator_cli` and `bids_validator_docker`.

## Container/CLI Usage

CLI:

```bash
bids-validator <dataset>
bids-validator <dataset> --json
bids-validator <dataset> --format json
bids-validator <dataset> --format json_pp
```

Docker:

```bash
docker run --rm -ti \
  -v /path/to/bids:/data:ro \
  bids/validator /data
```

Official CLI options to preserve in agent answers:

- `--json` is shorthand for `--format json`; use it when the backend needs machine-readable preflight evidence.
- `--format json` and `--format json_pp` emit JSON result formats; text remains the default human display format.
- `--ignoreWarnings` suppresses warning reporting. Agent answers should still say warnings remain reportable unless explicitly ignored.
- `--ignoreNiftiHeaders` skips checks that require opening NIfTI headers, so it is a speed or environment tradeoff, not proof that header-dependent checks passed.
- `--datasetTypes` limits validation to dataset types such as `raw`, `derivative`, or `study`.
- `--recursive` validates datasets found under `derivatives/` subdirectories recursively.
- `-c FILE` / `--config FILE` accepts a JSON configuration file. A project may store this as `.bids-validator-config.json`, but the agent should describe it as an explicit config file path unless runtime code confirms automatic discovery.

## Important Inputs/Outputs

Inputs:

- BIDS root directory.
- `dataset_description.json`.
- Proper subject/session/datatype folders and sidecars.
- Optional validator config JSON such as `.bids-validator-config.json` when passed through `--config`.

Outputs:

- Validation errors and warnings.
- Summary of dataset compliance issues.
- JSON output for preflight parsing when `--json`, `--format json`, or `--format json_pp` is used.
- API-style issue groupings include `issues.errors`, `issues.warnings`, and a dataset `summary`.

## image_agent Notes

- Treat JSON validator output as machine-readable preflight evidence, not as a scientific result.
- Validation errors should block real workflow launch unless the operator explicitly chooses a risk-accepted skip flag.
- Warnings remain reportable unless explicitly ignored with `--ignoreWarnings`; do not silently hide warning-level evidence.
- If `--ignoreNiftiHeaders` was used, say that NIfTI-header-dependent checks were skipped.
- If `--datasetTypes derivative` or `--recursive` was used, distinguish raw BIDS readiness from derivative-dataset checks.
- Config files can reclassify or ignore issues, so report when a `.bids-validator-config.json` or other `--config` file influenced results.
- For BOLD, common issues include missing `TaskName`, missing/invalid `RepetitionTime`, and sidecar mismatches.
- For DWI, common issues include missing `.bval`/`.bvec`.
- For T1, ensure the suffix and datatype folder match BIDS expectations, for example `anat/*_T1w.nii.gz`.
