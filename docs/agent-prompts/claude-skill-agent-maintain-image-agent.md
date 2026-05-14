You are the Skill agent for /home/yyf/project/image_agent. The user requires all non-built-in project agents to be Claude-driven now.

Scope: update skill/docs only, unless a typo in docs path blocks validation. Do not modify backend/frontend business code.

Current orchestration model:
- Total-control agent: coordinates work, monitors tasks, assigns Claude development and Claude review/test agents, and only escalates to user for external blockers.
- Frontend/backend development agent: Claude, edits app code/tests only.
- Review/Test agent: Claude, reviews product and runs safe tests/validations.
- Skill agent: Claude, maintains skills and references following skill-creator principles.
- Built-in software chat agent: DeepSeek remains inside the app.

Current technical state:
- QSIPrep: must use Docker --gpus all plus eddy_cuda_config.json with use_cuda=true and --eddy-config /eddy_cuda_config.json. The image must expose eddy_cuda or DWI runs fail fast. Current pennlinc/qsiprep:latest lacks eddy_cuda.
- QSIRecon: docs show no CUDA-specific CLI switch; use Docker --gpus all and validate GPU device visibility inside container.
- Review/Test found dwi_qsi_full may bypass GPU safety checks; dev agent is fixing.

Tasks:
1. Inspect docs/skills and docs/workflows.
2. Ensure the skills clearly state Claude is used for development/review/test/skill agents, while DeepSeek is only the app built-in agent.
3. Ensure QSIPrep, QSIRecon, dwi_qsi_full GPU rules and failure/update workflow are documented.
4. Keep SKILL.md concise; put detail in references.
5. Run a lightweight markdown/frontmatter check.
6. Final report changed files and remaining blockers.

Do not revert other agents changes.

TOTAL-CONTROL UPDATE: User acceptance requires complete real-data processing, not validate-only. Skills/workflow docs must define real acceptance evidence: upload packages, real T1/BOLD/DWI/QSIRecon outputs, GPU usage where supported, mixed-sample matrix, unsupported sequence handling, and failure-to-skill-update process.
