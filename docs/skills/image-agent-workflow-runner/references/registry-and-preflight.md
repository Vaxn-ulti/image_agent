# Registry and Preflight

## Registry Fields

Each workflow registry entry should declare:

- `workflow_type`;
- display name and modality;
- production, validation, legacy, or experimental status;
- required input files and required metadata fields;
- dependency workflow/task requirements;
- runner implementation;
- expected output families;
- validation-only variant name;
- estimated runtime or timeout;
- security/mount requirements;
- compatibility aliases for historical tasks.

## Required Inputs

- `t1_deepprep`: T1w NIfTI/BIDS-like anat placement and required FreeSurfer license if the runner needs it.
- `bold_deepprep`: BOLD NIfTI/BIDS-like func placement and required DeepPrep support mounts.
- `bold_second_level`: completed BOLD DeepPrep outputs for the same subject/series, MNI BOLD data, and a matching MNI/EPI mask or documented mask-generation path.
- `dwi_fast_gpu_dti`: DWI NIfTI, `.bval`, `.bvec`, JSON sidecar, `PhaseEncodingDirection`, and `TotalReadoutTime`.
- `dwi_qsiprep`: DWI NIfTI, `.bval`, `.bvec`, and CUDA-capable QSIPrep configuration.
- `dwi_qsirecon`: completed QSIPrep output and valid `--recon-spec`.
- `bold_fmriprep_xcpd`: BOLD BIDS/NIfTI-BIDS or completed preprocessing derivatives for fMRIPrep, followed by a DeepPrep-derived fMRIPrep-compatible input for XCP-D; XCP-D must receive derivatives, not raw BIDS.

## Preflight Checks

Preflight should resolve:

1. Backend series/task identity.
2. Absolute paths for input, output, work, and read-only support mounts.
3. Required sidecars and metadata.
4. Docker image or host tool availability.
5. GPU/capability probes when relevant.
6. Command tokens and bind mounts.
7. Output directory writeability.
8. Whether this is validate-only or real execution.

For the BOLD fMRIPrep/XCP-D remote wrapper, preflight should expose `IMAGE_AGENT_TASK_XCPD_DIR` and `IMAGE_AGENT_TASK_TEMPLATEFLOW_DIR` to the scripts. TemplateFlow cache is a support mount; it must be scoped separately from raw input data and separately from XCP-D derivatives. Preflight must check that the shared TemplateFlow cache is writable and that the fixed prewarmed template files for `MNI152NLin2009cAsym`, `MNI152NLin6Asym`, and `OASIS30ANTs` are present and non-empty before human confirmation for a full production run. The two MNI templates require res-01/res-02 T1w and brain-mask files; `MNI152NLin2009cAsym` additionally requires the fMRIPrep BOLD-reference, brain-probseg, and carpet-dseg files used by BOLD reference skull-stripping and carpet-plot generation. XCP-D QC and atlas resampling require TemplateFlow H5 transforms in both directions between `MNI152NLin6Asym` and `MNI152NLin2009cAsym`. `OASIS30ANTs` is limited to the official res-01 T1w, brain T1w, and brain-mask files used by fMRIPrep brain extraction. script paths must be regular files, not directories. public preflight check summaries use path-safe labels, raised wrapper errors should use path-safe script labels, and script stdout/stderr must be redacted before task logs or RAG-facing summaries mention it. The runtime wrapper uses `IMAGE_AGENT_REMOTE_SCRIPT_TIMEOUT_SEC` for each script and translates `TimeoutExpired` into a remote-script-timed-out event with a redacted log tail.

The same BOLD fMRIPrep/XCP-D production path also requires a supported same-project T1/anat companion series. Missing T1/anat data is a launch blocker and must be reported before `task_service.create_series_task()` creates a production task.

Report exact blockers. Do not substitute a different workflow just because preflight fails.

## Data Candidate Selection

Before sandbox validation or workflow confirmation, the agent should call backend function tools such as `list_data_candidates` or `select_incubation_dataset` when the user has not specified an exact series. These tools are allowed to inspect backend DB rows and safe file-existence signals; they are not allowed to expose raw image contents, full sensitive paths, patient identifiers, or secrets.

Candidate ranking should prefer supported series with matching modality, BIDS-ready layout, complete required sidecars, existing storage, and project-root scoped paths. For BOLD fMRIPrep/XCP-D incubation, prefer BOLD BIDS/NIfTI-BIDS candidates; for T1 DeepPrep incubation, prefer T1 candidates; for DWI incubation, require JSON, bval, and bvec sidecars before ranking a candidate as ready.

Selecting an incubation dataset is not production execution. It must return `production_task_created: false`, and a later production task still requires preflight and explicit user confirmation.

Official BIDS boundary summary:

- `docs/rag/vendor/bids_official_mri_derivatives.md` documents MRI sidecar expectations, DWI `.bval`/`.bvec`/JSON readiness, and the raw-BIDS versus derivative-dataset boundary.
- `docs/rag/vendor/bids_validator_official_cli_docker.md` documents BIDS Validator CLI/Docker preflight. Prefer `bids-validator <dataset> --json` or `--format json` / `--format json_pp` when backend code needs machine-readable preflight evidence.

When reporting validator results:

- `--ignoreWarnings` means warnings remain reportable unless explicitly ignored; do not present warning-suppressed output as a clean full validation.
- `--ignoreNiftiHeaders` means header-dependent NIfTI checks were skipped.
- `--datasetTypes` narrows the accepted dataset type, for example raw, derivative, or study.
- `--recursive` includes datasets under `derivatives/` recursively, so distinguish raw BIDS readiness from derivative checks.

## Validate-Only Boundary

Validate-only may create command metadata, validation reports, and capability probe outputs. It must not create real-looking metric maps, tables, or summaries unless provenance clearly marks placeholder validation output.
