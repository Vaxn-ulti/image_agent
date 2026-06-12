import hashlib
import json
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from threading import Thread

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler as fastapi_request_validation_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from app.agent.graph import AgentRunner
from app.agent.contracts import (
    AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    AgentApiErrorResponse,
    AgentRunLookupResponse,
    AgentRunResponse,
    ChatCompatibilityResponse,
    ProjectAgentRunHistoryResponse,
    agent_api_error_detail,
    build_agent_run_response_payload,
    build_chat_compatibility_response,
    build_project_agent_run_history_response,
    normalize_agent_run_result,
)
from app.agent.model_gateway import ModelGateway, ModelGatewayError, provider_status as model_provider_status
from app.agent.run_ledger import finish_agent_run, list_project_agent_runs, load_agent_run, start_agent_run
from app.agent.tools import read_project_context
from app.agent.deepseek import DeepSeekUnavailable, complete_chat, provider_status as legacy_chat_provider_status
from app.agent.rag_orchestration import build_rag_response
from app.agent.rag_orchestration import dependency_status as rag_dependency_status
from app.agent.rag_orchestration import grounding_policy as rag_grounding_policy
from app.agent.rag_index import build_local_rag_index, local_rag_index_status, rag_vendor_coverage_catalog, rag_vendor_pointer_integrity, vendor_raw_source_status
from app.core.config import PROJECTS_ROOT
from app.db.database import connect, init_db, now_iso, row_to_dict
from app.imaging.detect import detect_series
from app.imaging.ingest import process_upload_session
from app.workflows.artifact_manifest import build_artifact_manifest
from app.workflows.deepprep import run_mock_deepprep
from app.workflows.eligibility import build_workflow_eligibility
from app.workflows.registry import allowed_runtime_workflows, list_workflows as registry_list_workflows, resolve_runtime_workflow_type
from app.workflows.result_contract import load_result_summary, result_contract_spec
from app.workflows.remote_scripts import classify_bold_fmriprep_xcpd_artifact_stage
from app.scripts.verify_scientific_reports import check_output as check_scientific_report_output
from app.scripts.verify_scientific_reports import resolve_task_output_dirs

try:
    from app.workflows.pipeline import inspect_runtime, run_pipeline_task
    from app.workflows.recovery import list_image_agent_containers as _list_agent_containers
except ImportError:
    def run_pipeline_task(task_id: int, qsiprep_task_id: int | None = None) -> None:
        with connect() as conn:
            conn.execute(
                "UPDATE tasks SET status='failed', error_message='pipeline runner missing', finished_at=? WHERE id=?",
                (now_iso(), task_id),
            )

    def inspect_runtime() -> dict:
        return {"error": "pipeline runner missing", "workflows": {}}

    def _list_agent_containers():
        return []

try:
    from app.workflows.bold_group_analysis import run_group_analysis
except ImportError:
    def run_group_analysis(*args, **kwargs):
        raise RuntimeError('bold group analysis unavailable')

try:
    from app.workflows.bold_descriptive_review import run_descriptive_review
except ImportError:
    def run_descriptive_review(*args, **kwargs):
        raise RuntimeError('bold descriptive review unavailable')

