from fastapi import APIRouter

from app.schemas import BoldDescriptiveReviewRequest, BoldGroupAnalysisRequest, ScientificReportVerifyRequest
from app.services import agent_service, result_service

router = APIRouter()


@router.post("/agent/tools/verify-scientific-reports")
def agent_verify_scientific_reports(req: ScientificReportVerifyRequest):
    return agent_service.agent_verify_scientific_reports(req)


@router.post("/projects/{project_id}/bold/group-analysis")
def bold_group_analysis(project_id: int, req: BoldGroupAnalysisRequest):
    return result_service.bold_group_analysis(project_id, req)


@router.post("/projects/{project_id}/bold/descriptive-review")
def bold_descriptive_review(project_id: int, req: BoldDescriptiveReviewRequest):
    return result_service.bold_descriptive_review(project_id, req)
