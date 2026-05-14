import hashlib
import json
import os
import zipfile
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent.deepseek import DeepSeekUnavailable, complete_chat, provider_status
from app.core.config import PROJECTS_ROOT
from app.db.database import connect, init_db, now_iso, row_to_dict
from app.imaging.detect import detect_series
from app.imaging.ingest import process_upload_session
from app.workflows.deepprep import run_mock_deepprep

try:
    from app.workflows.pipeline import inspect_runtime, run_pipeline_task
except ImportError:
    def run_pipeline_task(task_id: int, qsiprep_task_id: int | None = None) -> None:
        with connect() as conn:
            conn.execute(
                "UPDATE tasks SET status='failed', error_message='pipeline runner missing', finished_at=? WHERE id=?",
                (now_iso(), task_id),
            )

    def inspect_runtime() -> dict:
        return {"error": "pipeline runner missing", "workflows": {}}

app = FastAPI(title="Brain Image Agent API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

WORKFLOWS = [
    {"type": "t1_deepprep", "label": "T1 DeepPrep", "modality": "T1"},
    {"type": "t1_deepprep_validate", "label": "T1 DeepPrep Validate", "modality": "T1"},
    {"type": "bold_deepprep", "label": "fMRI/BOLD DeepPrep", "modality": "BOLD"},
    {"type": "bold_deepprep_validate", "label": "fMRI/BOLD DeepPrep Validate", "modality": "BOLD"},
    {"type": "bold_alff", "label": "BOLD ALFF", "modality": "BOLD"},
    {"type": "bold_alff_validate", "label": "BOLD ALFF Validate", "modality": "BOLD"},
    {"type": "bold_falff", "label": "BOLD fALFF", "modality": "BOLD"},
    {"type": "bold_falff_validate", "label": "BOLD fALFF Validate", "modality": "BOLD"},
    {"type": "dwi_qsiprep", "label": "DWI QSIPrep", "modality": "DWI"},
    {"type": "dwi_qsiprep_validate", "label": "DWI QSIPrep Validate", "modality": "DWI"},
    {"type": "dwi_qsirecon", "label": "DWI QSIRecon", "modality": "DWI"},
    {"type": "dwi_qsirecon_validate", "label": "DWI QSIRecon Validate", "modality": "DWI"},
    {"type": "dwi_qsi_full", "label": "DWI QSIPrep + QSIRecon", "modality": "DWI"},
    {"type": "dwi_qsi_full_validate", "label": "DWI Full Validate", "modality": "DWI"},
    {"type": "dicom_convert", "label": "DICOM to NIfTI", "modality": "DICOM"},
    {"type": "dicom_convert_validate", "label": "DICOM to NIfTI Validate", "modality": "DICOM"},
    {"type": "t1_deepprep_mock", "label": "T1 DeepPrep Mock", "modality": "T1"},
]
ALLOWED_WORKFLOWS = {w["type"] for w in WORKFLOWS}

class LoginRequest(BaseModel):
    username: str
    password: str

class ProjectCreate(BaseModel):
    name: str
    description: str = ""

class UploadSessionCreate(BaseModel):
    source_type: str = "folder_or_archive"
    label: str = "dataset"

class RunRequest(BaseModel):
    workflow_type: str = "t1_deepprep_mock"
    qsiprep_task_id: int | None = None

class ChatRequest(BaseModel):
    project_id: int | None = None
    message: str

@app.on_event("startup")
def startup() -> None:
    init_db()

def rows(sql: str, params=()):
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def parse_series_row(r: dict):
    r = dict(r)
    r["metadata"] = json.loads(r.pop("metadata_json"))
    r["supported_for_processing"] = bool(r.get("supported_for_processing", 1))
    return r

def save_upload(project_id: int, upload: UploadFile, file_type: str | None = None) -> dict:
    raw_dir = PROJECTS_ROOT / str(project_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(upload.filename or "upload.bin").name
    dest = raw_dir / safe_name
    sha = hashlib.sha256()
    with dest.open("wb") as out:
        while chunk := upload.file.read(1024 * 1024):
            sha.update(chunk)
            out.write(chunk)
    inferred = file_type or ("NIFTI" if safe_name.lower().endswith((".nii", ".nii.gz")) else Path(safe_name).suffix.lower().lstrip(".").upper())
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO files(project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, safe_name, str(dest), inferred, dest.stat().st_size, sha.hexdigest(), now_iso()),
        )
        return dict(conn.execute("SELECT * FROM files WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/workflows")
def list_workflows():
    return {"workflows": WORKFLOWS}

@app.get("/deployment")
def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    return {"backend_runtime_mode": mode, "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""), "agent": provider_status()}

@app.get("/runtime/containers")
def runtime_containers():
    return inspect_runtime()

@app.post("/auth/login")
def login(req: LoginRequest):
    with connect() as conn:
        existing = conn.execute("SELECT * FROM users WHERE username=?", (req.username,)).fetchone()
        if existing is None:
            cur = conn.execute("INSERT INTO users(username, created_at) VALUES(?,?)", (req.username, now_iso()))
            user = {"id": cur.lastrowid, "username": req.username}
        else:
            user = {"id": existing["id"], "username": existing["username"]}
    return {"access_token": "mvp-token", "token_type": "bearer", "user": user}

@app.get("/projects")
def list_projects():
    return rows("SELECT * FROM projects ORDER BY id DESC")

@app.post("/projects")
def create_project(req: ProjectCreate):
    with connect() as conn:
        cur = conn.execute("INSERT INTO projects(name, description, created_at) VALUES(?,?,?)", (req.name, req.description, now_iso()))
        project_id = cur.lastrowid
    for sub in ("raw", "logs", "derivatives"):
        (PROJECTS_ROOT / str(project_id) / sub).mkdir(parents=True, exist_ok=True)
    return row_to_dict(rows("SELECT * FROM projects WHERE id=?", (project_id,))[0])

@app.post("/projects/{project_id}/upload")
def upload(project_id: int, file: UploadFile = File(...)):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    file_row = save_upload(project_id, file)
    detection = detect_series(file_row["storage_path"])
    metadata = detection["metadata"]
    with connect() as conn:
        scur = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                file_row["id"],
                metadata.get("sequence_label"),
                1 if metadata.get("supported_for_processing", True) else 0,
                metadata.get("unsupported_reason", ""),
                detection["modality"],
                detection["format"],
                detection["confidence"],
                json.dumps(metadata),
                "detected",
                now_iso(),
            ),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (scur.lastrowid,)).fetchone()
    return {"file": file_row, "series": parse_series_row(series_row)}

@app.post("/projects/{project_id}/upload-dwi")
def upload_dwi(project_id: int, nifti: UploadFile = File(...), bval: UploadFile = File(...), bvec: UploadFile = File(...)):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    nifti_row = save_upload(project_id, nifti, "NIFTI")
    bval_row = save_upload(project_id, bval, "BVAL")
    bvec_row = save_upload(project_id, bvec, "BVEC")
    detection = detect_series(nifti_row["storage_path"])
    metadata = detection["metadata"]
    metadata.update({"has_bval": True, "has_bvec": True, "bval_file_id": bval_row["id"], "bvec_file_id": bvec_row["id"]})
    with connect() as conn:
        scur = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, nifti_row["id"], metadata.get("sequence_label", "DWI_multi_shell"), 1, "", "DWI", "NIFTI", 0.95, json.dumps(metadata), "detected", now_iso()),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (scur.lastrowid,)).fetchone()
    return {"files": [nifti_row, bval_row, bvec_row], "series": parse_series_row(series_row)}