app = FastAPI(title="Brain Image Agent API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

REPO_ROOT = Path(__file__).resolve().parents[3]

WORKFLOWS = registry_list_workflows()
ALLOWED_WORKFLOWS = allowed_runtime_workflows()

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


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None
    message: str


class AgentResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    confirmation: dict


class RagQueryRequest(BaseModel):
    project_id: int | None = None
    query: str


class ScientificReportVerifyRequest(BaseModel):
    task_ids: list[int] = []
    output_dirs: list[str] = []
    projects_root: str | None = None
    require_modalities: list[str] = []
    require_container_native_qc: bool = False
    min_native_qc_images: int = 0


class BoldGroupAnalysisRequest(BaseModel):
    group_a_task_ids: list[int]
    group_b_task_ids: list[int]
    seed_query: str = "PCC_DMN"
    label_a: str = "group_a"
    label_b: str = "group_b"


class BoldDescriptiveReviewRequest(BaseModel):
    deepprep_task_ids: list[int]
    seed_preset: str = "PCC_DMN"


def _requested_task_ids(message: str) -> list[int]:
    anchored = [int(match) for match in re.findall(r"(?:#|任务|task\s*)\s*(\d+)", message, flags=re.IGNORECASE)]
    if anchored:
        tail = message
        first_anchor = re.search(r"(?:#|任务|task\s*)\s*\d+", message, flags=re.IGNORECASE)
        if first_anchor:
            tail = message[first_anchor.start() :]
        nearby = [
            int(match)
            for match in re.findall(r"\d+", tail)
            if int(match) >= 20
        ]
        return list(dict.fromkeys([*anchored, *nearby]))
    return []


def _chat_intent(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("task", "tasks", "status", "progress", "state", "任务", "状态", "进度", "查看")):
        return "status"
    if any(token in lowered for token in ("next", "下一步", "建议", "tool", "工具", "调用")):
        return "next_step"
    if any(token in lowered for token in ("series", "image", "影像", "序列")):
        return "series"
    return "general"


def _task_context(project_id: int | None, message: str) -> list[dict]:
    requested_ids = _requested_task_ids(message)
    if project_id and requested_ids:
        placeholders = ",".join("?" for _ in requested_ids)
        query = (
            "SELECT id, project_id, workflow_type, status, progress, error_message "
            f"FROM tasks WHERE project_id=? AND id IN ({placeholders}) ORDER BY id DESC"
        )
        explicit = rows(query, (project_id, *requested_ids))
        found_ids = {task["id"] for task in explicit}
        missing = [
            {
                "id": task_id,
                "workflow_type": "unknown",
                "status": "not_found_in_project",
                "progress": 0,
                "error_message": None,
            }
            for task_id in requested_ids
            if task_id not in found_ids
        ]
        return sorted([*explicit, *missing], key=lambda task: int(task["id"]), reverse=True)
    if project_id:
        return rows(
            "SELECT id, project_id, workflow_type, status, progress, error_message FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 50",
            (project_id,),
        )
    if requested_ids:
        placeholders = ",".join("?" for _ in requested_ids)
        return rows(
            f"SELECT id, project_id, workflow_type, status, progress, error_message FROM tasks WHERE id IN ({placeholders}) ORDER BY id DESC",
            tuple(requested_ids),
        )
    return rows("SELECT id, project_id, workflow_type, status, progress, error_message FROM tasks ORDER BY id DESC LIMIT 10")


def _output_context(project_id: int | None, task_ids: list[int] | None = None) -> list[dict]:
    if task_ids:
        placeholders = ",".join("?" for _ in task_ids)
        return rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json "
            f"FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE outputs.task_id IN ({placeholders}) ORDER BY outputs.id DESC",
            tuple(task_ids),
        )
    if project_id:
        return rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE tasks.project_id=? ORDER BY outputs.id DESC LIMIT 100",
            (project_id,),
        )
    return []


def _result_summary_context(tasks: list[dict]) -> list[dict]:
    summaries = []
    for task in tasks:
        if task.get("status") == "not_found_in_project":
            continue
        output_dir = PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task["id"]) / "output"
        try:
            summary = load_result_summary(output_dir)
        except FileNotFoundError:
            continue
        if summary:
            summaries.append(summary)
    return summaries


def _status_reply(tasks: list[dict], recommended_next_step: str) -> str:
    if not tasks:
        return f"Tasks: none. Recommended next step: {recommended_next_step}"
    parts = []
    for task in tasks:
        error = f", error={task['error_message']}" if task.get("error_message") else ""
        parts.append(f"#{task['id']} {task['workflow_type']} {task['status']} {task['progress']}%{error}")
    return "Tasks: " + "; ".join(parts) + f". Recommended next step: {recommended_next_step}"

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
    file_rows = rows("SELECT storage_path, file_type FROM files WHERE id=?", (r.get("file_id"),))
    if file_rows:
        r["file_storage_path"] = file_rows[0]["storage_path"]
        r["file_type"] = file_rows[0]["file_type"]
    r["workflow_eligibility"] = build_workflow_eligibility(r)
    r.pop("file_storage_path", None)
    r.pop("file_type", None)
    return r

def _qsiprep_output_dir(task_id: int) -> Path:
    task_root = PROJECTS_ROOT / str(task_id)
    # real QSIPrep tasks write to data/projects/<project_id>/derivatives/<task_id>/output
    for project_dir in PROJECTS_ROOT.iterdir() if PROJECTS_ROOT.exists() else []:
        candidate = project_dir / 'derivatives' / str(task_id) / 'output'
        if candidate.exists():
            return candidate
    return PROJECTS_ROOT / '__missing__' / str(task_id) / 'output'


def _qsiprep_output_has_anat(task_id: int) -> bool:
    output_dir = _qsiprep_output_dir(task_id)
    anat_dir = output_dir / 'sub-01' / 'anat'
    return anat_dir.exists() and any(anat_dir.iterdir())


