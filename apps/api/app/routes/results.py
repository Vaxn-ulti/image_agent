from fastapi import APIRouter
from fastapi import HTTPException
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse

from app.services import result_service

router = APIRouter()


@router.get("/tasks/{task_id}/result-summary")
def get_result_summary(task_id: int):
    return result_service.get_result_summary(task_id)


@router.get("/tasks/{task_id}/artifact-manifest")
def get_task_artifact_manifest(task_id: int):
    return result_service.get_task_artifact_manifest(task_id)


@router.get("/tasks/{task_id}/export-bundle")
def get_task_export_bundle(task_id: int):
    bundle = result_service.create_task_export_bundle(task_id)
    return FileResponse(
        bundle["path"],
        filename=bundle["filename"],
        media_type=bundle["media_type"],
        background=BackgroundTask(bundle["path"].unlink, missing_ok=True),
    )


@router.post("/tasks/{task_id}/export-bundle-ticket")
def create_task_export_bundle_ticket(task_id: int):
    return result_service.create_task_export_ticket(task_id)


@router.get("/tasks/{task_id}/export-bundle-download")
def download_task_export_bundle_with_ticket(task_id: int, ticket: str):
    if not result_service.consume_task_export_ticket(task_id, ticket):
        raise HTTPException(status_code=403, detail="Invalid or expired export download ticket")
    bundle = result_service.create_task_export_bundle(task_id)
    return FileResponse(
        bundle["path"],
        filename=bundle["filename"],
        media_type=bundle["media_type"],
        background=BackgroundTask(bundle["path"].unlink, missing_ok=True),
    )


@router.get("/tasks/{task_id}/artifacts/{relative_path:path}")
def get_task_artifact(task_id: int, relative_path: str):
    artifact = result_service.resolve_task_artifact(task_id, relative_path)
    return FileResponse(artifact["path"], media_type=artifact["media_type"])
