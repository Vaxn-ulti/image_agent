from app.services.compat import legacy


def upload(project_id, file):
    return legacy().upload(project_id, file)


def upload_dwi(project_id, nifti, bval, bvec, json_sidecar=None):
    return legacy().upload_dwi(project_id, nifti, bval, bvec, json_sidecar)


def upload_dicom(project_id, archive):
    return legacy().upload_dicom(project_id, archive)


def create_upload_session(project_id, req):
    return legacy().create_upload_session(project_id, req)


def ingest_dataset(project_id, upload_session_id, archive, sync_fast_path=True):
    return legacy().ingest_dataset(project_id, upload_session_id, archive, sync_fast_path)


def get_inventory(project_id, upload_session_id):
    return legacy().get_inventory(project_id, upload_session_id)


def list_series(project_id):
    return legacy().list_series(project_id)
