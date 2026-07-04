import gzip
import io
import json
import struct
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.main import app


def test_missing_project_scoped_lists_return_404(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)

    series = client.get('/projects/999/series')
    tasks = client.get('/projects/999/tasks')

    assert series.status_code == 404
    assert tasks.status_code == 404
    assert series.json()['detail'] == 'Project not found'
    assert tasks.json()['detail'] == 'Project not found'


def make_nifti(path: Path, shape=(64, 64, 32)):
    header = bytearray(348)
    struct.pack_into('<i', header, 0, 348)
    dims = [len(shape), *shape, *([1] * (7 - len(shape)))]
    struct.pack_into('<8h', header, 40, *dims)
    struct.pack_into('<h', header, 70, 16)
    struct.pack_into('<h', header, 72, 32)
    struct.pack_into('<8f', header, 76, 0.0, 1.0, 1.0, 1.2, 1.0, 0.0, 0.0, 0.0)
    header[344:348] = b'n+1\0'
    if path.name.endswith('.gz'):
        with gzip.open(path, 'wb') as f:
            f.write(header)
    else:
        path.write_bytes(header)


def uploaded_storage_path(database, file_id: int) -> Path:
    with database.connect() as conn:
        row = conn.execute("SELECT storage_path FROM files WHERE id=?", (file_id,)).fetchone()
    return Path(row["storage_path"])


def test_upload_responses_omit_backend_storage_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-upload-safe'}).json()
    t1 = tmp_path / 'sub-001_T1w.nii.gz'
    dwi = tmp_path / 'sub-001_dwi.nii.gz'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    dicom_zip = tmp_path / 'dicom.zip'
    make_nifti(t1)
    make_nifti(dwi, shape=(8, 8, 8, 3))
    bval.write_text('0 1000\n', encoding='utf-8')
    bvec.write_text('1 0\n0 1\n0 0\n', encoding='utf-8')
    with zipfile.ZipFile(dicom_zip, 'w') as zf:
        zf.writestr('series/image-1.dcm', 'dicom')

    with t1.open('rb') as t1_f:
        standard = client.post(f"/projects/{project['id']}/upload", files={'file': (t1.name, t1_f, 'application/gzip')}).json()
    with dwi.open('rb') as dwi_f, bval.open('rb') as bval_f, bvec.open('rb') as bvec_f:
        dwi_upload = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                'nifti': (dwi.name, dwi_f, 'application/gzip'),
                'bval': (bval.name, bval_f, 'text/plain'),
                'bvec': (bvec.name, bvec_f, 'text/plain'),
            },
        ).json()
    with dicom_zip.open('rb') as dicom_f:
        dicom = client.post(f"/projects/{project['id']}/upload-dicom", files={'archive': (dicom_zip.name, dicom_f, 'application/zip')}).json()

    serialized = json.dumps({'standard': standard, 'dwi_upload': dwi_upload, 'dicom': dicom})
    assert 'storage_path' not in standard['file']
    assert all('storage_path' not in item for item in dwi_upload['files'])
    assert 'storage_path' not in dicom['file']
    assert str(tmp_path / 'projects') not in serialized
    assert standard['file']['id']
    assert dwi_upload['files'][0]['id']
    assert dicom['file']['id']
    assert uploaded_storage_path(database, standard['file']['id']).exists()


def test_single_file_upload_creates_completed_upload_session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-upload-session-contract'}).json()
    nifti = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nifti)

    with nifti.open('rb') as f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload",
            files={'file': (nifti.name, f, 'application/gzip')},
        ).json()

    upload_session_id = uploaded['upload_session_id']
    assert isinstance(upload_session_id, int) and upload_session_id > 0
    assert uploaded['series']['upload_session_id'] == upload_session_id
    inventory = client.get(f"/projects/{project['id']}/datasets/{upload_session_id}/inventory").json()
    assert inventory['status'] == 'completed'
    assert inventory['progress'] == 100
    assert inventory['inventory']['inventory_status'] == 'completed'
    assert inventory['inventory']['series'][0]['series_id'] == uploaded['series']['id']
    assert inventory['inventory']['series'][0]['workflow_eligibility']['policy_version'] == 'workflow_eligibility_v1'
    assert str(tmp_path / 'projects') not in json.dumps({'uploaded': uploaded, 'inventory': inventory})


def test_arbitrary_file_upload_is_saved_as_attachment_not_imaging_series(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-upload-attachments'}).json()
    note = tmp_path / 'operator-notes.txt'
    note.write_text('scan notes and acquisition caveats\n', encoding='utf-8')

    with note.open('rb') as f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload",
            files={'file': (note.name, f, 'text/plain')},
        ).json()

    assert uploaded['file']['original_name'] == 'operator-notes.txt'
    assert uploaded['series'] is None
    upload_session_id = uploaded['upload_session_id']
    inventory = client.get(f"/projects/{project['id']}/datasets/{upload_session_id}/inventory").json()
    assert inventory['status'] == 'completed'
    assert inventory['inventory']['inventory_status'] == 'completed'
    assert inventory['inventory']['total_files'] == 1
    assert inventory['inventory']['series'] == []
    assert inventory['inventory']['attachments'][0]['original_name'] == 'operator-notes.txt'
    assert inventory['inventory']['attachments'][0]['file_type'] == 'TXT'
    assert client.get(f"/projects/{project['id']}/series").json() == []
    assert str(tmp_path / 'projects') not in json.dumps({'uploaded': uploaded, 'inventory': inventory})


def test_project_files_endpoint_lists_uploads_with_linked_detection_without_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-file-list'}).json()
    t1 = tmp_path / 'sub-001_T1w.nii.gz'
    note = tmp_path / 'operator-notes.txt'
    make_nifti(t1)
    note.write_text('notes\n', encoding='utf-8')

    with t1.open('rb') as f:
        client.post(f"/projects/{project['id']}/upload", files={'file': (t1.name, f, 'application/gzip')})
    with note.open('rb') as f:
        client.post(f"/projects/{project['id']}/upload", files={'file': (note.name, f, 'text/plain')})

    files = client.get(f"/projects/{project['id']}/files").json()

    assert [item['original_name'] for item in files] == ['operator-notes.txt', 'sub-001_T1w.nii.gz']
    t1_file = next(item for item in files if item['original_name'] == 'sub-001_T1w.nii.gz')
    assert t1_file['linked_series'][0]['modality'] == 'T1'
    assert t1_file['linked_series'][0]['sequence_label'] == 'T1w_MPRAGE'
    note_file = next(item for item in files if item['original_name'] == 'operator-notes.txt')
    assert note_file['linked_series'] == []
    assert 'storage_path' not in json.dumps(files)
    assert str(tmp_path / 'projects') not in json.dumps(files)


def test_project_file_delete_removes_unstarted_upload_and_linked_series(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-delete-file'}).json()
    t1 = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(t1)
    with t1.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (t1.name, f, 'application/gzip')}).json()

    storage_path = uploaded_storage_path(database, uploaded['file']['id'])
    response = client.delete(f"/projects/{project['id']}/files/{uploaded['file']['id']}")

    assert response.status_code == 200
    assert response.json()['deleted_file']['original_name'] == 'sub-001_T1w.nii.gz'
    assert response.json()['deleted_series_ids'] == [uploaded['series']['id']]
    assert not storage_path.exists()
    assert client.get(f"/projects/{project['id']}/files").json() == []
    assert client.get(f"/projects/{project['id']}/series").json() == []


def test_project_file_delete_blocks_when_referenced_by_task(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-delete-protected'}).json()
    t1 = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(t1)
    with t1.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (t1.name, f, 'application/gzip')}).json()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?)",
            (project['id'], uploaded['series']['id'], 't1_deepprep_anat_report', 'queued', 0, str(tmp_path / 'task.log'), '2026-06-22T00:00:00'),
        )

    response = client.delete(f"/projects/{project['id']}/files/{uploaded['file']['id']}")

    assert response.status_code == 409
    assert 'referenced by existing tasks' in response.json()['detail']
    assert uploaded_storage_path(database, uploaded['file']['id']).exists()


def test_dwi_sidecar_upload_rejects_clear_bold_or_t1_nifti(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-dwi-conflict'}).json()
    bold = tmp_path / 'sub-001_task-rest_bold.nii.gz'
    bval = tmp_path / 'sub-001_task-rest_bold.bval'
    bvec = tmp_path / 'sub-001_task-rest_bold.bvec'
    sidecar = tmp_path / 'sub-001_task-rest_bold.json'
    make_nifti(bold, shape=(8, 8, 8, 120))
    bval.write_text('0 1000\n', encoding='utf-8')
    bvec.write_text('1 0\n0 1\n0 0\n', encoding='utf-8')
    sidecar.write_text(json.dumps({'TaskName': 'rest', 'RepetitionTime': 2.0}), encoding='utf-8')

    with bold.open('rb') as nii_f, bval.open('rb') as bval_f, bvec.open('rb') as bvec_f, sidecar.open('rb') as json_f:
        response = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                'nifti': (bold.name, nii_f, 'application/gzip'),
                'bval': (bval.name, bval_f, 'text/plain'),
                'bvec': (bvec.name, bvec_f, 'text/plain'),
                'json_sidecar': (sidecar.name, json_f, 'application/json'),
            },
        )

    assert response.status_code == 400
    assert 'BOLD' in response.json()['detail']


def test_pipeline_bids_preserves_uncompressed_nifti_and_sidecars(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.workflows import pipeline
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-real-nii'}).json()
    nii = tmp_path / 'sub-001_dwi.nii'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    sidecar = tmp_path / 'sub-001_dwi.json'
    make_nifti(nii, shape=(8, 8, 8, 3))
    bval.write_text('0 1000 1000\n', encoding='utf-8')
    bvec.write_text('1 0 0\n0 1 0\n0 0 1\n', encoding='utf-8')
    sidecar.write_text('{}\n', encoding='utf-8')
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/octet-stream')}).json()
    series = uploaded['series']
    assert series['modality'] == 'DWI'
    stored = uploaded_storage_path(database, uploaded['file']['id'])
    for sidecar in (bval, bvec, sidecar):
        stored.with_name(sidecar.name).write_bytes(sidecar.read_bytes())

    task = {
        'id': 1,
        'project_id': project['id'],
        'series_id': series['id'],
        'workflow_type': 'dwi_qsiprep_validate',
        'log_path': str(tmp_path / 'task.log'),
    }
    dirs = pipeline._build_bids(task, {'metadata_json': json.dumps(series['metadata']), **series})
    staged_nifti = dirs['bids'] / 'sub-01' / 'dwi' / 'sub-01_dwi.nii.gz'
    assert staged_nifti.exists()
    assert staged_nifti.read_bytes()[:2] == b'\x1f\x8b'
    assert (dirs['bids'] / 'sub-01' / 'dwi' / 'sub-01_dwi.bval').exists()
    assert (dirs['bids'] / 'sub-01' / 'dwi' / 'sub-01_dwi.bvec').exists()
    assert (dirs['bids'] / 'sub-01' / 'dwi' / 'sub-01_dwi.json').exists()
    assert not (dirs['bids'] / 'sub-01' / 'dwi' / 'sub-01_dwi.json').is_symlink()


def test_dwi_stage_copies_uploaded_json_sidecar_by_file_id(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.workflows import pipeline
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-dwi-json-stage'}).json()
    dwi = tmp_path / 'sub-001_dwi.nii.gz'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    sidecar = tmp_path / 'sub-001_dwi.json'
    make_nifti(dwi, shape=(8, 8, 8, 3))
    bval.write_text('0 1000 1000\n', encoding='utf-8')
    bvec.write_text('1 0 0\n0 1 0\n0 0 1\n', encoding='utf-8')
    sidecar.write_text('{"PhaseEncodingDirection": "j-", "TotalReadoutTime": 0.07}', encoding='utf-8')
    with dwi.open('rb') as f, bval.open('rb') as bval_f, bvec.open('rb') as bvec_f, sidecar.open('rb') as json_f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                'nifti': (dwi.name, f, 'application/gzip'),
                'bval': (bval.name, bval_f, 'text/plain'),
                'bvec': (bvec.name, bvec_f, 'text/plain'),
                'json_sidecar': (sidecar.name, json_f, 'application/json'),
            },
        ).json()

    task = {
        'id': 12,
        'project_id': project['id'],
        'series_id': uploaded['series']['id'],
        'workflow_type': 'dwi_fast_gpu_dti_validate',
        'log_path': str(tmp_path / 'task.log'),
    }
    dirs = pipeline._build_bids(task, {'metadata_json': json.dumps(uploaded['series']['metadata']), **uploaded['series']})
    staged = dirs['bids'] / 'sub-01' / 'dwi' / 'sub-01_dwi.json'

    assert json.loads(staged.read_text(encoding='utf-8'))['PhaseEncodingDirection'] == 'j-'


