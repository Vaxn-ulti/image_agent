# Deployment

Development runs API and frontend separately on the remote server.

API:

```bash
cd /home/yyf/project/image_agent/apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd /home/yyf/project/image_agent/apps/desktop
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Production can later serve built frontend from FastAPI or Tauri can package the UI.
