You are the Claude development agent for image_agent. Work in /home/yyf/project/image_agent.

Fix the QSIPrep eddy CUDA config causing real DWI task 65 to hang. Do not stop containers; controller will stop/rerun after patch review.

Current evidence:
- task 65 DWI is only ~87MB / 129 bvals, but eddy_cuda10.2 has run >3.5h at 100% CPU with only small eddy files and no workdir updates since 19:35 CST.
- Review/test agent concluded the root cause is eddy_cuda_config.json using num_threads: 1 in _write_qsiprep_eddy_cuda_config(), starving eddy GP estimation.
- Need use GPU where supported, but not single-thread eddy.

Required patch:
1. In apps/api/app/workflows/pipeline.py, change _write_qsiprep_eddy_cuda_config() so eddy uses a practical thread count tied to DWI_QSIPREP_OMP_NTHREADS or a new env var, not hard-coded 1. Default should be >1 and compatible with existing QSIPrep --omp-nthreads 2 / --nthreads 4 resource limits unless you justify changing those defaults.
2. Add conservative speed/stability adjustments to eddy config only if scientifically acceptable for MVP real validation. Preserve correction quality where possible. Do not blindly disable important correction unless documented.
3. Add tests proving the eddy config uses CUDA and thread count >1/default env behavior.
4. Update workflow/skill docs with this failure mode and the new eddy threading rule.
5. Run apps/api/.venv/bin/pytest -q apps/api/tests.
6. Report changed files.

Do not commit and do not touch running containers/tasks.
