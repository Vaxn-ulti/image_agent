import gzip
import io
import json
import struct
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.core import config
from app.main import app


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
    stored = Path(uploaded['file']['storage_path'])
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
    stored_dwi = Path(dwi_upload['file']['storage_path'])
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


def test_workflow_catalog_exposes_implemented_workflows():
    client = TestClient(app)
    workflow_types = {w['type'] for w in client.get('/workflows').json()['workflows']}

    assert 'dicom_convert_validate' in workflow_types
    assert 'dicom_convert' in workflow_types
    assert 'bold_alff_validate' in workflow_types
    assert 'bold_alff' in workflow_types
    assert 'bold_falff_validate' in workflow_types
    assert 'bold_falff' in workflow_types


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
    assert client.get(f"/tasks/{task['id']}/outputs").json()
    assert 'completed' in client.get(f"/tasks/{task['id']}/logs").json()['text'].lower()
    chat = client.post('/chat', json={'project_id': project['id'], 'message': 'task status'}).json()
    assert 'Tasks:' in chat['reply']


def test_bold_deepprep_validate_allowed_for_fmri(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(config, 'PROJECTS_ROOT', tmp_path / 'projects')
    from app.db import database
    import app.main as main
    monkeypatch.setattr(database, 'DB_PATH', tmp_path / 'app.db')
    monkeypatch.setattr(main, 'run_pipeline_task', lambda task_id, qsiprep_task_id=None: None)

    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-bold'}).json()
    nii = tmp_path / 'sub-001_task-rest_bold.nii.gz'
    make_nifti(nii, shape=(64, 64, 32, 100))
    with nii.open('rb') as f:
        uploaded = client.post(f"/projects/{project['id']}/upload", files={'file': (nii.name, f, 'application/gzip')}).json()
    assert uploaded['series']['modality'] == 'BOLD'

    accepted = client.post(
        f"/series/{uploaded['series']['id']}/run",
        json={'workflow_type': 'bold_deepprep_validate'},
    )
    assert accepted.status_code == 200


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
    assert inventory['dicom']['found_files'] == 1
    assert inventory['post_conversion_counts']['by_modality']['T1'] >= 1
    assert inventory['post_conversion_counts']['by_modality']['DWI'] >= 1
    assert inventory['post_conversion_counts']['by_modality']['BOLD'] >= 1
    assert any(x['sequence'] == 'T2_FLAIR' for x in inventory['recognized_unsupported_sequences'])
    assert all('bids/rawdata/' in x['bids_path'] for x in inventory['series'])
    polled = client.get(f"/projects/{project['id']}/datasets/{session['id']}/inventory").json()
    assert polled['inventory']['post_conversion_counts'] == inventory['post_conversion_counts']


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

    monkeypatch.setattr(main, 'complete_chat', fake_complete_chat)
    database.init_db()
    client = TestClient(app)
    project = client.post('/projects', json={'name': 'P-chat'}).json()
    res = client.post('/chat', json={'project_id': project['id'], 'message': '帮我解释当前项目'}).json()
    assert res['provider'] == 'deepseek'
    assert res['reply'] == 'DeepSeek response'



def test_eddy_cuda_detection_accepts_versioned_binary(monkeypatch):
    from app.workflows import pipeline

    class Proc:
        returncode = 0
        stdout = "Detected CUDA eddy executable: /app/.pixi/envs/qsiprep/bin/eddy_cuda11.0\n"

    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *args, **kwargs: Proc())

    ok, detail = pipeline._docker_image_has_eddy_cuda("pennlinc/qsiprep:latest")

    assert ok is True
    assert "eddy_cuda11.0" in detail


def test_eddy_cuda_detection_rejects_missing_binary(monkeypatch):
    from app.workflows import pipeline

    class Proc:
        returncode = 1
        stdout = "No executable matching eddy_cuda* found\n"

    monkeypatch.setenv("IMAGE_AGENT_SUDO_PASSWORD", "pw")
    monkeypatch.setattr(pipeline.subprocess, "run", lambda *args, **kwargs: Proc())

    ok, detail = pipeline._docker_image_has_eddy_cuda("pennlinc/qsiprep:latest")

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
