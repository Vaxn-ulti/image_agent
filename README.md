# Brain Image Agent MVP

Phase 1 implements a desktop-style web UI connected to a remote FastAPI backend for brain image upload, NIfTI metadata detection, mock T1 DeepPrep execution, logs, outputs, and deterministic chat tools.

## Layout

- `apps/api`: FastAPI backend, SQLite DB, storage, NIfTI detection, mock workflow.
- `apps/desktop`: React/Vite frontend, Tauri-ready later.
- `data`: remote backend storage root.
- `docs`: implementation contracts and handoff notes.

## Run API

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run Frontend

```bash
cd apps/desktop
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Default demo login accepts any username/password and returns a local MVP token.
