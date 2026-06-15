from fastapi import APIRouter

from app.services import result_service, task_service

router = APIRouter()


@router.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: int):
    return task_service.list_project_tasks(project_id)


@router.get("/tasks/{task_id}")
def get_task(task_id: int):
    return task_service.get_task(task_id)


@router.get("/tasks/{task_id}/logs")
def get_logs(task_id: int):
    return result_service.get_logs(task_id)


@router.get("/tasks/{task_id}/outputs")
def get_outputs(task_id: int):
    return result_service.get_outputs(task_id)
