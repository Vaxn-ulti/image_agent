You are the Claude Skill/Workflow agent for image_agent. Work in /home/yyf/project/image_agent.

Update the skill and workflow docs for the latest operational lessons:
- API port 8000 can be taken by unrelated uvicorn services; image_agent watcher will return 404 from /tasks/{id} when this happens.
- Correct recovery: identify the port owner, stop only the conflicting non-image_agent process when image_agent must own 8000, restart image_agent API from /home/yyf/project/image_agent with .env, verify /health and /tasks/{active_id}.
- Real QSIPrep task 65 may continue in Docker during API restarts; do not assume API restart means container stopped. Inspect Docker mounts and task logs.
- Preserve DWI lock and reduced resource policy from faf5930.
- Acceptance is real processing outputs, not validation.
- Never stop unrelated containers or push patient data/logs/DB/images to GitHub.

Update relevant docs under docs/skills and docs/workflows. Keep SKILL.md concise and put details in references. Report changed files.