def _sidecar_base(path: Path) -> str:
    return path.name[:-7] if path.name.lower().endswith(".nii.gz") else path.stem


def _dwi_sidecar_paths(series: dict, metadata: dict) -> dict[str, Path]:
    sidecars: dict[str, Path] = {}
    for raw_path in metadata.get("sidecars") or []:
        path = Path(raw_path)
        suffix = path.suffix.lower()
        if suffix in {".json", ".bval", ".bvec"} and path.exists():
            sidecars[suffix] = path

    try:
        main_file = rows("SELECT storage_path FROM files WHERE id=?", (series["file_id"],))[0]
    except (IndexError, KeyError):
        main_file = None
    allow_same_stem_fallback = bool(
        metadata.get("sidecars")
        or metadata.get("bids_path")
        or series.get("format") == "NIFTI_BIDS"
        or (main_file and main_file.get("file_type") == "NIFTI_BIDS")
    )
    if main_file and allow_same_stem_fallback:
        src = Path(main_file["storage_path"])
        base = _sidecar_base(src)
        for suffix in (".json", ".bval", ".bvec"):
            candidate = src.with_name(base + suffix)
            if suffix not in sidecars and candidate.exists():
                sidecars[suffix] = candidate
    return sidecars


def _dwi_has_eddy_json_metadata(series: dict, metadata: dict) -> bool:
    if metadata.get("has_json") and metadata.get("has_dwi_eddy_metadata"):
        return True
    json_path = _dwi_sidecar_paths(series, metadata).get(".json")
    if json_path is None:
        return False
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("PhaseEncodingDirection") is not None and payload.get("TotalReadoutTime") is not None


def _dwi_has_required_sidecars(series: dict, metadata: dict) -> bool:
    sidecars = _dwi_sidecar_paths(series, metadata)
    return (
        bool(metadata.get("has_bval") or ".bval" in sidecars)
        and bool(metadata.get("has_bvec") or ".bvec" in sidecars)
        and _dwi_has_eddy_json_metadata(series, metadata)
    )


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
    return {"status": "ok", "app": "image_agent", "version": "0.2.0"}

@app.get("/workflows")
def list_workflows():
    return {"workflows": WORKFLOWS}


@app.get("/result-contract")
def get_result_contract():
    return result_contract_spec()

@app.get("/deployment")
def deployment():
    mode = os.environ.get("BACKEND_RUNTIME_MODE", "remote")
    return {
        "backend_runtime_mode": mode,
        "api_base_hint": os.environ.get("IMAGE_AGENT_PUBLIC_BASE_URL", ""),
        "agent": model_provider_status(),
        "legacy_chat_provider": legacy_chat_provider_status(),
    }


@app.get("/agent/rag/status")
def agent_rag_status():
    index_status = local_rag_index_status(root=REPO_ROOT, persist_dir=REPO_ROOT / ".rag_index")
    indexed_sources = index_status.get("indexed_sources") or []
    return {
        "dependencies": rag_dependency_status(),
        "grounding_policy": rag_grounding_policy(),
        "index": index_status,
        "vendor_raw_sources": vendor_raw_source_status(
            root=REPO_ROOT,
            indexed_sources=indexed_sources,
        ),
        "vendor_pointer_integrity": rag_vendor_pointer_integrity(root=REPO_ROOT),
        "vendor_coverage_catalog": rag_vendor_coverage_catalog(
            root=REPO_ROOT,
            indexed_sources=indexed_sources,
        ),
    }


@app.post("/agent/rag/rebuild")
def agent_rag_rebuild():
    return build_local_rag_index(root=REPO_ROOT, persist_dir=REPO_ROOT / ".rag_index")


@app.get("/agent/model/status")
def agent_model_status():
    return model_provider_status()


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/agent/runs"):
        return JSONResponse(
            status_code=422,
            content={
                "detail": agent_api_error_detail(
                    "request_contract_violation",
                    "Request does not match the Agent API contract.",
                )
            },
        )
    return await fastapi_request_validation_exception_handler(request, exc)


AGENT_RUN_ERROR_RESPONSES = {
    404: {"model": AgentApiErrorResponse},
    422: {"model": AgentApiErrorResponse},
    502: {"model": AgentApiErrorResponse},
}