def test_container_workflows_request_gpu(monkeypatch, tmp_path):
    from app.workflows import pipeline
    monkeypatch.setattr(pipeline, 'FS_LICENSE', tmp_path / 'license.txt')
    dirs = {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    }

    for workflow in ('t1_deepprep', 'bold_deepprep', 'dwi_qsiprep', 'dwi_qsirecon', 'dwi_qsi_full'):
        for cmd in pipeline._commands(workflow, dirs):
            assert '--gpus' in cmd
            assert cmd[cmd.index('--gpus') + 1] == 'all'


def test_dwi_bids_includes_project_t1_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.workflows import pipeline
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-dwi-with-t1'}).json()
    t1 = tmp_path / 'sub-001_T1w.nii'
    dwi = tmp_path / 'sub-001_dwi.nii'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    make_nifti(t1, shape=(8, 8, 8))
    make_nifti(dwi, shape=(8, 8, 8, 3))
    bval.write_text('0 1000 1000\n', encoding='utf-8')
    bvec.write_text('1 0 0\n0 1 0\n0 0 1\n', encoding='utf-8')

    with t1.open('rb') as f:
        t1_upload = client.post(f"/projects/{project['id']}/upload", files={'file': (t1.name, f, 'application/octet-stream')}).json()
    with dwi.open('rb') as f:
        dwi_upload = client.post(f"/projects/{project['id']}/upload", files={'file': (dwi.name, f, 'application/octet-stream')}).json()
    stored_dwi = uploaded_storage_path(database, dwi_upload['file']['id'])
    for sidecar in (bval, bvec):
        stored_dwi.with_name(sidecar.name).write_bytes(sidecar.read_bytes())

    task = {
        'id': 2,
        'project_id': project['id'],
        'series_id': dwi_upload['series']['id'],
        'workflow_type': 'dwi_qsiprep_validate',
        'log_path': str(tmp_path / 'task.log'),
    }
    dirs = pipeline._build_bids(task, {'metadata_json': json.dumps(dwi_upload['series']['metadata']), **dwi_upload['series']})

    assert (dirs['bids'] / 'sub-01' / 'anat' / 'sub-01_T1w.nii.gz').exists()
    cmd = pipeline._commands('dwi_qsiprep', dirs)[0]
    assert '--anat-modality' not in cmd


def test_dwi_without_project_t1_uses_anat_modality_none(tmp_path, monkeypatch):
    from app.workflows import pipeline
    dirs = {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    }
    (dirs['bids'] / 'sub-01' / 'dwi').mkdir(parents=True)
    cmd = pipeline._commands('dwi_qsiprep', dirs)[0]
    wrapper_script = cmd[cmd.index('-c') + 1]
    assert '--anat-modality none' in wrapper_script
    assert '--eddy-config /eddy_cuda_config.json' in wrapper_script
    assert (tmp_path / 'eddy_cuda_config.json').exists()
    config = json.loads((tmp_path / 'eddy_cuda_config.json').read_text(encoding='utf-8'))
    assert config['use_cuda'] is True
    assert config['num_threads'] >= 2
    assert config['dont_peas'] is True
    assert config['cnr_maps'] is True
    assert config['niter'] == 3
    assert config['is_shelled'] is True


def test_eddy_config_uses_default_omp_threads(tmp_path, monkeypatch):
    """eddy num_threads defaults to DWI_QSIPREP_OMP_NTHREADS (4) with floor 2."""
    monkeypatch.delenv("IMAGE_AGENT_EDDY_NUM_THREADS", raising=False)
    monkeypatch.setenv("IMAGE_AGENT_DWI_QSIPREP_OMP_NTHREADS", "4")
    monkeypatch.setenv("IMAGE_AGENT_DWI_QSIPREP_NTHREADS", "8")
    # Force re-import so module-level constants pick up monkeypatched env
    import app.workflows.pipeline as p
    import importlib
    importlib.reload(p)
    dirs = {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    (dirs["bids"] / "sub-01" / "dwi").mkdir(parents=True)
    p._write_qsiprep_eddy_cuda_config(dirs)
    config = json.loads((tmp_path / "eddy_cuda_config.json").read_text(encoding="utf-8"))
    assert config["num_threads"] == 4
    assert config["use_cuda"] is True
    assert config["cnr_maps"] is True
    assert config["niter"] == 3
    assert config["is_shelled"] is True


def test_eddy_config_env_override(tmp_path, monkeypatch):
    """IMAGE_AGENT_EDDY_NUM_THREADS overrides the default."""
    monkeypatch.setenv("IMAGE_AGENT_EDDY_NUM_THREADS", "4")
    monkeypatch.setenv("IMAGE_AGENT_DWI_QSIPREP_OMP_NTHREADS", "2")
    import app.workflows.pipeline as p
    import importlib
    importlib.reload(p)
    dirs = {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    (dirs["bids"] / "sub-01" / "dwi").mkdir(parents=True)
    p._write_qsiprep_eddy_cuda_config(dirs)
    config = json.loads((tmp_path / "eddy_cuda_config.json").read_text(encoding="utf-8"))
    assert config["num_threads"] == 4
    assert config["use_cuda"] is True
    assert config["dont_peas"] is True
    assert config["cnr_maps"] is True


def test_eddy_config_floor_enforced(tmp_path, monkeypatch):
    """num_threads never falls below 2 even if OMP/override is 1."""
    monkeypatch.setenv("IMAGE_AGENT_EDDY_NUM_THREADS", "1")
    import app.workflows.pipeline as p
    import importlib
    importlib.reload(p)
    dirs = {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    (dirs["bids"] / "sub-01" / "dwi").mkdir(parents=True)
    p._write_qsiprep_eddy_cuda_config(dirs)
    config = json.loads((tmp_path / "eddy_cuda_config.json").read_text(encoding="utf-8"))
    assert config["num_threads"] == 2  # floor kicks in


def test_eddy_config_niter_env_override(tmp_path, monkeypatch):
    """IMAGE_AGENT_DWI_QSIPREP_EDDY_NITER controls eddy iteration count."""
    monkeypatch.setenv("IMAGE_AGENT_DWI_QSIPREP_EDDY_NITER", "5")
    import app.workflows.pipeline as p
    import importlib
    importlib.reload(p)
    dirs = {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    (dirs["bids"] / "sub-01" / "dwi").mkdir(parents=True)
    p._write_qsiprep_eddy_cuda_config(dirs)
    config = json.loads((tmp_path / "eddy_cuda_config.json").read_text(encoding="utf-8"))
    assert config["niter"] == 5


def test_eddy_config_detects_qspace_as_not_shelled(tmp_path, monkeypatch):
    """Many distinct non-b0 b values should not force eddy shell assignment."""
    monkeypatch.delenv("IMAGE_AGENT_DWI_QSIPREP_IS_SHELLED", raising=False)
    import app.workflows.pipeline as p
    import importlib
    importlib.reload(p)
    dirs = {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    dwi_dir = dirs["bids"] / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    (dwi_dir / "sub-01_dwi.bval").write_text(
        "0 200 400 550 750 950 1150 1500 1700 1900 2050 2100 2250 2450 2650 3000",
        encoding="utf-8",
    )
    p._write_qsiprep_eddy_cuda_config(dirs)
    config = json.loads((tmp_path / "eddy_cuda_config.json").read_text(encoding="utf-8"))
    assert config["is_shelled"] is False


def test_eddy_config_is_shelled_env_override(tmp_path, monkeypatch):
    """Operator override can force shelled behavior when needed."""
    monkeypatch.setenv("IMAGE_AGENT_DWI_QSIPREP_IS_SHELLED", "true")
    import app.workflows.pipeline as p
    import importlib
    importlib.reload(p)
    dirs = {"root": tmp_path, "bids": tmp_path / "bids", "output": tmp_path / "output", "work": tmp_path / "work"}
    dwi_dir = dirs["bids"] / "sub-01" / "dwi"
    dwi_dir.mkdir(parents=True)
    (dwi_dir / "sub-01_dwi.bval").write_text("0 200 400 550 750 950", encoding="utf-8")
    p._write_qsiprep_eddy_cuda_config(dirs)
    config = json.loads((tmp_path / "eddy_cuda_config.json").read_text(encoding="utf-8"))
    assert config["is_shelled"] is True


def test_bold_bids_includes_project_t1_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.workflows import pipeline
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-bold-with-t1'}).json()
    t1 = tmp_path / 'sub-001_T1w.nii'
    bold = tmp_path / 'sub-001_task-rest_bold.nii'
    make_nifti(t1, shape=(8, 8, 8))
    make_nifti(bold, shape=(8, 8, 8, 12))

    with t1.open('rb') as f:
        client.post(f"/projects/{project['id']}/upload", files={'file': (t1.name, f, 'application/octet-stream')}).json()
    with bold.open('rb') as f:
        bold_upload = client.post(f"/projects/{project['id']}/upload", files={'file': (bold.name, f, 'application/octet-stream')}).json()

    task = {
        'id': 3,
        'project_id': project['id'],
        'series_id': bold_upload['series']['id'],
        'workflow_type': 'bold_deepprep_validate',
        'log_path': str(tmp_path / 'task.log'),
    }
    dirs = pipeline._build_bids(task, {'metadata_json': json.dumps(bold_upload['series']['metadata']), **bold_upload['series']})

    assert (dirs['bids'] / 'sub-01' / 'anat' / 'sub-01_T1w.nii.gz').exists()
    assert (dirs['bids'] / 'sub-01' / 'func' / 'sub-01_task-rest_bold.nii.gz').exists()
    bold_sidecar = dirs['bids'] / 'sub-01' / 'func' / 'sub-01_task-rest_bold.json'
    assert json.loads(bold_sidecar.read_text(encoding='utf-8'))['RepetitionTime'] == 1.0


def test_bold_fmriprep_xcpd_requires_project_t1_companion(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.schemas import RunRequest
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-bold-requires-t1'}).json()
    bold = tmp_path / 'sub-001_task-rest_bold.nii'
    make_nifti(bold, shape=(8, 8, 8, 12))
    with bold.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (bold.name, f, 'application/octet-stream')}).json()

    with pytest.raises(Exception) as exc:
        task_service.create_series_task(
            uploaded['series']['id'],
            RunRequest(workflow_type='bold_fmriprep_xcpd_report'),
            confirmed_agent_gate=True,
        )

    assert "requires T1/anat data in the same project" in str(exc.value)
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='bold_fmriprep_xcpd_report'").fetchone()[0] == 0


def test_workflow_catalog_exposes_implemented_workflows():
    client = TestClient(app)
    workflows = client.get('/workflows').json()['workflows']
    workflow_types = {w['type'] for w in workflows}
    workflow_labels = {w['type']: w['label'] for w in workflows}

    assert 'dicom_convert_validate' in workflow_types
    assert 'dicom_convert' in workflow_types
    assert 'bold_alff_validate' in workflow_types
    assert 'bold_alff' in workflow_types
    assert 'bold_falff_validate' in workflow_types
    assert 'bold_falff' in workflow_types
    assert 'bold_second_level' in workflow_types
    assert 'bold_second_level_validate' in workflow_types
    assert 'dwi_fast_gpu_dti' in workflow_types
    assert 'dwi_fast_gpu_dti_validate' in workflow_types
    assert workflow_labels['bold_second_level'] == 'BOLD downstream metrics (single subject)'


def test_dwi_validate_reports_missing_eddy_cuda(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_exists', lambda image: (True, 'image ok'))
    monkeypatch.setattr(pipeline, '_docker_image_has_eddy_cuda', lambda image: (False, 'no eddy_cuda* executable found'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    monkeypatch.setattr(pipeline, '_row', lambda sql, params=(): {
        'id': 1,
        'project_id': 1,
        'series_id': 1,
        'workflow_type': 'dwi_qsiprep_validate',
        'log_path': str(tmp_path / 'task.log'),
        'modality': 'DWI',
        'metadata_json': '{}',
    })
    updates = {}
    monkeypatch.setattr(pipeline, '_update', lambda task_id, **values: updates.update(values))
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: None)

    pipeline.run_pipeline_task(1)

    assert updates['status'] == 'failed'
    assert 'eddy_cuda' in updates['error_message']


def test_bold_metric_command_uses_completed_deepprep_outputs(tmp_path, monkeypatch):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')
    project_id = 7
    source_task = 41
    func = tmp_path / 'projects' / str(project_id) / 'derivatives' / str(source_task) / 'output' / 'BOLD' / 'sub-01' / 'func'
    qc = tmp_path / 'projects' / str(project_id) / 'derivatives' / str(source_task) / 'output' / 'QC' / 'sub-01' / 'figures'
    func.mkdir(parents=True)
    qc.mkdir(parents=True)
    preproc = func / 'sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz'
    bold_json = func / 'sub-01_task-rest_space-MNI152NLin6Asym_desc-preproc_bold.json'
    mask = func / 'sub-01_task-rest_space-MNI152NLin6Asym_desc-brain_mask.nii.gz'
    confounds = func / 'sub-01_task-rest_desc-confounds_timeseries.tsv'
    tsnr = qc / 'sub-01_task-rest_desc-tsnr_bold.nii.gz'
    for path in (preproc, mask, tsnr):
        path.write_bytes(b'nifti')
    bold_json.write_text('{"RepetitionTime": 2.0}', encoding='utf-8')
    confounds.write_text('framewise_displacement\tdvars\n0.1\t1.0\n', encoding='utf-8')

    def fake_row(sql, params=()):
        if "workflow_type='bold_deepprep'" in sql:
            return {'id': source_task, 'project_id': project_id}
        return None

    monkeypatch.setattr(pipeline, '_row', fake_row)
    inputs = pipeline._resolve_bold_metric_inputs(
        {'project_id': project_id, 'series_id': 3},
        {'project_id': project_id, 'id': 3},
    )
    cmd = pipeline._commands(
        'bold_alff',
        {'bids': tmp_path / 'bids', 'output': tmp_path / 'out', 'work': tmp_path / 'work', 'root': tmp_path},
        metric_inputs=inputs,
    )[0]

    assert '--preproc-bold' in cmd
    assert str(preproc) in cmd
    assert '--brain-mask' in cmd
    assert str(mask) in cmd
    assert '--confounds' in cmd
    assert str(confounds) in cmd


def test_dwi_fast_gpu_dti_validate_requires_agent_confirmation_for_task_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    from app.schemas import RunRequest
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'run_pipeline_task', lambda task_id, qsiprep_task_id=None: None)
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-fast-dti'}).json()
    dwi = tmp_path / 'sub-001_dwi.nii.gz'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    sidecar = tmp_path / 'sub-001_dwi.json'
    make_nifti(dwi, shape=(8, 8, 8, 3))
    bval.write_text('0 1000 1000\n', encoding='utf-8')
    bvec.write_text('1 0 0\n0 1 0\n0 0 1\n', encoding='utf-8')
    sidecar.write_text('{"PhaseEncodingDirection": "j", "TotalReadoutTime": 0.05}', encoding='utf-8')
    with dwi.open('rb') as f, bval.open('rb') as bval_f, bvec.open('rb') as bvec_f, sidecar.open('rb') as json_f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                'nifti': (dwi.name, f, 'application/gzip'),
                'bval': (bval.name, bval_f, 'text/plain'),
                'bvec': (bvec.name, bvec_f, 'text/plain'),
                'json_sidecar': (sidecar.name, json_f, 'application/json'),
            },
        ).json()
    assert uploaded['series']['metadata']['has_json'] is True
    assert uploaded['series']['metadata']['has_dwi_eddy_metadata'] is True

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 'dwi_fast_gpu_dti_validate'},
    )

    assert rejected.status_code == 403
    assert "/agent/runs" in rejected.json()['detail']
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='dwi_fast_gpu_dti_validate'").fetchone()[0] == 0

    task = task_service.create_series_task(
        uploaded['series']['id'],
        RunRequest(workflow_type='dwi_fast_gpu_dti_validate'),
        confirmed_agent_gate=True,
    )

    assert task['workflow_type'] == 'dwi_fast_gpu_dti_validate'


def test_production_direct_series_run_requires_agent_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-production-direct-run'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 't1_deepprep_anat_report'},
    )

    assert rejected.status_code == 403
    assert "/agent/runs" in rejected.json()['detail']


