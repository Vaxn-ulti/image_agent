You are the Claude development agent for image_agent. Work in /home/yyf/project/image_agent.

Use the user's proven scripts as references for efficiency tuning, but do not stop current running tasks/containers. Current real DWI rerun task 68 is running; task 67 waits. Do not touch them.

Reference scripts:
- /home/yyf/Project/cn_dwi_qsi_20260512/run_cn_dwi_qsi_to_deepprep_t1_parallel4.sh
- /home/yyf/Project/qsitest_20260507/acpc_to_deepprep_t1_sub002S0413/run_acpc_to_deepprep_t1_sub002S0413.sh
- /home/yyf/Project/cn_dwi_qsi_20260512/pause_cn_dwi_qsi_20260512.sh

Observed proven settings from reference:
- QSIPrep: --gpus all, --network host, TEMPLATEFLOW_HOME=/templateflow, local templateflow mount /home/yyf/Project/qsitest_20260507/templateflow:/templateflow, FS license /home/yyf/codex/license.txt, --output-resolution 2, --nthreads 8, --omp-nthreads 4, --mem 24000, --notrack.
- Reference batch runs parallel 4, but image_agent previously hit memory pressure with multiple QSIPrep containers. For image_agent, preserve serial DWI workflow lock unless you can prove safe concurrency.
- Pause script stops all pennlinc/qsiprep containers; DO NOT copy that behavior. image_agent pause/admin must target only image_agent-labeled containers.
- ACPC->DeepPrep T1 mapping script uses FLIRT 6DOF normmi and applies FA transform to MD/AD/RD. This should be documented as a future DTI metric mapping workflow, not necessarily implemented now unless easy and scoped.

Implement a focused optimization patch:
1. Update DWI defaults in apps/api/app/workflows/pipeline.py to match proven single-task settings where safe: QSIPrep nthreads 8, omp 4, mem 24000; eddy num threads default should follow OMP (4) with floor 2. Keep env overrides.
2. Add configurable TemplateFlow cache mount/env for QSIPrep/QSIRecon/BOLD fMRIPrep if local cache exists. Use env IMAGE_AGENT_TEMPLATEFLOW_HOME defaulting to /home/yyf/Project/qsitest_20260507/templateflow when present. Inside container use /templateflow and set TEMPLATEFLOW_HOME=/templateflow. Do not require the cache if missing.
3. Add tests for new resource defaults and templateflow mount behavior.
4. Update workflow/skill docs with: proven cn_dwi script settings, serial lock rationale, safe pause rule (only labeled containers), and ACPC->DeepPrep T1 FLIRT mapping as DTI metric export/mapping reference.
5. Run apps/api/.venv/bin/pytest -q apps/api/tests.
6. Report changed files. Do not commit.

Do not stop or rerun tasks 67/68. Controller will decide after review.
