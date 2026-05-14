You are the Claude development agent for image_agent. Work in /home/yyf/project/image_agent.

Context:
- User wants total-control progress to real acceptance: real upload/process outputs, not validate-only.
- Built-in app agent remains DeepSeek. Development/review/skill agents use Claude.
- Stack direction: Streamlit + FastAPI + LiteLLM + WebSocket + Python + Docker.
- A port conflict occurred: /home/yyf/Project/gpt_agent_project uvicorn took port 8000, so scripts_watch_qsirecon_65_66.sh got 404 from /tasks/65 and /tasks/66. Controller restored image_agent API on 8000.
- Real task 65 is a QSIPrep Docker run still active; task 66 is waiting on dwi_qsiprep.lock. Because API was restarted, task 65 may be an orphaned Docker process whose original Python run_pipeline_task thread is gone. We need robust recovery and future-proofing.
- Existing backend patch faf5930 added reduced DWI resources and dwi_qsiprep lock. Tests passed 22.

Tasks:
1. Inspect current code and runtime state. Do not stop running task 65 unless clearly failed and report evidence first.
2. Implement minimal code/scripts to make image_agent API service ownership safer and recover orphaned real Docker tasks after API restarts. Prefer a small admin/recovery script if a full worker system is too large.
3. The recovery must avoid patient data in git and must never stop unrelated containers outside /home/yyf/project/image_agent.
4. Ensure watcher scripts use the intended API and can recover from temporary 404s once API is restored.
5. Add focused tests if code changes.
6. Run tests and report changed files.
