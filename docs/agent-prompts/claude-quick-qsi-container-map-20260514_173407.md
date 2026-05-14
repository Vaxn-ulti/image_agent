You are a short-run Claude Review/Test agent. Work in /home/yyf/project/image_agent.

Objective: produce a quick, actionable container-task map for stalled real QSIPrep tasks. Do not modify files except the requested report. Do not stop containers.

Facts to verify:
- DB tasks 61 and 62 are dwi_qsiprep running at progress=20.
- Docker has six pennlinc/qsiprep containers. Four appear old/other subject containers with participant labels 067S*. Two appear current tasks with participant-label 01 and eddy_cuda symlink command.
- Task 61 has a SynthSeg crash: mri_synthseg --cpu Killed.
- Task 62 log may be stale.

Commands you may run:
- sqlite3 or python sqlite reads of data/app.db
- sudo docker ps --no-trunc and docker inspect for container mounts
- tail/stat of data/projects/13/logs/61.log and data/projects/15/logs/62.log
- ps/nvidia-smi/free/df

Write report to docs/reviews/claude-quick-qsi-container-map-${stamp}.md with exactly these sections:
1. Task status
2. Container map
3. Stalled/failing evidence
4. Safe action recommendation
5. Development fix needed

Keep it concise. Finish within 10 minutes.