@app.post("/agent/runs", response_model=AgentRunResponse, responses=AGENT_RUN_ERROR_RESPONSES)
def agent_run(req: AgentRunRequest):
    message = req.message.strip()
    if not message:
        raise HTTPException(
            422,
            agent_api_error_detail("message_required", "message is required"),
        )
    agent_run_id = start_agent_run(request_type="run", project_id=req.project_id, message=message)
    project_context = read_project_context(req.project_id, rows_fn=rows, workflows=WORKFLOWS)
    try:
        result = normalize_agent_run_result(dict(AgentRunner().run(message=message, project_context=project_context)))
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="run",
            project_id=req.project_id,
        )
    except HTTPException as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise
    except Exception as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise HTTPException(
            502,
            agent_api_error_detail(
                "agent_model_call_failed",
                "Agent model call failed.",
                agent_run_id=agent_run_id,
            ),
        ) from exc


@app.get("/agent/runs/{agent_run_id}", response_model=AgentRunLookupResponse, responses=AGENT_RUN_ERROR_RESPONSES)
def agent_run_lookup(agent_run_id: str):
    run = load_agent_run(agent_run_id)
    if run is None:
        raise HTTPException(
            404,
            agent_api_error_detail("agent_run_not_found", "Agent run not found"),
        )
    return build_agent_run_response_payload(
        run,
        ledger=run,
        contract_version=AGENT_RUN_LOOKUP_CONTRACT_VERSION,
    )


@app.post("/agent/runs/{thread_id}/resume", response_model=AgentRunResponse, responses=AGENT_RUN_ERROR_RESPONSES)
def agent_resume(thread_id: str, req: AgentResumeRequest):
    def _create_task(series_id: int, workflow_type: str, qsiprep_task_id: int | None = None) -> dict:
        return create_series_task(series_id, RunRequest(workflow_type=workflow_type, qsiprep_task_id=qsiprep_task_id))

    agent_run_id = start_agent_run(
        request_type="resume",
        project_id=req.confirmation.get("project_id"),
        thread_id=thread_id,
        approved=req.approved,
        confirmation=req.confirmation,
    )
    try:
        result = normalize_agent_run_result(dict(AgentRunner().resume(
            thread_id=thread_id,
            approved=req.approved,
            confirmation=req.confirmation,
            create_task_fn=_create_task,
        )))
        result["agent_run_id"] = agent_run_id
        finish_agent_run(agent_run_id, result=result)
        ledger = load_agent_run(agent_run_id) or {}
        return build_agent_run_response_payload(
            result,
            ledger=ledger,
            request_type="resume",
        )
    except HTTPException as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise
    except Exception as exc:
        finish_agent_run(agent_run_id, error=exc)
        raise HTTPException(
            502,
            agent_api_error_detail(
                "agent_resume_failed",
                "Agent resume failed.",
                agent_run_id=agent_run_id,
            ),
        ) from exc


@app.post("/agent/rag/query")
def agent_rag_query(req: RagQueryRequest):
    backend_context = {
        "project_id": req.project_id,
        "tasks": rows("SELECT id, workflow_type, status, progress, error_message FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 20", (req.project_id,)) if req.project_id else [],
        "outputs": rows(
            "SELECT outputs.task_id, outputs.output_type, outputs.path, outputs.metadata_json FROM outputs JOIN tasks ON tasks.id=outputs.task_id WHERE tasks.project_id=? ORDER BY outputs.id DESC LIMIT 20",
            (req.project_id,),
        ) if req.project_id else [],
    }
    return build_rag_response(req.query, root=REPO_ROOT, backend_context=backend_context)


@app.post("/agent/tools/verify-scientific-reports")
def agent_verify_scientific_reports(req: ScientificReportVerifyRequest):
    projects_root = Path(req.projects_root) if req.projects_root else PROJECTS_ROOT
    task_output_dirs, resolution_errors = resolve_task_output_dirs(projects_root, req.task_ids)
    explicit_output_dirs = [Path(path) for path in req.output_dirs]
    output_paths = [*explicit_output_dirs, *task_output_dirs]
    results = [
        check_scientific_report_output(
            path,
            require_container_native_qc=req.require_container_native_qc,
            min_native_qc_images=max(req.min_native_qc_images, 0),
        )
        for path in output_paths
    ]
    required_modalities = {modality.upper() for modality in req.require_modalities}
    present_modalities = {result.modality for result in results}
    missing_modalities = sorted(required_modalities - present_modalities)
    ok = all(result.ok for result in results) and not resolution_errors and not missing_modalities
    return {
        "ok": ok,
        "read_only": True,
        "projects_root": str(projects_root),
        "task_ids": req.task_ids,
        "require_container_native_qc": req.require_container_native_qc,
        "min_native_qc_images": max(req.min_native_qc_images, 0),
        "resolution_errors": resolution_errors,
        "missing_modalities": missing_modalities,
        "results": [
            {
                "output_dir": str(result.output_dir),
                "modality": result.modality,
                "ok": result.ok,
                "errors": result.errors,
                "warnings": result.warnings,
            }
            for result in results
        ],
    }


