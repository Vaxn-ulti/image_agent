from fastapi import APIRouter

from app.schemas import RunRequest
from app.services import task_service, upload_service

router = APIRouter()


@router.get("/projects/{project_id}/series")
def list_series(project_id: int):
    return upload_service.list_series(project_id)


@router.get("/series/{series_id}")
def get_series(series_id: int):
    return task_service.get_series(series_id)


@router.post("/series/{series_id}/run")
def run_series(series_id: int, req: RunRequest):
    return task_service.run_series(series_id, req)