@app.post("/projects/{project_id}/upload-dicom")
def upload_dicom(project_id: int, archive: UploadFile = File(...)):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    archive_row = save_upload(project_id, archive, "DICOM_ZIP")
    extract_dir = PROJECTS_ROOT / str(project_id) / "raw" / f"dicom_{archive_row['id']}"
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_row["storage_path"]) as zf:
            for member in zf.infolist():
                target = (extract_dir / member.filename).resolve()
                if not str(target).startswith(str(extract_dir.resolve())):
                    raise HTTPException(400, "Unsafe DICOM archive path")
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, "DICOM upload must be a zip archive") from exc
    dicom_files = [p for p in extract_dir.rglob("*") if p.is_file()]
    metadata = {"filename": archive_row["original_name"], "archive_file_id": archive_row["id"], "dicom_dir": str(extract_dir), "dicom_file_count": len(dicom_files)}
    with connect() as conn:
        scur = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, archive_row["id"], "DICOM_ARCHIVE", 1, "", "DICOM", "DICOM_ZIP", 0.85 if dicom_files else 0.2, json.dumps(metadata), "detected", now_iso()),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (scur.lastrowid,)).fetchone()
    return {"file": archive_row, "series": parse_series_row(series_row)}

@app.post("/projects/{project_id}/datasets/upload-session")
def create_upload_session(project_id: int, req: UploadSessionCreate):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO upload_sessions(project_id, label, source_type, status, progress, inventory_json, created_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, req.label, req.source_type, "ready", 0, "{}", now_iso()),
        )
        return dict(conn.execute("SELECT * FROM upload_sessions WHERE id=?", (cur.lastrowid,)).fetchone())