@app.get("/runtime/containers")
def runtime_containers():
    return inspect_runtime()


@app.get("/admin/containers")
def admin_containers():
    """List Docker containers launched by image_agent (label-filtered). Safe: read-only."""
    containers = _list_agent_containers()
    return {"containers": containers, "count": len(containers)}

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

def _dwi_json_metadata(json_row: dict | None) -> dict:
    if json_row is None:
        return {"has_json": False, "has_dwi_eddy_metadata": False}
    path = Path(json_row["storage_path"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "DWI JSON sidecar must be valid JSON") from exc
    phase_encoding = payload.get("PhaseEncodingDirection")
    total_readout = payload.get("TotalReadoutTime")
    return {
        "has_json": True,
        "json_file_id": json_row["id"],
        "has_dwi_eddy_metadata": phase_encoding is not None and total_readout is not None,
        "phase_encoding_direction": phase_encoding,
        "total_readout_time": total_readout,
    }


@app.post("/projects/{project_id}/upload-dwi")
def upload_dwi(
    project_id: int,
    nifti: UploadFile = File(...),
    bval: UploadFile = File(...),
    bvec: UploadFile = File(...),
    json_sidecar: UploadFile | None = File(None),
):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    nifti_row = save_upload(project_id, nifti, "NIFTI")
    bval_row = save_upload(project_id, bval, "BVAL")
    bvec_row = save_upload(project_id, bvec, "BVEC")
    json_row = save_upload(project_id, json_sidecar, "JSON") if json_sidecar is not None else None
    detection = detect_series(nifti_row["storage_path"])
    metadata = detection["metadata"]
    metadata.update(
        {
            "has_bval": True,
            "has_bvec": True,
            "bval_file_id": bval_row["id"],
            "bvec_file_id": bvec_row["id"],
            **_dwi_json_metadata(json_row),
        }
    )
    with connect() as conn:
        scur = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, nifti_row["id"], metadata.get("sequence_label", "DWI_multi_shell"), 1, "", "DWI", "NIFTI", 0.95, json.dumps(metadata), "detected", now_iso()),
        )
        series_row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (scur.lastrowid,)).fetchone()
    file_rows = [nifti_row, bval_row, bvec_row]
    if json_row is not None:
        file_rows.append(json_row)
    return {"files": file_rows, "series": parse_series_row(series_row)}

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
    inventory = enrich_inventory_workflow_eligibility(inventory)
    return {"upload_session_id": upload_session_id, "status": session["status"], "progress": session["progress"], "inventory": inventory, "error_message": session.get("error_message")}


def enrich_inventory_workflow_eligibility(inventory: dict) -> dict:
    if not isinstance(inventory, dict):
        return inventory
    series = inventory.get("series")
    if not isinstance(series, list):
        return inventory
    enriched_series = []
    changed = False
    for item in series:
        if not isinstance(item, dict):
            enriched_series.append(item)
            continue
        eligibility = item.get("workflow_eligibility")
        if isinstance(eligibility, dict) and eligibility.get("policy_version") == "workflow_eligibility_v1":
            enriched_series.append(item)
            continue
        enriched_series.append({**item, "workflow_eligibility": build_workflow_eligibility(item)})
        changed = True
    if not changed:
        return inventory
    return {**inventory, "series": enriched_series}


@app.get("/projects/{project_id}/series")
def list_series(project_id: int):
    return [parse_series_row(r) for r in rows("SELECT * FROM imaging_series WHERE project_id=? ORDER BY id DESC", (project_id,))]

