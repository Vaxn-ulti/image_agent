# Agent Roles

Use these boundaries when multiple agents work on `/home/yyf/project/image_agent`.

## Model Assignments

- **Orchestrator (total-control)**: Claude coordinates, monitors, assigns work, and escalates only external blockers to the user.
- **Frontend/Backend Developer**: Claude edits app code and tests only.
- **Review/Test**: Claude reviews product and runs safe tests/validations.
- **Skill**: Claude maintains skills and references following skill-creator principles.
- **Built-in chat (app)**: OpenAI SDK chat gateway via `ModelGateway` and Responses-native requests for freeform answers; deterministic backend rules still handle status/series questions, and DeepSeek legacy fallback is compatibility-only when the OpenAI gateway is unavailable. Not used for development, review, testing, or skill maintenance.

## Orchestrator Agent

- Own task decomposition, sequencing, and acceptance gates.
- Decide which Claude agent gets backend/frontend implementation, review/testing, runner validation, or skill updates.
- Track blocked infrastructure separately from code defects.
- Stop or fail long-running tasks that are known to be using the wrong runtime, then hand the concrete failure back to developer or skill agents.
- Do not make broad code changes while delegating the same surface to another agent.

## Frontend/Backend Developer Agent (Claude)

- Own product code changes in `apps/api`, `apps/desktop`, and related workflow docs.
- Keep backend contracts deterministic before adjusting desktop UI or OpenAI SDK chat gateway wording.
- For DWI, implement QSIPrep CUDA config generation and command wiring; do not hide missing container capabilities behind retries.
- For QSIRecon, preserve dependency on completed QSIPrep output and use Docker GPU exposure rather than inventing unsupported CLI flags.
- Hand off with files changed, commands run, known risks, and exact next validation target.

## Review/Test Agent (Claude)

- Own independent verification, regression tests, and risk review.
- Start from repository state and documented contracts, not from developer intent.
- Verify the focused matrix in `testing-matrix.md`; add targeted tests when behavior changed.
- Treat a fast validation failure that proves an unavailable CUDA binary as an infrastructure block, not as a failed test implementation.
- Report findings with file/line references, commands run, and residual risk.

## Skill Agent (Claude)

- Own updates to `docs/skills/**` and skill references only.
- Keep `SKILL.md` concise; move detailed strategy, failure points, and acceptance flow into `references/`.
- Update skills after real failures reveal missing guidance, stale assumptions, or unclear agent boundaries.
- Do not change business code while acting as skill agent.