@app.post("/projects/{project_id}/datasets/{upload_session_id}/ingest")
def ingest_dataset(project_id: int, upload_session_id: int, archive: UploadFile = File(...), sync_fast_path: bool = True):
    sessions = rows("SELECT * FROM upload_sessions WHERE id=? AND project_id=?", (upload_session_id, project_id))
    if not sessions:
        raise HTTPException(404, "Upload session not found")
    upload_dir = PROJECTS_ROOT / str(project_id) / "uploads" / str(upload_session_id) / "originals"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(archive.filename or "dataset.zip").name
    archive_path = upload_dir / safe_name
    with archive_path.open("wb") as out:
        while chunk := archive.file.read(1024 * 1024):
            out.write(chunk)
    threshold = int(os.environ.get("IMAGE_AGENT_SYNC_INGEST_MAX_BYTES", str(32 * 1024 * 1024)))
    if sync_fast_path and archive_path.stat().st_size <= threshold:
        inventory = process_upload_session(project_id, upload_session_id, archive_path)
        return {"upload_session_id": upload_session_id, "status": inventory["inventory_status"], "inventory": inventory}
    Thread(target=process_upload_session, args=(project_id, upload_session_id, archive_path), daemon=True).start()
    return {"upload_session_id": upload_session_id, "status": "running"}

@app.get("/projects/{project_id}/datasets/{upload_session_id}/inventory")
def get_inventory(project_id: int, upload_session_id: int):
    found = rows("SELECT * FROM upload_sessions WHERE id=? AND project_id=?", (upload_session_id, project_id))
    if not found:
        raise HTTPException(404, "Upload session not found")
    session = found[0]
    inventory = json.loads(session["inventory_json"] or "{}")
    return {"upload_session_id": upload_session_id, "status": session["status"], "progress": session["progress"], "inventory": inventory, "error_message": session.get("error_message")}

@app.get("/projects/{project_id}/series")
def list_series(project_id: int):
    return [parse_series_row(r) for r in rows("SELECT * FROM imaging_series WHERE project_id=? ORDER BY id DESC", (project_id,))]

@app.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: int):
    return rows("SELECT * FROM tasks WHERE project_id=? ORDER BY id DESC", (project_id,))

@app.get("/series/{series_id}")
def get_series(series_id: int):
    found = rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
    if not found:
        raise HTTPException(404, "Series not found")
    return parse_series_row(found[0])

