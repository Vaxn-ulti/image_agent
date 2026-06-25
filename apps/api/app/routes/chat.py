from fastapi import APIRouter

from app.agent.contracts import ChatCompatibilityResponse
from app.schemas import ChatRequest
from app.services import agent_service

router = APIRouter()


@router.post("/chat", response_model=ChatCompatibilityResponse)
def chat(req: ChatRequest):
    return agent_service.chat(req)
