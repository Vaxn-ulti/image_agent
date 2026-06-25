from fastapi import APIRouter

from app.schemas import ProjectCreate
from app.services import project_service

router = APIRouter()


@router.get("/projects")
def list_projects():
    return project_service.list_projects()


@router.post("/projects")
def create_project(req: ProjectCreate):
    return project_service.create_project(req)