def validate_run_request(series: dict, req: RunRequest) -> None:
    if req.workflow_type not in ALLOWED_WORKFLOWS:
        raise HTTPException(400, f"Unknown workflow_type: {req.workflow_type}")
    metadata = json.loads(series["metadata_json"])
    modality = series["modality"]
    if req.workflow_type == "t1_deepprep_mock":
        if modality != "T1":
            raise HTTPException(400, "T1 mock requires T1 series")
        return
    if req.workflow_type.startswith("t1_deepprep") and modality != "T1":
        raise HTTPException(400, "DeepPrep requires a T1 series")
    if req.workflow_type.startswith("bold_deepprep") and modality != "BOLD":
        raise HTTPException(400, "BOLD DeepPrep requires a BOLD/fMRI series")
    if req.workflow_type.startswith("dwi_qsiprep") or req.workflow_type.startswith("dwi_qsi_full"):
        if modality != "DWI" or not metadata.get("has_bval") or not metadata.get("has_bvec"):
            raise HTTPException(400, "DWI workflows require DWI series with bval and bvec")
    if req.workflow_type.startswith("dwi_qsirecon"):
        if not req.qsiprep_task_id:
            raise HTTPException(400, "QSIRecon requires qsiprep_task_id")
        candidates = rows("SELECT * FROM tasks WHERE id=?", (req.qsiprep_task_id,))
        if not candidates:
            raise HTTPException(400, "qsiprep_task_id not found")
        if not candidates[0]["workflow_type"].startswith("dwi_qsiprep") and candidates[0]["workflow_type"] != "dwi_qsi_full":
            raise HTTPException(400, "qsiprep_task_id must reference QSIPrep task")
        if not req.workflow_type.endswith("_validate") and candidates[0]["status"] != "completed":
            raise HTTPException(400, "QSIRecon requires completed QSIPrep task")
    if req.workflow_type.startswith("dicom_convert") and modality != "DICOM":
        raise HTTPException(400, "DICOM conversion requires a DICOM archive series")
    if req.workflow_type.startswith("bold_") and modality != "BOLD":
        raise HTTPException(400, "BOLD workflows require BOLD series")
    if req.workflow_type.startswith("bold_alff") or req.workflow_type.startswith("bold_falff"):
        project_id = series["project_id"]
        prior = rows(
            "SELECT workflow_type, status FROM tasks WHERE project_id=? ORDER BY id DESC",
            (project_id,),
        )
        if req.workflow_type.endswith("_validate"):
            has_any_preproc = any(
                t["workflow_type"] in {"bold_deepprep_validate", "bold_deepprep", "t1_deepprep_validate", "t1_deepprep"}
                for t in prior
            )
            if not has_any_preproc:
                raise HTTPException(400, "BOLD ALFF/fALFF validate requires a prior fMRIPrep/DeepPrep task")
        else:
            has_completed_preproc = any(
                t["status"] == "completed" and t["workflow_type"] in {"bold_deepprep", "t1_deepprep"}
                for t in prior
            )
            if not has_completed_preproc:
                raise HTTPException(400, "BOLD ALFF/fALFF requires a completed fMRIPrep/DeepPrep task")
    if series.get("supported_for_processing") == 0 and req.workflow_type != "t1_deepprep_mock":
        raise HTTPException(400, series.get("unsupported_reason") or "This sequence is not supported for processing")