def test_direct_series_run_requires_agent_confirmation_for_agent_selectable_workflow(tmp_path, monkeypatch):
    monkeypatch.delenv("IMAGE_AGENT_ENV", raising=False)
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-agent-selectable-direct-run'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 't1_deepprep_anat_report'},
    )
    diagnostic = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 't1_deepprep_mock'},
    )

    assert rejected.status_code == 403
    assert "/agent/runs" in rejected.json()['detail']
    assert diagnostic.status_code == 200
    assert diagnostic.json()['workflow_type'] == 't1_deepprep_mock'
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='t1_deepprep_anat_report'").fetchone()[0] == 0


def test_direct_series_run_requires_agent_confirmation_for_fixed_validate_workflow(tmp_path, monkeypatch):
    monkeypatch.delenv("IMAGE_AGENT_ENV", raising=False)
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-fixed-validate-direct-run'}).json()
    dwi = tmp_path / 'sub-001_dwi.nii.gz'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    sidecar = tmp_path / 'sub-001_dwi.json'
    make_nifti(dwi, shape=(8, 8, 8, 3))
    bval.write_text('0 1000 1000\n', encoding='utf-8')
    bvec.write_text('1 0 0\n0 1 0\n0 0 1\n', encoding='utf-8')
    sidecar.write_text(json.dumps({'PhaseEncodingDirection': 'j-', 'TotalReadoutTime': 0.095}), encoding='utf-8')
    with dwi.open('rb') as f, bval.open('rb') as bval_f, bvec.open('rb') as bvec_f, sidecar.open('rb') as json_f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                'nifti': (dwi.name, f, 'application/gzip'),
                'bval': (bval.name, bval_f, 'text/plain'),
                'bvec': (bvec.name, bvec_f, 'text/plain'),
                'json_sidecar': (sidecar.name, json_f, 'application/json'),
            },
        ).json()

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 'dwi_fast_gpu_dti_validate'},
    )

    assert rejected.status_code == 403
    assert "/agent/runs" in rejected.json()['detail']
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='dwi_fast_gpu_dti_validate'").fetchone()[0] == 0


def test_direct_series_run_rejects_runtime_alias_without_registered_workflow_type(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-runtime-alias-spoof'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={
            'workflow_type': 'T1 DeepPrep anatomical processing, QC, and report',
            'runtime_workflow_type': 't1_deepprep',
        },
    )

    assert rejected.status_code == 400
    assert 'Unknown workflow_type' in rejected.json()['detail']
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_production_create_series_task_blocks_incubation_debug_workflow_even_with_agent_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGE_AGENT_ENV", "production")
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.schemas import RunRequest
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-production-debug-block'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()

    with pytest.raises(Exception) as excinfo:
        task_service.create_series_task(
            uploaded['series']['id'],
            RunRequest(workflow_type='t1_deepprep_mock'),
        )

    assert getattr(excinfo.value, "status_code", None) == 403
    assert "Incubation" in str(getattr(excinfo.value, "detail", ""))


def test_dwi_fast_gpu_dti_rejects_missing_json_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.schemas import RunRequest
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-fast-dti-no-json'}).json()
    dwi = tmp_path / 'sub-001_dwi.nii.gz'
    bval = tmp_path / 'sub-001_dwi.bval'
    bvec = tmp_path / 'sub-001_dwi.bvec'
    make_nifti(dwi, shape=(8, 8, 8, 3))
    bval.write_text('0 1000 1000\n', encoding='utf-8')
    bvec.write_text('1 0 0\n0 1 0\n0 0 1\n', encoding='utf-8')
    with dwi.open('rb') as f, bval.open('rb') as bval_f, bvec.open('rb') as bvec_f:
        uploaded = client.post(
            f"/projects/{project['id']}/upload-dwi",
            files={
                'nifti': (dwi.name, f, 'application/gzip'),
                'bval': (bval.name, bval_f, 'text/plain'),
                'bvec': (bvec.name, bvec_f, 'text/plain'),
            },
        ).json()

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 'dwi_fast_gpu_dti_validate'},
    )

    assert rejected.status_code == 403
    assert '/agent/runs' in rejected.json()['detail']

    with pytest.raises(Exception) as excinfo:
        task_service.create_series_task(
            uploaded['series']['id'],
            RunRequest(workflow_type='dwi_fast_gpu_dti_validate'),
            confirmed_agent_gate=True,
        )

    assert getattr(excinfo.value, 'status_code', None) == 400
    assert 'JSON sidecar' in str(getattr(excinfo.value, 'detail', ''))