@app.get("/projects/{project_id}/agent-runs", response_model=ProjectAgentRunHistoryResponse)
def list_project_agent_run_history(project_id: int):
    return build_project_agent_run_history_response(project_id, list_project_agent_runs(project_id))

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
    if req.workflow_type not in allowed_runtime_workflows():
        raise HTTPException(400, f"Unknown workflow_type: {req.workflow_type}")
    workflow_type = resolve_runtime_workflow_type(req.workflow_type)
    metadata = json.loads(series["metadata_json"])
    modality = series["modality"]
    if workflow_type == "t1_deepprep_mock":
        if modality != "T1":
            raise HTTPException(400, "T1 mock requires T1 series")
        return
    if workflow_type.startswith("t1_deepprep") and modality != "T1":
        raise HTTPException(400, "DeepPrep requires a T1 series")
    if workflow_type.startswith("bold_deepprep") and modality != "BOLD":
        raise HTTPException(400, "BOLD DeepPrep requires a BOLD/fMRI series")
    if workflow_type.startswith("dwi_qsiprep") or workflow_type.startswith("dwi_qsi_full"):
        if modality != "DWI" or not metadata.get("has_bval") or not metadata.get("has_bvec"):
            raise HTTPException(400, "DWI workflows require DWI series with bval and bvec")
        if workflow_type.startswith("dwi_qsi_full"):
            companion_t1 = rows(
                "SELECT id FROM imaging_series WHERE project_id=? AND modality='T1' AND supported_for_processing=1 ORDER BY id DESC LIMIT 1",
                (series["project_id"],),
            )
            if not companion_t1:
                raise HTTPException(400, "DWI QSIPrep + QSIRecon requires T1/anat data in the same project")
    if workflow_type.startswith("dwi_fast_gpu_dti"):
        if modality != "DWI" or not _dwi_has_required_sidecars(series, metadata):
            raise HTTPException(
                400,
                "DWI fast GPU DTI requires DWI series with bval, bvec, and JSON sidecar containing PhaseEncodingDirection and TotalReadoutTime",
            )
    if workflow_type.startswith("dwi_qsirecon"):
        if not req.qsiprep_task_id:
            raise HTTPException(400, "QSIRecon requires qsiprep_task_id")
        candidates = rows("SELECT * FROM tasks WHERE id=?", (req.qsiprep_task_id,))
        if not candidates:
            raise HTTPException(400, "qsiprep_task_id not found")
        if not candidates[0]["workflow_type"].startswith("dwi_qsiprep") and candidates[0]["workflow_type"] != "dwi_qsi_full":
            raise HTTPException(400, "qsiprep_task_id must reference QSIPrep task")
        if not req.workflow_type.endswith("_validate") and candidates[0]["status"] != "completed":
            raise HTTPException(400, "QSIRecon requires completed QSIPrep task")
        if candidates[0]["status"] == "completed" and not _qsiprep_output_has_anat(req.qsiprep_task_id):
            raise HTTPException(400, "QSIRecon requires QSIPrep output with subject anat derivatives; rerun QSIPrep in a project that includes T1/anat input")
    if workflow_type.startswith("dicom_convert") and modality != "DICOM":
        raise HTTPException(400, "DICOM conversion requires a DICOM archive series")
    if workflow_type.startswith("bold_") and modality != "BOLD":
        raise HTTPException(400, "BOLD workflows require BOLD series")
    if workflow_type.startswith("bold_alff") or workflow_type.startswith("bold_falff") or workflow_type.startswith("bold_second_level"):
        prior = rows(
            "SELECT workflow_type, status FROM tasks WHERE project_id=? AND series_id=? ORDER BY id DESC",
            (series["project_id"], series["id"]),
        )
        has_completed_preproc = any(
            t["status"] == "completed" and t["workflow_type"] == "bold_deepprep"
            for t in prior
        )
        if not has_completed_preproc:
            raise HTTPException(400, "BOLD metrics require a completed bold_deepprep task for this series")
    if series.get("supported_for_processing") == 0 and workflow_type != "t1_deepprep_mock":
        raise HTTPException(400, series.get("unsupported_reason") or "This sequence is not supported for processing")

def create_series_task(series_id: int, req: RunRequest) -> dict:
    try:
        req.workflow_type = resolve_runtime_workflow_type(req.workflow_type)
    except KeyError as exc:
        raise HTTPException(400, f"Unknown workflow_type: {req.workflow_type}") from exc
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


@app.post("/series/{series_id}/run")
def run_series(series_id: int, req: RunRequest):
    return create_series_task(series_id, req)

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
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    output_dir = PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    output_log_dir = output_dir / "logs"
    remote_logs = []
    if output_log_dir.exists():
        for log_file in sorted(output_log_dir.glob("*.log")):
            try:
                log_text = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            remote_logs.append(
                {
                    "name": log_file.name,
                    "path": str(log_file),
                    "source_stage": classify_bold_fmriprep_xcpd_artifact_stage(log_file, output_dir),
                    "size_bytes": log_file.stat().st_size,
                    "tail": log_text[-12000:],
                }
            )
    return {
        "task_id": task_id,
        "text": text,
        "remote_logs": remote_logs,
        "log_paths": [str(path), *[item["path"] for item in remote_logs]],
    }

