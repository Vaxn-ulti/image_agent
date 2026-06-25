from fastapi import APIRouter

from app.schemas import LoginRequest
from app.services import project_service

router = APIRouter()


@router.post("/auth/login")
def login(req: LoginRequest):
    return project_service.login(req)
