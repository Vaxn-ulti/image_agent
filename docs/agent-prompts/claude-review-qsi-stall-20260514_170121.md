You are the Claude Review/Test agent for image_agent. Work in /home/yyf/project/image_agent.

The controller found a real-data processing risk during acceptance monitoring:
- Real QSIPrep GPU tasks 61 and 62 are still marked running.
- Task 61 log last updated around 2026-05-14 16:57 CST and includes a crash file under data/projects/13/derivatives/61/output/sub-01/log/*/crash-*-synthseg-*.txt.
- Crash shows mri_synthseg --cpu was Killed and missing out_post, likely memory/process pressure.
- Task 62 log appears stale since around 14:46 CST.
- docker ps shows 6 pennlinc/qsiprep containers running, while only current acceptance DWI tasks 61/62 should be active. Do not kill unrelated containers; identify mapping first.
- GPU evidence is valid: logs show eddy_cuda11.0 and "Using CUDA and 1 threads in eddy".

Your task:
1. Inspect DB tasks, task logs, work/output dirs, and Docker containers. Use sudo only if needed; do not print secrets.
2. Determine whether tasks 61/62 are genuinely progressing, stalled, failed but not marked, or blocked by leftover/duplicate containers.
3. Identify each running QSIPrep container command and map it to task/work directory if possible.
4. Produce a concise review report in docs/reviews/claude-review-qsi-stall-${stamp}.md with: current status, root cause evidence, safe next action, and whether a development fix is needed.
5. If it is safe and clearly necessary to stop only containers belonging to failed/stalled task 61/62, recommend exact container IDs but do not stop them yourself.
6. Do not count validation-only as acceptance. Do not modify source code.