@app.get("/tasks/{task_id}/outputs")
def get_outputs(task_id: int):
    result = []
    for r in rows("SELECT * FROM outputs WHERE task_id=? ORDER BY id", (task_id,)):
        r["metadata"] = json.loads(r.pop("metadata_json"))
        result.append(r)
    return result


@app.get("/tasks/{task_id}/result-summary")
def get_result_summary(task_id: int):
    task = get_task(task_id)
    task_outputs = get_outputs(task_id)
    for output in task_outputs:
        metadata = output["metadata"]
        output_path = output.get("path") or ""
        if metadata.get("kind") == "result_summary" or output_path.endswith("_result_summary.json"):
            path = Path(output["path"])
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.setdefault("summary_path", str(path))
                return payload
    for output in task_outputs:
        metadata = output["metadata"]
        output_path = output.get("path") or ""
        if metadata.get("kind") == "bold_metrics_summary" and output_path:
            path = Path(output["path"])
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "contract_version": payload.get("contract_version", "legacy-bold-metrics"),
                    "task_id": task_id,
                    "workflow_type": task["workflow_type"],
                    "modality": "BOLD",
                    "spaces": payload.get("spaces", ["MNI152"]),
                    "feature_groups": ["legacy_bold_metrics"],
                    "outputs": {},
                    "provenance": {
                        "legacy_fallback": True,
                        "legacy_summary_path": str(path),
                        "note": "Legacy BOLD metrics summary returned because no unified result_summary was registered.",
                    },
                    "legacy_summary": payload,
                }
    output_dir = PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    summary = load_result_summary(output_dir)
    if summary is None:
        raise HTTPException(404, "Result summary not found")
    return summary


@app.get("/tasks/{task_id}/artifact-manifest")
def get_task_artifact_manifest(task_id: int):
    task = get_task(task_id)
    output_dir = PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task_id) / "output"
    try:
        summary = get_result_summary(task_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        summary = None
    return build_artifact_manifest(task, output_dir, summary, get_outputs(task_id))


@app.get("/tasks/{task_id}/artifacts/{relative_path:path}")
def get_task_artifact(task_id: int, relative_path: str):
    if "\\" in relative_path:
        raise HTTPException(400, "Artifact path is outside the task output directory")
    task = get_task(task_id)
    output_dir = (PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task_id) / "output").resolve()
    target = (output_dir / relative_path).resolve()
    if output_dir not in [target, *target.parents]:
        raise HTTPException(400, "Artifact path is outside the task output directory")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Artifact not found")
    if target.name.endswith(".nii.gz"):
        media_type = "application/gzip"
    else:
        media_type = mimetypes.guess_type(target.name)[0]
    return FileResponse(target, media_type=media_type)