def test_dwi_fast_gpu_dti_validate_checks_lightweight_toolbox_not_full_qsiprep(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline.dwi_fast_dti, "check_runtime", lambda: (True, "FSL eddy_cuda ok\nfull_qsiprep_run: false\nmax_runtime_sec: 2100"))
    monkeypatch.setattr(pipeline, "_build_bids", lambda task, series: {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    })
    monkeypatch.setattr(pipeline, "_row", lambda sql, params=(): {
        "id": 8,
        "project_id": 1,
        "series_id": 1,
        "workflow_type": "dwi_fast_gpu_dti_validate",
        "log_path": str(tmp_path / "task.log"),
        "modality": "DWI",
        "metadata_json": "{}",
    })
    monkeypatch.setattr(pipeline.dwi_fast_dti, "validate_inputs", lambda dirs: None)
    monkeypatch.setattr(pipeline, "_update", lambda *args, **kwargs: None)
    outputs = []
    monkeypatch.setattr(pipeline, "_insert_output", lambda *args, **kwargs: outputs.append(args))

    pipeline.run_pipeline_task(8)

    metadata = outputs[-1][3]
    command_text = " ".join(str(part) for cmd in metadata["commands"] for part in cmd)
    assert "full_qsiprep_run: false" in metadata["inspect_tail"]
    assert "max_runtime_sec: 2100" in metadata["inspect_tail"]
    assert "qsiprep /data /out participant" not in command_text
    assert "--eddy-config" not in command_text
    assert "app.workflows.dwi_fast_dti run" in command_text


def test_pipeline_runner_uses_runtime_workflow_type_when_task_keeps_canonical_id(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(pipeline, "_isolate_stale_task_workspace", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pipeline,
        "_build_bids",
        lambda task, series: {
            "root": tmp_path,
            "bids": tmp_path / "bids",
            "output": tmp_path / "output",
            "work": tmp_path / "work",
        },
    )
    monkeypatch.setattr(pipeline, "_docker_image_exists", lambda image: (True, "deepprep image ok"))
    monkeypatch.setattr(pipeline, "_insert_output", lambda *args, **kwargs: None)
    updates = []
    monkeypatch.setattr(pipeline, "_update", lambda task_id, **values: updates.append(values))

    def fake_row(sql, params=()):
        if "FROM tasks" in sql:
            return {
                "id": 77,
                "project_id": 1,
                "series_id": 11,
                "workflow_type": "t1_deepprep_anat_report",
                "runtime_workflow_type": "t1_deepprep_validate",
                "log_path": str(tmp_path / "task.log"),
                "qsiprep_task_id": None,
            }
        if "FROM imaging_series" in sql:
            return {"id": 11, "project_id": 1, "modality": "T1", "metadata_json": "{}"}
        return None

    monkeypatch.setattr(pipeline, "_row", fake_row)

    pipeline.run_pipeline_task(77)

    assert any(item.get("status") == "completed" for item in updates)
    log_text = (tmp_path / "task.log").read_text(encoding="utf-8")
    manifest_line = next(line for line in log_text.splitlines() if "RUNTIME_MANIFEST " in line)
    manifest = json.loads(manifest_line.split("RUNTIME_MANIFEST ", 1)[1])
    assert manifest["workflow_type"] == "t1_deepprep_validate"
    assert manifest["runtime_workflow"] == "t1_deepprep"


def test_task_result_summary_endpoint_returns_frontend_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.db.database import now_iso
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-result-summary'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()
    summary_dir = tmp_path / 'projects' / str(project['id']) / 'derivatives' / '99' / 'output' / 'summary'
    summary_dir.mkdir(parents=True)
    summary = summary_dir / 't1_result_summary.json'
    summary.write_text(
        json.dumps({
            'contract_version': '1.0',
            'task_id': 99,
            'workflow_type': 't1_deepprep',
            'modality': 'T1',
            'spaces': ['T1w', 'MNI152'],
            'feature_groups': ['segmentation_volumes'],
            'outputs': {},
            'provenance': {},
        }),
        encoding='utf-8',
    )
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (99, project['id'], uploaded['series']['id'], 't1_deepprep', 'completed', 100, str(tmp_path / 'task.log'), now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (99, 'json', str(summary), None, json.dumps({'kind': 'result_summary'}), now_iso()),
        )

    result = client.get('/tasks/99/result-summary')

    assert result.status_code == 200
    payload = result.json()
    assert payload['project_id'] == project['id']
    assert payload['workflow_type'] == 't1_deepprep'
    assert payload['workflow_metadata']['workflow_type'] == 't1_deepprep_anat_report'
    assert payload['workflow_metadata']['runtime_workflow_type'] == 't1_deepprep'
    assert payload['workflow_metadata']['display_name'] == 'T1 DeepPrep anatomical processing, QC, and report'
    assert payload['workflow_metadata']['is_report_only'] is False
    assert payload['spaces'] == ['T1w', 'MNI152']
    assert 'summary_path' not in payload


def test_task_outputs_endpoint_returns_frontend_safe_artifact_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.db.database import now_iso
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-output-contract'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()
    output_dir = tmp_path / 'projects' / str(project['id']) / 'derivatives' / '88' / 'output'
    table = output_dir / 'tables' / 'regions.tsv'
    table.parent.mkdir(parents=True)
    table.write_text('region\tvolume\nctx\t12\n', encoding='utf-8')
    preview = output_dir / 'preview.png'
    preview.write_bytes(b'\x89PNG\r\n\x1a\n')
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (88, project['id'], uploaded['series']['id'], 't1_deepprep', 'completed', 100, str(tmp_path / 'task.log'), now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (
                88,
                'table',
                str(table),
                str(preview),
                json.dumps({
                    'kind': 'qc_table',
                    'relative_path': 'tables/regions.tsv',
                    'content_type': 'text/tab-separated-values',
                    'path': str(table),
                    'preview_path': str(preview),
                }),
                now_iso(),
            ),
        )

    response = client.get('/tasks/88/outputs')

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert len(payload) == 1
    assert payload[0]['relative_path'] == 'tables/regions.tsv'
    assert payload[0]['download_url'] == '/tasks/88/artifacts/tables/regions.tsv'
    assert payload[0]['content_type'] == 'text/tab-separated-values'
    assert payload[0]['size_bytes'] == table.stat().st_size
    assert payload[0]['metadata']['kind'] == 'qc_table'
    assert 'path' not in payload[0]
    assert 'preview_path' not in payload[0]
    assert str(table) not in serialized
    assert str(preview) not in serialized


def test_t1_deepprep_pipeline_registers_real_freesurfer_stats_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.db.database import now_iso
    from app.workflows import pipeline
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-t1-real-summary'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()

    log_path = tmp_path / 'task.log'
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (120, project['id'], uploaded['series']['id'], 't1_deepprep', 'queued', 0, str(log_path), now_iso()),
        )

    def fake_run_command(task, cmd, task_log_path):
        out = tmp_path / 'projects' / str(project['id']) / 'derivatives' / '120' / 'output'
        stats = out / 'Recon' / 'sub-01' / 'stats'
        stats.mkdir(parents=True)
        mri = out / 'Recon' / 'sub-01' / 'mri'
        (mri / 'transforms').mkdir(parents=True)
        (mri / 'aparc+aseg.mgz').write_bytes(b'mgz')
        (mri / 'transforms' / 'talairach.xfm').write_text('xfm', encoding='utf-8')
        (stats / 'brainvol.stats').write_text(
            '# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 938722.000000000000, mm^3\n',
            encoding='utf-8',
        )
        aparc = '\n'.join([
            '# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd',
            'bankssts 1227 925 1890 2.133 0.453 0.104 0.021 5 1.1',
        ])
        (stats / 'lh.aparc.stats').write_text(aparc, encoding='utf-8')
        (stats / 'rh.aparc.stats').write_text(aparc, encoding='utf-8')

    monkeypatch.setattr(pipeline, '_run_command', fake_run_command)

    pipeline.run_pipeline_task(120)

    result = client.get('/tasks/120/result-summary')
    assert result.status_code == 200
    payload = result.json()
    assert payload['provenance']['placeholder_outputs'] is False
    assert payload['provenance']['extraction_status'] == 'real_deepprep_freesurfer_stats'
    assert payload['outputs']['tables'][0]['name'] == 't1_brain_measures'
    assert any(item['name'] == 't1_aparc_aseg' for item in payload['outputs']['maps'])
    assert any(item['name'] == 'talairach_xfm' for item in payload['outputs']['transforms'])


def test_dwi_validate_accepts_versioned_eddy_cuda(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_exists', lambda image: (True, 'image ok'))
    monkeypatch.setattr(pipeline, '_docker_image_has_eddy_cuda', lambda image: (True, '/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    monkeypatch.setattr(pipeline, '_row', lambda sql, params=(): {
        'id': 5,
        'project_id': 1,
        'series_id': 1,
        'workflow_type': 'dwi_qsiprep_validate',
        'log_path': str(tmp_path / 'task.log'),
        'modality': 'DWI',
        'metadata_json': '{}',
    })
    outputs = []
    updates = {}
    monkeypatch.setattr(pipeline, '_update', lambda task_id, **values: updates.update(values))
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: outputs.append(args))

    pipeline.run_pipeline_task(5)

    assert updates['status'] == 'completed'
    metadata = outputs[0][3]
    assert 'eddy_cuda11.0' in metadata['inspect_tail']


