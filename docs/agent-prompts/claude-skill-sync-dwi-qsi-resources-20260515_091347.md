# Claude Skill Agent: update Image Agent skills for DWI/QSI resource profile

You are the skill-maintenance agent for /home/yyf/project/image_agent.

Controller update:
- User-approved resource profile is now QSIPrep `--nthreads 8 --omp-nthreads 4 --mem 24000` and QSIRecon `--nprocs 8 --omp-nthreads 4 --mem 24000`.
- Commit `6162be9 Use user-approved DWI QSI resource defaults` updated backend defaults and skill references.
- Real acceptance remains: complete real T1/BOLD/DWI/QSIRecon processing, not validation-only.
- Current DWI run: task 78 running, task 77 waiting on lock, watcher script will submit QSIRecon.

Your job:
1. Review the skills under docs/skills for stale statements about old DWI/QSI resource defaults, reduced resources, or validate-only acceptance.
2. Keep skill-creator style: concise SKILL.md plus focused references/evals, no broad noisy rewrite.
3. If a stale skill reference remains, patch it and report files changed.
4. Do not touch patient data, logs, DB files, or running tasks.
