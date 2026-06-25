from fastapi import APIRouter, File, UploadFile

from app.schemas import UploadSessionCreate
from app.services import upload_service

router = APIRouter()


@router.post("/projects/{project_id}/upload")
def upload(project_id: int, file: UploadFile = File(...)):
    return upload_service.upload(project_id, file)


@router.post("/projects/{project_id}/upload-dwi")
def upload_dwi(
    project_id: int,
    nifti: UploadFile = File(...),
    bval: UploadFile = File(...),
    bvec: UploadFile = File(...),
    json_sidecar: UploadFile | None = File(None),
):
    return upload_service.upload_dwi(project_id, nifti, bval, bvec, json_sidecar)


@router.post("/projects/{project_id}/upload-dicom")
def upload_dicom(project_id: int, archive: UploadFile = File(...)):
    return upload_service.upload_dicom(project_id, archive)


@router.post("/projects/{project_id}/datasets/upload-session")
def create_upload_session(project_id: int, req: UploadSessionCreate):
    return upload_service.create_upload_session(project_id, req)


@router.post("/projects/{project_id}/datasets/{upload_session_id}/ingest")
def ingest_dataset(project_id: int, upload_session_id: int, archive: UploadFile = File(...), sync_fast_path: bool = True):
    return upload_service.ingest_dataset(project_id, upload_session_id, archive, sync_fast_path)


@router.get("/projects/{project_id}/datasets/{upload_session_id}/inventory")
def get_inventory(project_id: int, upload_session_id: int):
    return upload_service.get_inventory(project_id, upload_session_id)


@router.get("/projects/{project_id}/files")
def list_project_files(project_id: int):
    return upload_service.list_project_files(project_id)


@router.delete("/projects/{project_id}/files/{file_id}")
def delete_project_file(project_id: int, file_id: int):
    return upload_service.delete_project_file(project_id, file_id)
