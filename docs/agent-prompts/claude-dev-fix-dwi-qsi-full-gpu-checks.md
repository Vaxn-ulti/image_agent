You are the frontend-backend development agent for /home/yyf/project/image_agent.

A Claude Review/Test agent found a real bug: dwi_qsi_full and dwi_qsi_full_validate bypass GPU safety checks because run_pipeline_task only checks workflow == dwi_qsiprep and workflow == dwi_qsirecon. The dwi_qsi_full command chain includes QSIPrep and QSIRecon, so it must enforce both policies:

- Before real dwi_qsi_full execution and dwi_qsi_full_validate completion, verify the selected QSIPrep image exposes eddy_cuda. If missing, fail fast with an eddy_cuda-specific message. Do not allow dwi_qsi_full to run CPU eddy.
- dwi_qsi_full should still generate/use eddy_cuda_config.json via its internal dwi_qsiprep command.
- For dwi_qsi_full_validate, also record QSIRecon GPU visibility if possible, because the second step is QSIRecon with --gpus all.
- Keep dwi_qsirecon standalone behavior: no CUDA-specific CLI requirement, only GPU visibility record.

Tasks:
1. Patch apps/api/app/workflows/pipeline.py.
2. Add/adjust tests in apps/api/tests/test_api_flow.py for dwi_qsi_full_validate failing fast when eddy_cuda is absent and/or recording QSIRecon GPU visibility when present.
3. Run apps/api pytest -q and apps/desktop npm run build.
4. Do not run real long imaging workflows.
5. Final report changed files, test results, and any remaining blockers.

Do not revert other agents changes.

TOTAL-CONTROL UPDATE: User acceptance requires real-data processing, not validate-only. Your fix must protect real dwi_qsi_full execution from CPU eddy fallback. DWI real processing must not proceed until CUDA-enabled QSIPrep/FSL image with eddy_cuda is available. Keep tests focused; do not start long real processing.
