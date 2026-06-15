from fastapi import APIRouter

from app.services import result_service

router = APIRouter()


@router.get("/tasks/{task_id}/result-summary")
def get_result_summary(task_id: int):
    return result_service.get_result_summary(task_id)


@router.get("/tasks/{task_id}/artifact-manifest")
def get_task_artifact_manifest(task_id: int):
    return result_service.get_task_artifact_manifest(task_id)


@router.get("/tasks/{task_id}/artifacts/{relative_path:path}")
def get_task_artifact(task_id: int, relative_path: str):
    return result_service.get_task_artifact(task_id, relative_path)
