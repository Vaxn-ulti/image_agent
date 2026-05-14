You are the Claude Review/Test agent for final real acceptance of /home/yyf/project/image_agent.

User clarified acceptance: validate is NOT enough. Final acceptance requires complete real-data tests:
- Upload different real data packages.
- User can request processing from GUI/API.
- Software completes real container processing and produces outputs.
- Use GPU mode whenever containers/tools support it, for speed.
- Skills and workflow orchestration docs must be complete.

Current blocker:
- DWI real processing is blocked because current pennlinc/qsiprep:latest lacks eddy_cuda. QSIPrep must run with --gpus all, --eddy-config /eddy_cuda_config.json, use_cuda=true, and image must expose eddy_cuda. Do not accept CPU eddy.
- QSIRecon has no documented CUDA-specific CLI switch; expected behavior is docker run --gpus all and GPU visibility recorded.

Your tasks:
1. Inspect current DB and data/projects to identify real sample series for T1, BOLD, DWI, DICOM/mixed packages, unsupported sequences.
2. Draft and, where safe, implement scripts for final real acceptance matrix, but do not start long real DWI until a CUDA-enabled QSIPrep image is available.
3. Include real tests for: T1 DeepPrep, BOLD DeepPrep, DWI QSIPrep with eddy_cuda, QSIRecon after QSIPrep, mixed upload/package inventory, unsupported sequence blocking, multiple sample combinations.
4. Verify current code/tests and identify exact blockers preventing real acceptance.
5. Produce a report with: Acceptance Matrix, Available Real Samples, Blocking Items, Ready-to-run Commands/Scripts, and Required Evidence for Pass.

Do not run fake-only validation as acceptance. Do not kill unrelated containers. Do not revert other agents changes.