@app.post("/series/{series_id}/run")
def run_series(series_id: int, req: RunRequest):
    series = rows("SELECT * FROM imaging_series WHERE id=?", (series_id,))
    if not series:
        raise HTTPException(404, "Series not found")
    series_row = series[0]
    validate_run_request(series_row, req)
    project_id = series_row["project_id"]
    log_path = PROJECTS_ROOT / str(project_id) / "logs" / "pending.log"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks(project_id, series_id, workflow_type, status, progress, log_path, qsiprep_task_id, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (project_id, series_id, req.workflow_type, "queued", 0, str(log_path), req.qsiprep_task_id, now_iso()),
        )
        task_id = cur.lastrowid
        final_log = PROJECTS_ROOT / str(project_id) / "logs" / f"{task_id}.log"
        conn.execute("UPDATE tasks SET log_path=? WHERE id=?", (str(final_log), task_id))
        task = dict(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
    if req.workflow_type == "t1_deepprep_mock":
        Thread(target=run_mock_deepprep, args=(task_id,), daemon=True).start()
    else:
        Thread(target=run_pipeline_task, args=(task_id, req.qsiprep_task_id), daemon=True).start()
    return task

@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    found = rows("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not found:
        raise HTTPException(404, "Task not found")
    return found[0]

@app.get("/tasks/{task_id}/logs")
def get_logs(task_id: int):
    task = get_task(task_id)
    path = Path(task["log_path"])
    return {"task_id": task_id, "text": path.read_text(encoding="utf-8") if path.exists() else ""}

@app.get("/tasks/{task_id}/outputs")
def get_outputs(task_id: int):
    result = []
    for r in rows("SELECT * FROM outputs WHERE task_id=? ORDER BY id", (task_id,)):
        r["metadata"] = json.loads(r.pop("metadata_json"))
        result.append(r)
    return result

@app.post("/chat")
def chat(req: ChatRequest):
    message = req.message.lower()
    reply = "I can list series, check task status, and explain DICOM, DeepPrep, QSIPrep, QSIRecon, and BOLD workflow results."
    refs = []
    project_context = {
        "project_id": req.project_id,
        "series": rows("SELECT id, modality, sequence_label, supported_for_processing, status, confidence FROM imaging_series WHERE project_id=? ORDER BY id DESC LIMIT 20", (req.project_id,)) if req.project_id else [],
        "tasks": rows("SELECT id, workflow_type, status, progress, error_message FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 20", (req.project_id,)) if req.project_id else rows("SELECT id, workflow_type, status, progress, error_message FROM tasks ORDER BY id DESC LIMIT 5"),
        "supported_workflows": WORKFLOWS,
    }
    used_provider = "rules"
    provider_error = ""
    try:
        reply = complete_chat(req.message, project_context)
        used_provider = "deepseek"
    except DeepSeekUnavailable as exc:
        provider_error = str(exc)
    message = req.message.lower()
    if "series" in message or "image" in message:
        data = project_context["series"] if req.project_id else []
        reply = "Series: " + (", ".join([f"#{x['id']} {x['modality']} ({x['confidence']:.2f})" for x in data]) or "none")
        used_provider = "rules"
    elif "task" in message or "status" in message:
        data = project_context["tasks"]
        reply = "Tasks: " + (", ".join([f"#{x['id']} {x['workflow_type']} {x['status']} {x['progress']}%" for x in data]) or "none")
        refs = [{"type": "task", "id": x["id"]} for x in data]
        used_provider = "rules"
    elif "qsiprep" in message:
        if used_provider != "deepseek":
            reply = "QSIPrep preprocesses DWI data and requires a DWI NIfTI plus bval/bvec sidecars."
    elif "qsirecon" in message:
        if used_provider != "deepseek":
            reply = "QSIRecon reconstructs diffusion models from a completed QSIPrep output."
    elif "dicom" in message:
        if used_provider != "deepseek":
            reply = "Upload DICOM studies as a zip archive. Dataset ingest attempts dcm2niix conversion and reports conversion status in inventory."
    elif "alff" in message or "falff" in message or "bold" in message:
        if used_provider != "deepseek":
            reply = "BOLD/fMRI preprocessing is handled by DeepPrep in this project. ALFF/fALFF metric computation is planned after preprocessing outputs are validated."
    elif "deepprep" in message or "t1" in message:
        if used_provider != "deepseek":
            reply = "DeepPrep runs anatomical processing for T1 images. Use validate mode to check the command before launching a long job."
    with connect() as conn:
        conn.execute("INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)", (req.project_id, "user", req.message, now_iso()))
        conn.execute("INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)", (req.project_id, "assistant", reply, now_iso()))
    return {"reply": reply, "references": refs, "provider": used_provider, "provider_error": provider_error}