@app.post("/projects/{project_id}/bold/group-analysis")
def bold_group_analysis(project_id: int, req: BoldGroupAnalysisRequest):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    try:
        return run_group_analysis(
            project_id=project_id,
            group_a_tasks=req.group_a_task_ids,
            group_b_tasks=req.group_b_task_ids,
            seed_query=req.seed_query,
            label_a=req.label_a,
            label_b=req.label_b,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/projects/{project_id}/bold/descriptive-review")
def bold_descriptive_review(project_id: int, req: BoldDescriptiveReviewRequest):
    if not rows("SELECT * FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Project not found")
    try:
        return run_descriptive_review(
            project_id=project_id,
            deepprep_task_ids=req.deepprep_task_ids,
            seed_preset=req.seed_preset,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/chat", response_model=ChatCompatibilityResponse)
def chat(req: ChatRequest):
    message = req.message.lower()
    reply = "I can list series, check task status, and explain DICOM, DeepPrep, QSIPrep, QSIRecon, and BOLD workflow results."
    refs = []
    task_context = _task_context(req.project_id, req.message)
    task_ids = [task["id"] for task in task_context if task.get("status") != "not_found_in_project"]
    project_context = {
        "project_id": req.project_id,
        "series": rows("SELECT id, modality, sequence_label, supported_for_processing, status, confidence FROM imaging_series WHERE project_id=? ORDER BY id DESC LIMIT 20", (req.project_id,)) if req.project_id else [],
        "tasks": task_context,
        "outputs": _output_context(req.project_id, task_ids=task_ids),
        "result_summaries": _result_summary_context(task_context),
        "supported_workflows": WORKFLOWS,
    }
    rag_response = build_rag_response(req.message, root=REPO_ROOT, backend_context=project_context)
    intent = rag_response.get("intent") or _chat_intent(req.message)
    tool_recommendation = next(
        (
            invocation.get("result", {}).get("recommended_action")
            for invocation in rag_response.get("tool_invocations", [])
            if invocation.get("tool") == "recommend_next_action"
        ),
        None,
    )
    recommended_next_step = tool_recommendation or rag_response.get("recommended_next_step") or rag_response.get("tool_chain_hint") or "Inspect backend task state before launching a new workflow."
    used_provider = "rules"
    provider_error = ""
    if intent not in {"status", "next_step", "launchability"}:
        try:
            reply = ModelGateway().complete_text(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the built-in chat for image_agent. Answer from backend records first, "
                            "use retrieved RAG only as supporting context, and stay non-diagnostic."
                        ),
                    },
                    {
                        "role": "user",
                        "content": "User message:\n"
                        + req.message
                        + "\n\nBackend project context JSON:\n"
                        + json.dumps(project_context, ensure_ascii=False)[:20000]
                        + "\n\nRetrieved RAG response JSON:\n"
                        + json.dumps(rag_response, ensure_ascii=False)[:12000],
                    },
                ],
                purpose="chat_answer",
            )
            used_provider = "OpenAI"
        except ModelGatewayError as exc:
            provider_error = str(exc)
            try:
                reply = complete_chat(req.message, project_context)
                used_provider = "deepseek"
                provider_error = ""
            except DeepSeekUnavailable as fallback_exc:
                provider_error = f"OpenAI gateway: {provider_error}; DeepSeek fallback: {fallback_exc}"
    message = req.message.lower()
    if intent == "launchability":
        reply = rag_response.get("answer") or "Use workflow_eligibility and backend task records to decide workflow launchability."
        refs = [
            {"type": "rag_source", "source": citation.get("path") or citation.get("source"), "title": citation.get("title")}
            for citation in rag_response.get("citations", [])
            if citation.get("path") or citation.get("source")
        ]
        used_provider = "rules"
    elif "series" in message or "image" in message:
        data = project_context["series"] if req.project_id else []
        reply = "Series: " + (", ".join([f"#{x['id']} {x['modality']} ({x['confidence']:.2f})" for x in data]) or "none")
        used_provider = "rules"
    elif intent in {"status", "next_step"} or "task" in message or "status" in message:
        data = project_context["tasks"]
        reply = _status_reply(data, recommended_next_step)
        refs = [{"type": "task", "id": x["id"]} for x in data if x.get("status") != "not_found_in_project"]
        used_provider = "rules"
    elif "qsiprep" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "QSIPrep preprocesses DWI data and requires a DWI NIfTI plus bval/bvec sidecars."
    elif "qsirecon" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "QSIRecon reconstructs diffusion models from a completed QSIPrep output."
    elif "dicom" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "Upload DICOM studies as a zip archive. Dataset ingest attempts dcm2niix conversion and reports conversion status in inventory."
    elif "alff" in message or "falff" in message or "bold" in message:
        bold_scope = (
            "BOLD/fMRI preprocessing is handled by DeepPrep in this project. "
            "Downstream BOLD structured outputs include ALFF, fALFF, ReHo, DMN, "
            "seed-to-ROI summaries, and fixed-coordinate spherical seed runs."
        )
        reply = bold_scope if used_provider not in {"OpenAI", "deepseek"} else f"{reply}\n\n{bold_scope}"
    elif "deepprep" in message or "t1" in message:
        if used_provider not in {"OpenAI", "deepseek"}:
            reply = "DeepPrep runs anatomical processing for T1 images. Use validate mode to check the command before launching a long job."
    with connect() as conn:
        conn.execute("INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)", (req.project_id, "user", req.message, now_iso()))
        conn.execute("INSERT INTO chat_messages(project_id, role, content, created_at) VALUES(?,?,?,?)", (req.project_id, "assistant", reply, now_iso()))
    return build_chat_compatibility_response(
        {
            "reply": reply,
            "references": refs,
            "provider": used_provider,
            "provider_error": provider_error,
            "intent": intent,
            "recommended_next_step": recommended_next_step,
            "tool_chain_hint": rag_response.get("tool_chain_hint"),
            "tool_invocations": rag_response.get("tool_invocations", []),
            "rag_mode": rag_response.get("mode"),
        }
    )
