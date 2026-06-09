# Product Context

## Scope

Image Agent is a remote-compute MVP with a React/Vite desktop UI and FastAPI backend. The backend owns storage, ingest, BIDS-like construction, workflow validation/execution, task status, logs, outputs, and OpenAI SDK chat gateway grounding.

## Data Path

Uploads land under:

`data/projects/{project_id}/raw`

Workflow derivatives land under:

`data/projects/{project_id}/derivatives/{task_id}`

Logs land under:

`data/projects/{project_id}/logs/{task_id}.log`

## Supported Ingest

The MVP supports mixed uploads:

- DICOM archives or folders.
- NIfTI files.
- Sidecar JSON.
- DWI gradient files `.bval` and `.bvec`.

Ingest should produce deterministic inventory and BIDS-like placement. It should not silently overwrite BIDS artifacts; use `run-*` and/or `acq-*` entities when collisions occur.

Metadata precedence:

1. Sidecar JSON.
2. DICOM tags.
3. NIfTI header.
4. Filename tokens.

## Supported Workflows

MVP workflow family:

- `t1_deepprep`: DeepPrep T1w preprocessing.
- `bold_deepprep`: DeepPrep fMRI/BOLD preprocessing.
- `bold_second_level`: single-subject downstream BOLD metrics after DeepPrep, including ALFF, fALFF, ReHo, DMN, and seed-to-ROI outputs.
- `dwi_fast_gpu_dti`: production DWI path using the fast GPU DTI workflow.

Legacy or experimental workflow family:

- `dwi_qsiprep`: QSIPrep DWI preprocessing.
- `dwi_qsirecon`: QSIRecon reconstruction from completed QSIPrep output.
- `dwi_qsi_full`: chained QSIPrep then QSIRecon.

Each workflow may have a validate-only variant that resolves Docker image availability, bind mounts, and command string without launching the container.

## DWI Runtime Position

`dwi_fast_gpu_dti` is the production DWI path and is based on the fast GPU DTI workflow. It requires DWI NIfTI, `.bval`, `.bvec`, and a JSON sidecar with `PhaseEncodingDirection` and `TotalReadoutTime`. Expected outputs include FA, MD, AD, RD, MNI152-space maps, and atlas regional DTI tables.

Production fast DTI is intentionally lightweight:

- use host FSL from `/home/yyf/project/MCI_project/tools/fsl` for GPU `eddy_cuda` and FSL registration utilities;
- use `pennlinc/qsiprep:latest` only as an MRtrix toolbox image;
- do not run full QSIPrep or full QSIRecon;
- target DTI metric generation within 35 minutes / `2100` seconds;
- if a real run exceeds that target, report the exact bottleneck from task logs rather than recommending the legacy full QSI path.

Current real-run evidence: task `107` completed on project 22 / series 38 in about 19 minutes 52 seconds (`runtime_sec=1156` in QC), task `112` completed on project 23 / series 39 in about 18 minutes 2 seconds (`runtime_sec=1042` in QC), and mixed-project task `114` completed on project 13 / series 24 with `runtime_sec=1021`. These runs produced real native and MNI152 FA/MD/AD/RD maps, HarvardOxford regional DTI tables, and `validation_only=false` result summaries. Delivered metric maps are sanitized to remove sparse NaN/inf values and the replacement counts are recorded in provenance.

Legacy BIDS-ingested DWI records can be eligible when real `.json`, `.bval`, and `.bvec` sidecars are listed in metadata or BIDS placement, even if newer upload metadata fields are absent. Ordinary DWI uploads without JSON remain ineligible for fast GPU DTI.

Legacy DWI QSIPrep tasks `46` and `47` used `eddy_cpu`, ran too long, were stopped, and are marked `failed`. Do not tell users to retry that CPU path as the product recommendation.

Legacy/experimental QSIPrep remains CUDA-oriented:

- Backend generates `eddy_cuda_config.json`.
- Command mounts it at `/eddy_cuda_config.json`.
- Command passes `--eddy-config /eddy_cuda_config.json`.
- Config contains `use_cuda: true`, `num_threads >= 4`, `dont_peas: true`, `cnr_maps: true`, default `niter: 3`, and an auto-inferred `is_shelled` value from b-values.

`pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`. Detection uses `eddy_cuda*` glob to accept versioned binaries for legacy QSIPrep validation. Production fast DTI probes host FSL GPU `eddy_cuda` instead.

For legacy QSIRecon, current docs do not confirm a CUDA-only CLI flag. The product uses `docker run --gpus all` and records whether GPU is visible inside the container. QSIRecon requires `--recon-spec` to select the reconstruction pipeline.

## Grounding Precedence

Backend DB records, task state, logs, and output records outrank retrieved documentation or RAG snippets. If retrieved docs disagree with current task/output records, report the backend state and mention that docs may be stale only when useful.

Built-in agent orchestration now exposes a grounded RAG response with `intent`, `recommended_next_step`, `tool_chain_hint`, `tool_invocations`, and `rag_mode` (`langgraph` when available, otherwise fallback). The `tool_invocations` field is a read-only tool-chain trace: it may inspect backend task status, registered outputs, scientific report summaries, and a safe next-action recommendation, but it must not launch long workflows from chat. It must still treat deterministic workflow eligibility, task state, logs, `/tasks/{id}/result-summary`, `/result-contract`, and registered outputs as higher priority than retrieved text.

The legacy `/chat` route now prefers the OpenAI SDK chat gateway through `ModelGateway` and the Responses-native `responses.create` boundary for freeform answers. DeepSeek legacy fallback exists only for compatibility when the OpenAI gateway is unavailable; deterministic rules still handle series/status/task responses before model text.

Frontend-ready result summaries expose artifact `download_url`, `relative_path`, `content_type`, and `size_bytes`. Use `/tasks/{task_id}/artifacts/{relative_path}` to retrieve task output files rather than exposing local absolute paths to users. NIfTI gzip downloads (`.nii.gz`) should come back as `application/gzip`.

Scientific report display artifacts are registered under `outputs.reports`. When present, direct users to the `Scientific report` panel or `reports/index.html` for readable charts and tables, while keeping raw maps and TSVs as the source data. Current report-builder figures are PNG assets and should be described as derived presentation artifacts when `artifact_role=derived_presentation_asset` or `native_artifact=false`; they do not replace missing container-native QC. NIfTI maps remain download/source artifacts unless a dedicated image viewer is implemented.

The read-only Agent tool endpoint `POST /agent/tools/verify-scientific-reports` can verify real report-layer artifacts by task id. Use it to check task `41`, `111`, and `114` after deployment, or the current task ids selected by backend records.

## fMRI/BOLD Position

fMRI/BOLD must be treated as supported for DeepPrep preprocessing when BOLD input is present and passes backend eligibility checks. `bold_second_level` is single-subject downstream metrics after DeepPrep and may produce ALFF, fALFF, ReHo, tSNR/RSFA, DMN, 15-seed seed-to-ROI, and seed time-series outputs in MNI152 space; only describe outputs that backend records show as completed. Group-level BOLD analysis is separate from this workflow.

Current real-run evidence: task `110` on project 14 / series 25 and task `111` on project 13 / series 23 completed `bold_second_level` from completed DeepPrep BOLD outputs. Both returned unified BOLD result summaries from `/tasks/{id}/result-summary`, MNI152 maps with shape `91 x 109 x 91`, 15-seed seed-to-ROI TSVs, and DMN summaries.

Historical reports from `D:\Project\image_agent\bold_descriptive_review_20260521` are descriptive review examples. They can guide report layout and output conventions such as MNI152NLin6Asym res-02 maps, PCC seed-FC, Schaefer 200 / 7-network heatmaps, and motion QC overlays, but they should not be described as second-level inference.

## T1 Result Position

T1 result summaries parse real DeepPrep/Freesurfer stats when available. Real parsed summaries use `extraction_status=real_deepprep_freesurfer_stats`, write brain-measure and cortical-region TSVs, and register actual T1w maps/transforms. Placeholder T1 summaries remain possible only when real stats are missing, and must be described as placeholders.

## Unsupported Sequences

When a recognized sequence is not supported for processing, surface this exact sentence:

`Current software does not support radiomics/processing for this sequence.`

Do not invent workaround workflows. Suggest upload correction or later feature support only when grounded in product state.
