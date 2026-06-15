from fastapi import APIRouter

from app.services import agent_service

router = APIRouter()


@router.get("/health")
def health():
    return agent_service.health()


@router.get("/workflows")
def list_workflows():
    return agent_service.list_workflows()


@router.get("/result-contract")
def get_result_contract():
    return agent_service.get_result_contract()


@router.get("/deployment")
def deployment():
    return agent_service.deployment()


@router.get("/runtime/containers")
def runtime_containers():
    return agent_service.runtime_containers()


@router.get("/admin/containers")
def admin_containers():
    return agent_service.admin_containers()