def test_dwi_qsi_full_validate_accepts_versioned_eddy_cuda(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_exists', lambda image: (True, 'image ok'))
    monkeypatch.setattr(pipeline, '_docker_image_has_eddy_cuda', lambda image: (True, '/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0'))
    monkeypatch.setattr(pipeline, '_docker_gpu_visible', lambda image: (True, 'nvidia devices found'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    monkeypatch.setattr(pipeline, '_row', lambda sql, params=(): {
        'id': 6,
        'project_id': 1,
        'series_id': 1,
        'workflow_type': 'dwi_qsi_full_validate',
        'log_path': str(tmp_path / 'task.log'),
        'modality': 'DWI',
        'metadata_json': '{}',
    })
    outputs = []
    monkeypatch.setattr(pipeline, '_update', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: outputs.append(args))

    pipeline.run_pipeline_task(6)

    metadata = outputs[0][3]
    assert 'QSIRecon GPU visible with Docker --gpus all: True' in metadata['inspect_tail']
    assert 'eddy_cuda11.0' in metadata['inspect_tail']


def test_qsirecon_validate_records_gpu_visibility(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_exists', lambda image: (True, 'image ok'))
    monkeypatch.setattr(pipeline, '_docker_gpu_visible', lambda image: (True, 'gpu visible'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    rows = {
        'task': {
            'id': 2,
            'project_id': 1,
            'series_id': 1,
            'workflow_type': 'dwi_qsirecon_validate',
            'log_path': str(tmp_path / 'task.log'),
            'qsiprep_task_id': 11,
        },
        'series': {
            'id': 1,
            'project_id': 1,
            'modality': 'DWI',
            'metadata_json': '{}',
        },
        'qsiprep': {
            'id': 11,
            'project_id': 1,
        },
    }

    def fake_row(sql, params=()):
        if 'FROM tasks WHERE id=?' in sql and params == (2,):
            return rows['task']
        if 'FROM imaging_series WHERE id=?' in sql:
            return rows['series']
        if 'FROM tasks WHERE id=?' in sql and params == (11,):
            return rows['qsiprep']
        return rows['task']

    outputs = []
    monkeypatch.setattr(pipeline, '_row', fake_row)
    monkeypatch.setattr(pipeline, '_update', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: outputs.append(args))

    pipeline.run_pipeline_task(2)

    metadata = outputs[0][3]
    assert 'QSIRecon GPU visible with Docker --gpus all: True' in metadata['inspect_tail']
    assert metadata['qsirecon_profile']['profile'] == 'dki'
    assert metadata['qsirecon_profile']['recon_spec'] == 'dipy_dki'
    assert metadata['legacy_snapshot_path'].endswith('qsirecon_legacy_dipy_dki_command.json')


def test_qsirecon_defaults_to_dipy_dki_with_notrack(monkeypatch, tmp_path):
    import importlib
    import app.core.config as app_config
    from app.workflows import pipeline

    monkeypatch.delenv("IMAGE_AGENT_QSIRECON_PROFILE", raising=False)
    importlib.reload(app_config)
    importlib.reload(pipeline)
    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }

    cmd = pipeline._commands("dwi_qsirecon", dirs)[0]

    assert "--recon-spec" in cmd
    assert cmd[cmd.index("--recon-spec") + 1] == "dipy_dki"
    assert "--notrack" in cmd
    assert "--skip-odf-reports" in cmd


def test_qsirecon_tractography_profile_switches_recon_spec(monkeypatch, tmp_path):
    import importlib
    import app.core.config as app_config
    from app.workflows import pipeline

    monkeypatch.setenv("IMAGE_AGENT_QSIRECON_PROFILE", "tractography")
    importlib.reload(app_config)
    importlib.reload(pipeline)
    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }

    cmd = pipeline._commands("dwi_qsirecon", dirs)[0]

    assert "--recon-spec" in cmd
    assert cmd[cmd.index("--recon-spec") + 1] == "mrtrix_multishell_msmt_noACT"
    assert "--notrack" not in cmd
    assert "--skip-odf-reports" not in cmd


def test_qsirecon_invalid_profile_fails_fast(monkeypatch, tmp_path):
    import importlib
    import app.core.config as app_config
    from app.workflows import pipeline

    monkeypatch.setenv("IMAGE_AGENT_QSIRECON_PROFILE", "typo_profile")
    importlib.reload(app_config)
    importlib.reload(pipeline)
    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }

    with pytest.raises(RuntimeError, match="Unsupported IMAGE_AGENT_QSIRECON_PROFILE"):
        pipeline._commands("dwi_qsirecon", dirs)

    monkeypatch.delenv("IMAGE_AGENT_QSIRECON_PROFILE", raising=False)
    importlib.reload(app_config)
    importlib.reload(pipeline)


def test_qsirecon_legacy_snapshot_is_written(tmp_path):
    from app.workflows import pipeline

    snapshot = pipeline._write_qsirecon_legacy_snapshot(tmp_path)

    assert snapshot.exists()
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert payload["recon_spec"] == "dipy_dki"
    assert "--notrack" in payload["extra_flags"]
    assert payload["image"] == "pennlinc/qsirecon:26.0.0"
    assert payload["input_type"] == "qsiprep"
    assert payload["command_template"][0:4] == ["docker", "run", "--rm", "--gpus"]
    assert "dipy_dki" in payload["command_template"]


def test_pipeline_runtime_images_are_version_pinned():
    from app.workflows import dwi_fast_dti, pipeline

    runtime_images = {
        **pipeline.IMAGES,
        "dwi_fast_gpu_dti_mrtrix": dwi_fast_dti.MRTRIX_IMAGE,
    }

    assert runtime_images["t1_deepprep"] == "pbfslab/deepprep:25.1.0"
    assert runtime_images["dwi_qsiprep"] == "pennlinc/qsiprep:26.0.0"
    assert runtime_images["dwi_qsirecon"] == "pennlinc/qsirecon:26.0.0"
    assert runtime_images["bold_fmriprep"] == "nipreps/fmriprep:25.2.5"
    assert runtime_images["bold_fmriprep_xcpd_report_xcpd"] == "pennlinc/xcp_d:26.0.2"
    for name, image in runtime_images.items():
        assert ":latest" not in image, f"{name} must use a fixed image tag, got {image}"


def test_pipeline_runtime_manifest_records_deployment_local_execution_and_versions(tmp_path):
    from app.workflows import pipeline

    dirs = {"bids": tmp_path / "bids", "output": tmp_path / "out", "work": tmp_path / "work"}
    cmd = pipeline._commands("t1_deepprep", dirs)[0]
    manifest = pipeline._runtime_manifest(
        workflow_type="t1_deepprep",
        workflow="t1_deepprep",
        commands=[cmd],
        image=pipeline.IMAGES["t1_deepprep"],
    )

    assert manifest["execution_scope"] == {
        "workflow_tool_execution": "deployment_server_local",
        "docker_runtime_host": "api_server",
        "external_worker_server_required": False,
    }
    assert manifest["version_lock"]["images"]["t1_deepprep"] == "pbfslab/deepprep:25.1.0"
    assert manifest["version_lock"]["floating_tags_allowed"] is False
    assert ":latest" not in json.dumps(manifest)
    assert manifest["commands"] == [cmd]


def test_dwi_qsi_full_validate_fails_without_eddy_cuda(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_exists', lambda image: (True, 'image ok'))
    monkeypatch.setattr(pipeline, '_docker_image_has_eddy_cuda', lambda image: (False, 'missing eddy_cuda*'))
    monkeypatch.setattr(pipeline, '_docker_gpu_visible', lambda image: (True, 'gpu visible'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    monkeypatch.setattr(pipeline, '_row', lambda sql, params=(): {
        'id': 3,
        'project_id': 1,
        'series_id': 1,
        'workflow_type': 'dwi_qsi_full_validate',
        'log_path': str(tmp_path / 'task.log'),
        'modality': 'DWI',
        'metadata_json': '{}',
    })
    updates = {}
    monkeypatch.setattr(pipeline, '_update', lambda task_id, **values: updates.update(values))
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: None)

    pipeline.run_pipeline_task(3)

    assert updates['status'] == 'failed'
    assert 'eddy_cuda' in updates['error_message']


def test_dwi_qsi_full_validate_records_qsirecon_gpu_visibility(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_exists', lambda image: (True, 'image ok'))
    monkeypatch.setattr(pipeline, '_docker_image_has_eddy_cuda', lambda image: (True, '/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0'))
    monkeypatch.setattr(pipeline, '_docker_gpu_visible', lambda image: (True, 'nvidia devices found'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    monkeypatch.setattr(pipeline, '_row', lambda sql, params=(): {
        'id': 4,
        'project_id': 1,
        'series_id': 1,
        'workflow_type': 'dwi_qsi_full_validate',
        'log_path': str(tmp_path / 'task.log'),
        'modality': 'DWI',
        'metadata_json': '{}',
    })
    outputs = []
    monkeypatch.setattr(pipeline, '_update', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: outputs.append(args))

    pipeline.run_pipeline_task(4)

    metadata = outputs[0][3]
    assert 'QSIRecon GPU visible with Docker --gpus all: True' in metadata['inspect_tail']
    assert 'eddy_cuda11.0' in metadata['inspect_tail']


def test_dwi_qsirecon_real_fails_without_gpu(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_gpu_visible', lambda image: (False, 'no nvidia devices'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    rows = {
        'task': {
            'id': 10,
            'project_id': 1,
            'series_id': 1,
            'workflow_type': 'dwi_qsirecon',
            'log_path': str(tmp_path / 'task.log'),
            'qsiprep_task_id': 9,
        },
        'series': {
            'id': 1,
            'project_id': 1,
            'modality': 'DWI',
            'metadata_json': '{}',
        },
        'qsiprep': {
            'id': 9,
            'project_id': 1,
        },
    }

    def fake_row(sql, params=()):
        if 'FROM tasks WHERE id=?' in sql and params == (10,):
            return rows['task']
        if 'FROM imaging_series WHERE id=?' in sql:
            return rows['series']
        if 'FROM tasks WHERE id=?' in sql and params == (9,):
            return rows['qsiprep']
        return rows['task']

    updates = {}
    monkeypatch.setattr(pipeline, '_row', fake_row)
    monkeypatch.setattr(pipeline, '_update', lambda task_id, **values: updates.update(values))
    monkeypatch.setattr(pipeline, '_append', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: None)

    pipeline.run_pipeline_task(10)

    assert updates['status'] == 'failed'
    assert 'QSIRecon' in updates['error_message']
    assert 'GPU' in updates['error_message']


def test_dwi_qsi_full_real_fails_when_qsirecon_gpu_not_visible(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, '_docker_image_has_eddy_cuda', lambda image: (True, '/app/.pixi/envs/qsiprep/bin/eddy_cuda11.0'))
    monkeypatch.setattr(pipeline, '_docker_gpu_visible', lambda image: (False, 'no nvidia devices'))
    monkeypatch.setattr(pipeline, '_build_bids', lambda task, series: {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    })
    monkeypatch.setattr(pipeline, '_row', lambda sql, params=(): {
        'id': 11,
        'project_id': 1,
        'series_id': 1,
        'workflow_type': 'dwi_qsi_full',
        'log_path': str(tmp_path / 'task.log'),
        'modality': 'DWI',
        'metadata_json': '{}',
    })
    updates = {}
    monkeypatch.setattr(pipeline, '_update', lambda task_id, **values: updates.update(values))
    monkeypatch.setattr(pipeline, '_append', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, '_insert_output', lambda *args, **kwargs: None)

    pipeline.run_pipeline_task(11)

    assert updates['status'] == 'failed'
    assert 'QSIRecon' in updates['error_message']
    assert 'GPU' in updates['error_message']


def test_full_t1_mock_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.workflows import deepprep
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(deepprep, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    assert client.get('/health').json()['status'] == 'ok'
    client.post('/auth/login', json={'username': 'demo', 'password': 'demo'}).raise_for_status()
    project = client.post('/projects', json={'name': 'P1'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()
    assert uploaded['series']['modality'] == 'T1'
    task = client.post(f"/series/{uploaded['series']['id']}/run", json={'workflow_type': 't1_deepprep_mock'}).json()
    for _ in range(20):
        current = client.get(f"/tasks/{task['id']}").json()
        if current['status'] == 'completed':
            break
        time.sleep(0.2)
    assert current['status'] == 'completed'
    outputs = client.get(f"/tasks/{task['id']}/outputs").json()
    assert outputs
    assert all(item['download_url'].startswith(f"/tasks/{task['id']}/artifacts/") for item in outputs)
    assert 'log_path' not in json.dumps(outputs)
    result_summary = client.get(f"/tasks/{task['id']}/result-summary").json()
    assert result_summary['task_id'] == task['id']
    assert result_summary['workflow_type'] in {'t1_deepprep', 't1_deepprep_mock'}
    assert result_summary['outputs']
    assert 'summary_path' not in result_summary
    manifest = client.get(f"/tasks/{task['id']}/artifact-manifest").json()
    assert manifest['artifacts']
    assert manifest['result_summary']['available'] is True
    assert any(
        artifact['download_url'].startswith(f"/tasks/{task['id']}/artifacts/")
        for artifact in manifest['artifacts']
    )
    assert 'completed' in client.get(f"/tasks/{task['id']}/logs").json()['text'].lower()
    chat = client.post('/chat', json={'project_id': project['id'], 'message': 'task status'}).json()
    assert 'Tasks:' in chat['reply']


def test_task_status_responses_omit_backend_log_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.services import task_service
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-task-public'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()

    created = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 't1_deepprep_mock'},
    ).json()
    detail = client.get(f"/tasks/{created['id']}").json()
    task_list = client.get(f"/projects/{project['id']}/tasks").json()

    serialized = json.dumps({'created': created, 'detail': detail, 'task_list': task_list})
    assert 'log_path' not in created
    assert 'log_path' not in detail
    assert all('log_path' not in task for task in task_list)
    assert str(tmp_path / 'projects') not in serialized
    with database.connect() as conn:
        raw = conn.execute("SELECT log_path FROM tasks WHERE id=?", (created['id'],)).fetchone()
    assert raw['log_path'].endswith(f"{created['id']}.log")


def test_task_logs_redact_secrets_and_backend_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-logs'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        series = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()['series']
    log_path = tmp_path / 'projects' / str(project['id']) / 'logs' / '77.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        'OPENAI_API_KEY=sk-test-secret failed at C:/Users/A/private/patient-001\n'
        'IMAGE_AGENT_SUDO_PASSWORD=super-secret\n'
        'processing continued\n',
        encoding='utf-8',
    )
    remote_log = tmp_path / 'projects' / str(project['id']) / 'derivatives' / '77' / 'output' / 'logs' / 'fmriprep.log'
    remote_log.parent.mkdir(parents=True, exist_ok=True)
    remote_log.write_text(
        'container TOKEN=remote-secret wrote /home/yyf/project/image_agent/private-output\n'
        'remote qc continued\n',
        encoding='utf-8',
    )
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            'INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)',
            (77, project['id'], series['id'], 't1_deepprep_mock', 'running', 20, str(log_path), now),
        )

    payload = client.get('/tasks/77/logs').json()
    serialized = json.dumps(payload)
    assert 'processing continued' in payload['text']
    assert 'sk-test-secret' not in serialized
    assert 'super-secret' not in serialized
    assert 'patient-001' not in serialized
    assert 'C:/Users/A/private' not in serialized
    assert 'remote-secret' not in serialized
    assert '/home/yyf/project/image_agent' not in serialized
    assert 'log_paths' not in payload
    assert payload['remote_logs'][0]['name'] == 'fmriprep.log'
    assert 'remote qc continued' in payload['remote_logs'][0]['tail']
    assert 'path' not in payload['remote_logs'][0]

    events_payload = client.get('/tasks/77/events').json()
    events_serialized = json.dumps(events_payload)
    assert events_payload['status'] == 'ok'
    assert events_payload['task']['id'] == 77
    assert events_payload['task']['status'] == 'running'
    assert 'log_path' not in events_payload['task']
    assert any(event['type'] == 'task.status' and event['status'] == 'running' for event in events_payload['events'])
    assert any(event['type'] == 'task.remote_log' and event['source_stage'] == 'fmriprep' for event in events_payload['events'])
    assert 'processing continued' in events_payload['main_log']['tail']
    assert events_payload['remote_logs'][0]['name'] == 'fmriprep.log'
    assert 'remote qc continued' in events_payload['remote_logs'][0]['tail']
    assert 'sk-test-secret' not in events_serialized
    assert 'super-secret' not in events_serialized
    assert 'remote-secret' not in events_serialized
    assert 'C:/Users/A/private' not in events_serialized
    assert '/home/yyf/project/image_agent' not in events_serialized
    assert 'log_path' not in events_serialized


def test_task_observe_repair_endpoint_is_read_only_and_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-observe-repair'}).json()
    nii = tmp_path / 'sub-001_T1w.nii.gz'
    make_nifti(nii)
    with nii.open('rb') as f:
        series = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()['series']
    log_path = tmp_path / 'projects' / str(project['id']) / 'logs' / '118.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        'OPENAI_API_KEY=sk-observe-secret failed at C:/Users/A/private/patient-118\n',
        encoding='utf-8',
    )
    remote_log = tmp_path / 'projects' / str(project['id']) / 'derivatives' / '118' / 'output' / 'logs' / 'fmriprep.log'
    remote_log.parent.mkdir(parents=True, exist_ok=True)
    remote_log.write_text(
        'remote TOKEN=repair-secret wrote /home/yyf/project/image_agent/private\n',
        encoding='utf-8',
    )
    now = database.now_iso()
    with database.connect() as conn:
        conn.execute(
            'INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)',
            (118, project['id'], series['id'], 't1_deepprep_mock', 'failed', 20, str(log_path), now),
        )
        conn.execute(
            'INSERT INTO outputs(task_id, output_type, path, metadata_json, created_at) VALUES(?,?,?,?,?)',
            (118, 'json', str(tmp_path / 'missing_result_summary.json'), '{"kind":"result_summary"}', now),
        )
        before_tasks = conn.execute('SELECT COUNT(*) AS count FROM tasks').fetchone()['count']
        before_outputs = conn.execute('SELECT COUNT(*) AS count FROM outputs').fetchone()['count']

    response = client.get('/tasks/118/observe-repair')

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert payload['status'] == 'ok'
    assert payload['policy'] == 'read_only_observe_repair'
    assert payload['task']['id'] == 118
    assert payload['task']['status'] == 'failed'
    assert any(item['kind'] == 'failed_task_repair_plan' for item in payload['repair_suggestions'])
    assert any(item['kind'] == 'result_summary_repair_plan' for item in payload['repair_suggestions'])
    assert payload['auto_rerun_allowed'] is False
    assert payload['production_task_created'] is False
    assert payload['requires_preflight_before_retry'] is True
    assert payload['requires_human_confirmation_before_retry'] is True
    assert any(event['type'] == 'task.status' and event['status'] == 'failed' for event in payload['events'])
    assert 'failed at' in payload['main_log']['tail']
    assert payload['remote_logs'][0]['name'] == 'fmriprep.log'
    assert 'log_path' not in serialized
    assert 'path' not in payload['remote_logs'][0]
    assert 'sk-observe-secret' not in serialized
    assert 'repair-secret' not in serialized
    assert 'patient-118' not in serialized
    assert 'C:/Users/A/private' not in serialized
    assert '/home/yyf/project/image_agent' not in serialized
    with database.connect() as conn:
        after_tasks = conn.execute('SELECT COUNT(*) AS count FROM tasks').fetchone()['count']
        after_outputs = conn.execute('SELECT COUNT(*) AS count FROM outputs').fetchone()['count']
        task = conn.execute('SELECT status, progress, log_path FROM tasks WHERE id=?', (118,)).fetchone()
    assert after_tasks == before_tasks
    assert after_outputs == before_outputs
    assert task['status'] == 'failed'
    assert task['progress'] == 20
    assert task['log_path'] == str(log_path)


def test_bold_deepprep_validate_allowed_for_fmri(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    from app.schemas import RunRequest
    from app.services import task_service
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'run_pipeline_task', lambda task_id, qsiprep_task_id=None: None)
    monkeypatch.setattr(task_service, 'submit_background', lambda *args, **kwargs: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-bold'}).json()
    nii = tmp_path / 'sub-001_task-rest_bold.nii.gz'
    make_nifti(nii, shape=(64, 64, 32, 100))
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()
    assert uploaded['series']['modality'] == 'BOLD'

    rejected = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 'bold_deepprep_validate'},
    )
    assert rejected.status_code == 403
    assert "/agent/runs" in rejected.json()['detail']
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks WHERE workflow_type='bold_deepprep_validate'").fetchone()[0] == 0

    task = task_service.create_series_task(
        uploaded['series']['id'],
        RunRequest(workflow_type='bold_deepprep_validate'),
        confirmed_agent_gate=True,
    )

    assert task['workflow_type'] == 'bold_deepprep_validate'


def test_bold_report_routes_dispatch_through_result_service(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.services import result_service

    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    database.init_db()

    calls = []

    def fake_group_analysis(**kwargs):
        calls.append(('group', kwargs))
        return {'kind': 'group', 'project_id': kwargs['project_id'], 'seed_query': kwargs['seed_query']}

    def fake_descriptive_review(**kwargs):
        calls.append(('descriptive', kwargs))
        return {'kind': 'descriptive', 'project_id': kwargs['project_id'], 'seed_preset': kwargs['seed_preset']}

    monkeypatch.setattr(result_service, 'run_group_analysis', fake_group_analysis)
    monkeypatch.setattr(result_service, 'run_descriptive_review', fake_descriptive_review)

    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-bold-report-service'}).json()

    missing = client.post(
        '/projects/999/bold/group-analysis',
        json={'group_a_task_ids': [1, 2], 'group_b_task_ids': [3, 4], 'seed_query': 'PCC_DMN'},
    )
    assert missing.status_code == 404

    group = client.post(
        f"/projects/{project['id']}/bold/group-analysis",
        json={'group_a_task_ids': [1, 2], 'group_b_task_ids': [3, 4], 'seed_query': 'PCC_DMN'},
    )
    assert group.status_code == 200
    assert group.json()['kind'] == 'group'

    descriptive = client.post(
        f"/projects/{project['id']}/bold/descriptive-review",
        json={'deepprep_task_ids': [7], 'seed_preset': 'PCC_DMN'},
    )
    assert descriptive.status_code == 200
    assert descriptive.json()['kind'] == 'descriptive'

    assert calls == [
        (
            'group',
            {
                'project_id': project['id'],
                'group_a_tasks': [1, 2],
                'group_b_tasks': [3, 4],
                'seed_query': 'PCC_DMN',
                'label_a': 'group_a',
                'label_b': 'group_b',
            },
        ),
        (
            'descriptive',
            {
                'project_id': project['id'],
                'deepprep_task_ids': [7],
                'seed_preset': 'PCC_DMN',
            },
        ),
    ]


def test_mixed_dataset_ingest_inventory_and_bids(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.imaging import ingest
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(ingest, 'PROJECTS_ROOT', tmp_path / 'projects')

    database.init_db()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name, shape in {
            'subj1/anat/subj1_T1w.nii.gz': (8, 8, 8),
            'subj1/func/subj1_task-rest_bold.nii.gz': (8, 8, 8, 12),
            'subj1/dwi/subj1_dwi.nii.gz': (8, 8, 8, 3),
            'subj1/anat/subj1_FLAIR.nii.gz': (8, 8, 8),
        }.items():
            tmp = tmp_path / Path(name).name
            make_nifti(tmp, shape=shape)
            z.writestr(name, tmp.read_bytes())
        z.writestr('subj1/dwi/subj1_dwi.bval', '0 1000 1000\n')
        z.writestr('subj1/dwi/subj1_dwi.bvec', '1 0 0\n0 1 0\n0 0 1\n')
        z.writestr('subj1/dicom/IM0001.dcm', b'\0' * 128 + b'DICM' + b'fake')

    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-mixed'}).json()
    session = client.post(
        f"/projects/{project['id']}/datasets/upload-session",
        json={'label': 'mixed.zip', 'source_type': 'folder_or_archive'},
    ).json()
    result = client.post(
        f"/projects/{project['id']}/datasets/{session['id']}/ingest",
        files={'archive': ('mixed.zip', buf.getvalue(), 'application/zip')},
    ).json()
    inventory = result['inventory']
    serialized_inventory = json.dumps(inventory)
    assert inventory['dicom']['found_files'] == 1
    assert inventory['bids_dataset_root'] == 'bids/rawdata'
    assert str(tmp_path / 'projects') not in serialized_inventory
    assert inventory['post_conversion_counts']['by_modality']['T1'] >= 1
    assert inventory['post_conversion_counts']['by_modality']['DWI'] >= 1
    assert inventory['post_conversion_counts']['by_modality']['BOLD'] >= 1
    assert any(x['sequence'] == 'T2_FLAIR' for x in inventory['recognized_unsupported_sequences'])
    assert all('bids/rawdata/' in x['bids_path'] for x in inventory['series'])
    by_modality = {item['modality']: item for item in inventory['series']}
    assert by_modality['T1']['workflow_eligibility']['primary_recommendation']['workflow_type'] == 't1_deepprep_anat_report'
    assert by_modality['BOLD']['workflow_eligibility']['primary_recommendation']['workflow_type'] == 'bold_fmriprep_xcpd_report'
    assert by_modality['DWI']['workflow_eligibility']['production_task_created'] is False
    assert not by_modality['DWI']['workflow_eligibility']['runnable_workflows']
    dwi_blockers = {
        blocked['workflow_type']: blocked['blocking_reasons']
        for blocked in by_modality['DWI']['workflow_eligibility']['blocked_workflows']
    }
    assert 'dwi_fast_gpu_dti' in dwi_blockers
    assert any('JSON sidecar' in reason for reason in dwi_blockers['dwi_fast_gpu_dti'])
    flair_eligibility = by_modality['FLAIR']['workflow_eligibility']
    assert flair_eligibility['primary_recommendation'] is None
    assert not flair_eligibility['runnable_workflows']
    assert any(
        'not supported for processing' in reason or 'Current software does not support' in reason
        for blocked in flair_eligibility['blocked_workflows']
        for reason in blocked['blocking_reasons']
    )
    polled = client.get(f"/projects/{project['id']}/datasets/{session['id']}/inventory").json()
    assert polled['inventory']['post_conversion_counts'] == inventory['post_conversion_counts']
    assert polled['inventory']['series'][0]['workflow_eligibility']['production_task_created'] is False
    assert polled['inventory']['bids_dataset_root'] == 'bids/rawdata'
    assert str(tmp_path / 'projects') not in json.dumps(polled)
    assert client.get(f"/projects/{project['id']}/tasks").json() == []


def test_dataset_inventory_endpoint_enriches_legacy_series_workflow_eligibility(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'PROJECTS_ROOT', tmp_path / 'projects')
    database.init_db()
    inventory = {
        "upload_session_id": 1,
        "project_id": 1,
        "inventory_status": "completed",
        "series": [
            {
                "series_id": 1,
                "modality": "T1",
                "sequence_label": "T1w_MPRAGE",
                "supported_for_processing": True,
                "unsupported_reason": "",
            }
        ],
    }
    with database.connect() as conn:
        now = database.now_iso()
        conn.execute("INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)", (1, "P", "", now))
        conn.execute(
            "INSERT INTO upload_sessions(id, project_id, label, source_type, status, progress, inventory_json, error_message, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                1,
                1,
                "legacy",
                "folder_or_archive",
                "failed",
                100,
                json.dumps(inventory),
                "failed under /home/yyf/project/image_agent/data/projects/1/uploads/1",
                now,
            ),
        )

    response = TestClient(app).get("/projects/1/datasets/1/inventory")

    assert response.status_code == 200
    payload_json = json.dumps(response.json())
    assert "/home/yyf/project/image_agent" not in payload_json
    assert response.json()["error_message"] == "failed under [redacted-host-path]"
    series = response.json()["inventory"]["series"][0]
    assert series["workflow_eligibility"]["policy_version"] == "workflow_eligibility_v1"
    assert series["workflow_eligibility"]["production_task_created"] is False
    assert series["workflow_eligibility"]["primary_recommendation"]["workflow_type"] == "t1_deepprep_anat_report"


def test_mixed_dataset_ingest_keeps_nifti_inventory_when_dcm2niix_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    from app.imaging import ingest
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(ingest, 'PROJECTS_ROOT', tmp_path / 'projects')

    def missing_dcm2niix(*args, **kwargs):
        raise FileNotFoundError("dcm2niix")

    monkeypatch.setattr(ingest.subprocess, 'run', missing_dcm2niix)
    database.init_db()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        tmp = tmp_path / 'subj1_T1w.nii.gz'
        make_nifti(tmp, shape=(8, 8, 8))
        z.writestr('subj1/anat/subj1_T1w.nii.gz', tmp.read_bytes())
        z.writestr('subj1/dicom/IM0001.dcm', b'\0' * 128 + b'DICM' + b'fake')

    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-missing-dcm2niix'}).json()
    session = client.post(
        f"/projects/{project['id']}/datasets/upload-session",
        json={'label': 'mixed.zip', 'source_type': 'folder_or_archive'},
    ).json()
    result = client.post(
        f"/projects/{project['id']}/datasets/{session['id']}/ingest",
        files={'archive': ('mixed.zip', buf.getvalue(), 'application/zip')},
    ).json()

    inventory = result['inventory']
    assert result['status'] == 'completed_with_partial_failures'
    assert inventory['dicom']['found_files'] == 1
    assert inventory['dicom']['conversion_status'] == 'failed'
    assert 'dcm2niix executable not found' in inventory['dicom']['failures'][0]['log_tail']
    assert 'source' not in inventory['dicom']['failures'][0]
    assert str(tmp_path / 'projects') not in json.dumps(inventory)
    assert inventory['post_conversion_counts']['by_modality']['T1'] == 1


def test_deepseek_chat_provider_can_be_used(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    def fake_complete_chat(message, context):
        assert message == '帮我解释当前项目'
        assert context['project_id'] is not None
        return 'DeepSeek response'

    class FailingModelGateway:
        def complete_text(self, messages, *, purpose):
            raise main.ModelGatewayError("OpenAI gateway intentionally unavailable in fallback test")

    monkeypatch.setattr(main, 'ModelGateway', lambda: FailingModelGateway())
    monkeypatch.setattr(main, 'complete_chat', fake_complete_chat)
    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-chat'}).json()
    res = client.post('/chat', json={'project_id': project['id'], 'message': '帮我解释当前项目'}).json()
    assert res['provider'] == 'deepseek'
    assert res['reply'] == 'DeepSeek response'


def test_chat_status_uses_requested_task_ids_beyond_recent_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-chat-status'}).json()
    with database.connect() as conn:
        for task_id in range(41, 75):
            conn.execute(
                "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    project['id'],
                    1,
                    't1_deepprep' if task_id == 41 else 'older_workflow',
                    'completed',
                    100,
                    str(tmp_path / f'{task_id}.log'),
                    f'2026-05-01T00:{task_id:02d}:00+00:00',
                ),
            )
        for task_id, workflow in ((111, 'bold_second_level'), (114, 'dwi_fast_gpu_dti')):
            conn.execute(
                "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (task_id, project['id'], 1, workflow, 'completed', 100, str(tmp_path / f'{task_id}.log'), '2026-05-02T00:00:00+00:00'),
            )

    res = client.post('/chat', json={'project_id': project['id'], 'message': '查看任务41、111、114的状态，并建议下一步'}).json()

    assert res['provider'] == 'rules'
    assert res['intent'] == 'status'
    assert '#41 t1_deepprep completed 100%' in res['reply']
    assert '#111 bold_second_level completed 100%' in res['reply']
    assert '#114 dwi_fast_gpu_dti completed 100%' in res['reply']
    assert res['recommended_next_step']
    assert res['tool_invocations']


def test_chat_inventory_capability_question_returns_full_read_only_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-chat-inventory'}).json()
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO files(id, project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (51, project['id'], 'sub-01_T1w.nii.gz', str(tmp_path / 'sub-01_T1w.nii.gz'), 'NIFTI', 1024, 'sha-t1', database.now_iso()),
        )
        conn.execute(
            "INSERT INTO imaging_series(id, project_id, file_id, sequence_label, supported_for_processing, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (61, project['id'], 51, 'T1w_MPRAGE', 1, 'T1', 'NIFTI', 0.98, '{}', 'ready', database.now_iso()),
        )

    payload = client.post(
        '/chat',
        json={'project_id': project['id'], 'message': '\u6211\u4e0a\u4f20\u4e86\u4ec0\u4e48\u6587\u4ef6\uff0c\u53ef\u4ee5\u8dd1\u4ec0\u4e48\u4efb\u52a1'},
    ).json()

    assert payload['provider'] == 'rules'
    assert payload['intent'] == 'inventory_capability'
    assert 'Uploaded files' in payload['reply']
    assert 'sub-01_T1w.nii.gz' in payload['reply']
    assert 'Detected series' in payload['reply']
    assert 'Runnable fixed workflows' in payload['reply']
    assert 't1_deepprep_anat_report' in payload['reply']
    assert 'No approval request has been created' in payload['reply']
    assert 'Approval required' not in payload['reply']


def test_chat_result_analysis_includes_observations_outputs_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-chat-results'}).json()
    output_dir = tmp_path / 'projects' / str(project['id']) / 'derivatives' / '118' / 'output'
    summary_dir = output_dir / 'summary'
    summary_dir.mkdir(parents=True)
    summary_path = summary_dir / 't1_result_summary.json'
    summary_path.write_text(json.dumps({
        'task_id': 118,
        'workflow_type': 't1_deepprep_anat_report',
        'modality': 'T1',
        'outputs': {
            'reports': [
                {'relative_path': 'reports/index.html', 'content_type': 'text/html'},
                {'relative_path': 'reports/t1_brain_measures_overview.png', 'content_type': 'image/png'},
            ],
            'qc': [
                {'relative_path': 'QC/sub-01/figures/sub-01_desc-volparc_T1w.svg', 'content_type': 'image/svg+xml'},
            ],
        },
    }), encoding='utf-8')
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO tasks(id, project_id, series_id, workflow_type, status, progress, log_path, created_at, finished_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (118, project['id'], 1, 't1_deepprep_anat_report', 'completed', 100, str(tmp_path / '118.log'), database.now_iso(), database.now_iso()),
        )
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (118, 'json', str(summary_path), None, json.dumps({'kind': 'result_summary'}), database.now_iso()),
        )

    payload = client.post(
        '/chat',
        json={'project_id': project['id'], 'message': 'analyze results for task 118 and explain the reports'},
    ).json()

    assert payload['provider'] == 'rules'
    assert payload['intent'] == 'status'
    assert 'Observation summary' in payload['reply']
    assert 'task 118' in payload['reply']
    assert 'completed' in payload['reply']
    assert 'Result artifacts' in payload['reply']
    assert 'reports/index.html' in payload['reply']
    assert 'QC observations' in payload['reply']
    assert 'No workflow was launched' in payload['reply']


def test_chat_mentions_real_bold_metric_outputs_after_implementation(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)
    reply = client.post('/chat', json={'message': 'Can you compute ALFF and seed connectivity?'}).json()['reply']
    assert 'ALFF' in reply
    assert 'seed-to-ROI' in reply
    assert 'fixed-coordinate spherical seed' in reply


def test_chat_exposes_intent_and_next_step_hints(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')

    database.init_db()
    client = TestClient(app)
    payload = client.post('/chat', json={'message': 'show me task status and next step'}).json()
    assert payload['intent'] in {'status', 'next_step'}
    assert payload['recommended_next_step']
    assert payload['tool_chain_hint']
    assert any(item['tool'] == 'inspect_task_status' for item in payload['tool_invocations'])
    assert payload['rag_mode'] in {'langgraph', 'fallback'}



def test_eddy_cuda_detection_accepts_versioned_binary(monkeypatch):
    from app.workflows import pipeline

    class Proc:
        returncode = 0
        stdout = "Detected CUDA eddy executable: /app/.pixi/envs/qsiprep/bin/eddy_cuda11.0\n"

    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *args, **kwargs: Proc())

    ok, detail = pipeline._docker_image_has_eddy_cuda("pennlinc/qsiprep:26.0.0")

    assert ok is True
    assert "eddy_cuda11.0" in detail


def test_eddy_cuda_detection_rejects_missing_binary(monkeypatch):
    from app.workflows import pipeline

    class Proc:
        returncode = 1
        stdout = "No executable matching eddy_cuda* found\n"

    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *args, **kwargs: Proc())

    ok, detail = pipeline._docker_image_has_eddy_cuda("pennlinc/qsiprep:26.0.0")

    assert ok is False
    assert "eddy_cuda*" in detail


def test_dwi_qsiprep_uses_reduced_resource_defaults(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, 'FS_LICENSE', tmp_path / 'license.txt')
    dirs = {
        'root': tmp_path,
        'bids': tmp_path / 'bids',
        'output': tmp_path / 'output',
        'work': tmp_path / 'work',
    }
    (dirs['bids'] / 'sub-01' / 'dwi').mkdir(parents=True)

    cmd = pipeline._commands('dwi_qsiprep', dirs)[0]
    wrapper_script = cmd[cmd.index('-c') + 1]

    assert '--nthreads 8' in wrapper_script
    assert '--omp-nthreads 4' in wrapper_script
    assert '--mem 24000' in wrapper_script


def test_dwi_workflow_lock_uses_projects_root(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, 'PROJECTS_ROOT', tmp_path / 'projects')
    log_path = tmp_path / 'task.log'

    with pipeline._workflow_lock('dwi_qsiprep', str(log_path)) as lock_path:
        assert lock_path == tmp_path / 'projects' / 'locks' / 'dwi_qsiprep.lock'
        assert lock_path.exists()

    log_text = log_path.read_text(encoding='utf-8')
    assert 'Acquired workflow lock' in log_text
    assert 'Released workflow lock' in log_text


# ── Docker labels ─────────────────────────────────────────────────────────────


def test_docker_labels_include_task_metadata():
    from app.workflows.pipeline import _docker_labels

    task = {"id": 42, "project_id": 7}
    labels = _docker_labels(task, "dwi_qsiprep")

    assert "--label" in labels
    assert "image_agent.app=image_agent" in labels
    assert "image_agent.task_id=42" in labels
    assert "image_agent.project_id=7" in labels
    assert "image_agent.workflow_type=dwi_qsiprep" in labels
    # Must not include patient data
    for item in labels:
        assert "patient" not in item.lower()
        assert "subject" not in item.lower()
        assert "name" not in item.lower()


def test_docker_labels_none_task_returns_empty():
    from app.workflows.pipeline import _docker_labels

    assert _docker_labels(None, "t1_deepprep") == []


def test_inject_labels_without_rm_falls_back_to_run():
    from app.workflows.pipeline import _inject_labels

    labels = ["--label", "image_agent.app=image_agent"]
    cmd = ["docker", "run", "--gpus", "all", "image:tag"]
    result = _inject_labels(cmd, labels)

    assert result == ["docker", "run", "--label", "image_agent.app=image_agent", "--gpus", "all", "image:tag"]


def test_inject_labels_skips_docker_inspect():
    from app.workflows.pipeline import _inject_labels

    labels = ["--label", "image_agent.app=image_agent"]
    cmd = ["docker", "inspect", "abc123"]
    result = _inject_labels(cmd, labels)

    assert result == cmd


def test_inject_labels_inserts_after_rm():
    from app.workflows.pipeline import _inject_labels

    labels = ["--label", "image_agent.app=image_agent"]
    cmd = ["docker", "run", "--rm", "--gpus", "all", "image:tag"]
    result = _inject_labels(cmd, labels)

    assert result == ["docker", "run", "--rm", "--label", "image_agent.app=image_agent", "--gpus", "all", "image:tag"]


def test_inject_labels_empty_labels_noop():
    from app.workflows.pipeline import _inject_labels

    cmd = ["docker", "run", "--rm", "--gpus", "all", "image:tag"]
    assert _inject_labels(cmd, []) == cmd


def test_inject_labels_skips_non_docker_cmd():
    from app.workflows.pipeline import _inject_labels

    cmd = ["python", "-m", "something"]
    labels = ["--label", "image_agent.app=image_agent"]
    assert _inject_labels(cmd, labels) == cmd


def test_commands_includes_labels_when_task_provided(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }
    (dirs["bids"] / "sub-01" / "dwi").mkdir(parents=True)
    task = {"id": 99, "project_id": 3}

    cmd = pipeline._commands("dwi_qsiprep", dirs, task=task)[0]
    wrapper_script = cmd[cmd.index("-c") + 1]

    assert "--label" in cmd
    assert "image_agent.app=image_agent" in cmd
    assert "image_agent.task_id=99" in cmd
    assert "image_agent.project_id=3" in cmd
    assert "image_agent.workflow_type=dwi_qsiprep" in cmd
    # Verify the wrapper script is still intact after label injection
    assert "--nthreads 8" in wrapper_script


def test_commands_without_task_omits_labels(monkeypatch, tmp_path):
    from app.workflows import pipeline

    monkeypatch.setattr(pipeline, "FS_LICENSE", tmp_path / "license.txt")
    dirs = {
        "root": tmp_path,
        "bids": tmp_path / "bids",
        "output": tmp_path / "output",
        "work": tmp_path / "work",
    }

    cmd = pipeline._commands("t1_deepprep", dirs)[0]
    assert "--label" not in cmd


# ── Health endpoint identity ─────────────────────────────────────────────────


def test_health_returns_app_identity():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/health").json()
    assert resp["status"] == "ok"
    assert resp["app"] == "image_agent"
    assert "version" in resp


def test_health_can_report_deployment_version_from_environment(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setenv("IMAGE_AGENT_DEPLOYMENT_VERSION", "codex-new-release")
    client = TestClient(app)

    resp = client.get("/health").json()

    assert resp["version"] == "codex-new-release"


def test_auth_required_rejects_missing_token_and_validates_login(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.app_factory import create_app
    from app.core import config
    from app.db import database

    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(config, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setenv("IMAGE_AGENT_REQUIRE_AUTH", "true")
    monkeypatch.setenv("IMAGE_AGENT_CONSOLE_USERNAME", "operator")
    monkeypatch.setenv("IMAGE_AGENT_CONSOLE_PASSWORD", "correct-password")
    monkeypatch.setenv("IMAGE_AGENT_CONSOLE_TOKEN", "operator-token")
    database.init_db()
    client = TestClient(create_app())

    assert client.get("/projects").status_code == 401
    assert client.post("/auth/login", json={"username": "operator", "password": "wrong"}).status_code == 401

    login = client.post("/auth/login", json={"username": "operator", "password": "correct-password"})
    assert login.status_code == 200
    assert login.json()["access_token"] == "operator-token"

    protected = client.get("/projects", headers={"Authorization": "Bearer operator-token"})
    assert protected.status_code == 200


# ── Recovery safety checks ───────────────────────────────────────────────────


def test_recovery_project_dir_exists(monkeypatch, tmp_path):
    from app.workflows import recovery

    monkeypatch.setattr(recovery, "PROJECTS_ROOT", tmp_path / "projects")
    (tmp_path / "projects" / "5").mkdir(parents=True)

    assert recovery._project_dir_exists(5) is True
    assert recovery._project_dir_exists(99) is False
    assert recovery._project_dir_exists(None) is False
    assert recovery._project_dir_exists("") is False


def test_recovery_container_in_project_tree(monkeypatch, tmp_path):
    from app.workflows import recovery

    projects = tmp_path / "projects"
    monkeypatch.setattr(recovery, "PROJECTS_ROOT", projects)

    # All mounts inside PROJECTS_ROOT — passes
    inside = {"Mounts": [{"Source": str(projects / "1" / "derivatives" / "42" / "output"), "RW": True}]}
    assert recovery._container_in_project_tree(inside) is True

    # Writable mount outside PROJECTS_ROOT — rejected
    outside_rw = {"Mounts": [{"Source": "/tmp/elsewhere", "RW": True}]}
    assert recovery._container_in_project_tree(outside_rw) is False

    # Read-only mount outside PROJECTS_ROOT with no project mount — rejected
    outside_ro = {"Mounts": [{"Source": "/opt/freesurfer/license.txt", "RW": False}]}
    assert recovery._container_in_project_tree(outside_ro) is False

    # Mixed: inside + read-only outside — passes
    mixed_ok = {"Mounts": [
        {"Source": str(projects / "1" / "bids"), "RW": True},
        {"Source": "/opt/freesurfer/license.txt", "RW": False},
    ]}
    assert recovery._container_in_project_tree(mixed_ok) is True

    # Mixed: inside + writable outside — rejected
    mixed_bad = {"Mounts": [
        {"Source": str(projects / "1" / "bids"), "RW": True},
        {"Source": "/etc/passwd", "RW": True},
    ]}
    assert recovery._container_in_project_tree(mixed_bad) is False

    # No mounts at all — rejected
    no_mounts = {"Mounts": []}
    assert recovery._container_in_project_tree(no_mounts) is False

    # Only read-only outside mounts, no project mount — rejected
    outside_only = {"Mounts": [{"Source": "/opt/freesurfer/license.txt", "RW": False}]}
    assert recovery._container_in_project_tree(outside_only) is False

    # No RW key defaults to writable — rejected for outside mount
    outside_no_rw = {"Mounts": [{"Source": "/tmp/elsewhere"}]}
    assert recovery._container_in_project_tree(outside_no_rw) is False


def test_recovery_no_project_mount_rejected(monkeypatch, tmp_path):
    from app.workflows import recovery

    projects = tmp_path / "projects"
    monkeypatch.setattr(recovery, "PROJECTS_ROOT", projects)

    # Only read-only outside mounts (e.g. license file, templateflow) but no project bind
    inspect_data = {"Mounts": [
        {"Source": "/opt/freesurfer/license.txt", "RW": False},
        {"Source": "/usr/share/templateflow", "RW": False},
    ]}
    assert recovery._container_in_project_tree(inspect_data) is False

    # Mixed: project mount + read-only support mounts — passes
    inspect_data_mixed = {"Mounts": [
        {"Source": str(projects / "1" / "derivatives" / "42" / "output"), "RW": True},
        {"Source": "/opt/freesurfer/license.txt", "RW": False},
    ]}
    assert recovery._container_in_project_tree(inspect_data_mixed) is True


def test_recovery_output_has_files(monkeypatch, tmp_path):
    from app.workflows import recovery

    projects = tmp_path / "projects"
    monkeypatch.setattr(recovery, "PROJECTS_ROOT", projects)

    out = projects / "1" / "derivatives" / "42" / "output"
    out.mkdir(parents=True)
    assert recovery._output_has_files(1, 42) is False

    (out / "result.nii.gz").write_text("fake")
    assert recovery._output_has_files(1, 42) is True


def test_recovery_list_containers_parses_docker_output(monkeypatch):
    from app.workflows import recovery

    class FakeProc:
        returncode = 0
        stdout = (
            "abc123\t42\t7\tdwi_qsiprep\trunning\tUp 2 hours\tpennlinc/qsiprep:latest\n"
            "def456\t43\t7\tdwi_qsirecon\texited\tExited (0) 1 hour ago\tpennlinc/qsirecon:latest\n"
        )

    monkeypatch.setattr(recovery, "_docker", lambda args, timeout=30: FakeProc())
    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")

    containers = recovery.list_image_agent_containers()
    assert len(containers) == 2
    assert containers[0]["task_id"] == "42"
    assert containers[0]["state"] == "running"
    assert containers[1]["task_id"] == "43"
    assert containers[1]["state"] == "exited"
