import json
import os
import shutil
import subprocess
import gzip
import sys
from contextlib import contextmanager, nullcontext
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows local test fallback
    fcntl = None

from app.core.config import (
    FS_LICENSE,
    PROJECTS_ROOT,
    QSIRECON_PROFILE,
    QSIRECON_PROFILE_RECON_SPECS,
)
from app.db.database import connect, now_iso
from app.workflows import dwi_fast_dti
from app.workflows.bold_results import write_bold_result_summary_from_outputs, write_bold_scientific_report_from_outputs
from app.workflows.remote_scripts import (
    bold_remote_script_config,
    discover_bold_fmriprep_xcpd_outputs,
    path_safe_remote_preflight_summary,
    preflight_bold_fmriprep_xcpd_remote,
    run_bold_fmriprep_xcpd_remote,
)
from app.workflows.result_contract import load_result_summary
from app.workflows.t1_results import write_t1_result_summary, write_t1_scientific_report

SUBJECT = "01"

DWI_QSIPREP_NTHREADS = int(os.environ.get("IMAGE_AGENT_DWI_QSIPREP_NTHREADS", "8"))
DWI_QSIPREP_OMP_NTHREADS = int(os.environ.get("IMAGE_AGENT_DWI_QSIPREP_OMP_NTHREADS", "4"))
DWI_QSIPREP_MEM_MB = int(os.environ.get("IMAGE_AGENT_DWI_QSIPREP_MEM_MB", "24000"))
# Floor of 2: single-threaded eddy starves the GPU-based GP estimation and causes
# multi-hour stalls on multi-shell DWI data (task 65).  Must stay >= 2.
DWI_QSIPREP_EDDY_NUM_THREADS = max(2, int(os.environ.get(
    "IMAGE_AGENT_EDDY_NUM_THREADS",
    str(DWI_QSIPREP_OMP_NTHREADS),
)))
DWI_QSIPREP_EDDY_NITER = max(1, int(os.environ.get("IMAGE_AGENT_DWI_QSIPREP_EDDY_NITER", "3")))
DWI_QSIPREP_IS_SHELLED = os.environ.get("IMAGE_AGENT_DWI_QSIPREP_IS_SHELLED", "auto").lower()
DWI_QSIRECON_NPROCS = int(os.environ.get("IMAGE_AGENT_DWI_QSIRECON_NPROCS", "8"))
DWI_QSIRECON_OMP_NTHREADS = int(os.environ.get("IMAGE_AGENT_DWI_QSIRECON_OMP_NTHREADS", "4"))
DWI_QSIRECON_MEM_MB = int(os.environ.get("IMAGE_AGENT_DWI_QSIRECON_MEM_MB", "24000"))

IMAGES = {
    "t1_deepprep": "pbfslab/deepprep:25.1.0",
    "bold_deepprep": "pbfslab/deepprep:25.1.0",
    "dwi_qsiprep": "pennlinc/qsiprep:latest",
    "dwi_qsirecon": "pennlinc/qsirecon:latest",
    "dwi_qsi_full": "pennlinc/qsiprep:latest",
    "dwi_fast_gpu_dti": dwi_fast_dti.IMAGE,
    "bold_fmriprep": "nipreps/fmriprep:latest",
    "bold_fmriprep_xcpd_report": "nipreps/fmriprep:latest",
    "bold_fmriprep_xcpd_report_xcpd": "pennlinc/xcp_d:26.0.2",
}

QSIRECON_LEGACY_COMMAND = {
    "profile": "dki",
    "recon_spec": "dipy_dki",
    "extra_flags": ["--skip-odf-reports", "--notrack"],
}


def _row(sql, params=()):
    with connect() as conn:
        return conn.execute(sql, params).fetchone()


def _rows(sql, params=()):
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def _update(task_id, **values):
    if not values:
        return
    cols = ", ".join([f"{k}=?" for k in values])
    with connect() as conn:
        conn.execute(f"UPDATE tasks SET {cols} WHERE id=?", [*values.values(), task_id])


def _insert_output(task_id, output_type, path=None, metadata=None):
    if path is None:
        task = _row("SELECT project_id FROM tasks WHERE id=?", (task_id,))
        if task is not None:
            metadata_dir = PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task_id) / "output" / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = metadata_dir / f"{output_type}_output.json"
            metadata_path.write_text(json.dumps(metadata or {}, indent=2), encoding="utf-8")
            path = metadata_path
        else:
            path = ""
    with connect() as conn:
        conn.execute(
            "INSERT INTO outputs(task_id, output_type, path, preview_path, metadata_json, created_at) VALUES(?,?,?,?,?,?)",
            (task_id, output_type, str(path or ""), None, json.dumps(metadata or {}), now_iso()),
        )


def _append(log_path, text):
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"[{now_iso()}] {text}\n")


def _file_by_id(file_id):
    row = _row("SELECT * FROM files WHERE id=?", (file_id,))
    if row is None:
        raise RuntimeError(f"file not found: {file_id}")
    return dict(row)


def _link_or_copy(src, dst):
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _nifti_ext(path):
    name = Path(path).name.lower()
    return ".nii.gz" if name.endswith(".nii.gz") else ".nii"


def _sidecar_base(path):
    p = Path(path)
    return p.name[:-7] if p.name.lower().endswith(".nii.gz") else p.stem


def _link_existing_sidecars(src, dst, suffixes=(".json", ".bval", ".bvec")):
    src = Path(src)
    dst = Path(dst)
    src_base = _sidecar_base(src)
    dst_base = _sidecar_base(dst)
    linked = {}
    for suffix in suffixes:
        sidecar = src.with_name(src_base + suffix)
        if sidecar.exists():
            target = dst.with_name(dst_base + suffix)
            _link_or_copy(sidecar, target)
            linked[suffix] = target
    return linked


def _stage_nifti_for_container(src, dst_base):
    src = Path(src)
    if src.name.lower().endswith(".nii.gz"):
        dst = Path(str(dst_base) + ".nii.gz")
        _link_or_copy(src, dst)
        return dst
    if src.name.lower().endswith(".nii"):
        dst = Path(str(dst_base) + ".nii.gz")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        with src.open("rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)
        return dst
    raise RuntimeError(f"unsupported NIfTI extension: {src}")


def _dataset_description(bids_dir):
    Path(bids_dir, "dataset_description.json").write_text(
        json.dumps({"Name": "Brain Image Agent", "BIDSVersion": "1.9.0", "DatasetType": "raw"}, indent=2),
        encoding="utf-8",
    )


def _task_dirs(task):
    root = PROJECTS_ROOT / str(task["project_id"]) / "derivatives" / str(task["id"])
    return {
        "root": root,
        "bids": root / "bids",
        "output": root / "output",
        "work": root / "work",
    }


def _task_has_registered_outputs(task_id):
    rows = _rows("SELECT id FROM outputs WHERE task_id=? LIMIT 1", (task_id,))
    return bool(rows)


def _path_has_contents(path):
    return path.exists() and any(path.iterdir())


def _isolate_stale_task_workspace(task, log_path=None):
    """Move a pre-existing task workspace aside before building a fresh run."""
    dirs = _task_dirs(task)
    root = dirs["root"]
    if not _path_has_contents(root) or _task_has_registered_outputs(task["id"]):
        return None
    stale_root = root.parent / "_stale_task_workspaces"
    stale_root.mkdir(parents=True, exist_ok=True)
    suffix = now_iso().replace(":", "").replace("+", "_").replace(".", "_")
    target = stale_root / f"{task['id']}_{suffix}"
    counter = 1
    while target.exists():
        target = stale_root / f"{task['id']}_{suffix}_{counter}"
        counter += 1
    shutil.move(str(root), str(target))
    if log_path:
        _append(log_path, f"Isolated pre-existing task workspace before fresh run: {target}")
    return target


def _companion_series(project_id, modality, exclude_series_id=None):
    params = [project_id, modality]
    extra = ""
    if exclude_series_id is not None:
        extra = " AND id<>?"
        params.append(exclude_series_id)
    row = _row(
        "SELECT * FROM imaging_series WHERE project_id=? AND modality=?"
        f"{extra} AND supported_for_processing=1 ORDER BY id DESC LIMIT 1",
        tuple(params),
    )
    return dict(row) if row is not None else None


def _latest_completed_bold_deepprep_task(project_id, series_id):
    row = _row(
        "SELECT * FROM tasks WHERE project_id=? AND series_id=? AND workflow_type='bold_deepprep' AND status='completed' ORDER BY id DESC LIMIT 1",
        (project_id, series_id),
    )
    return dict(row) if row is not None else None


def _pick_existing_path(candidates):
    for candidate in candidates:
        if candidate is not None and Path(candidate).exists():
            return Path(candidate)
    return None


def _resolve_bold_metric_inputs(task, series, log_path=None):
    source_task = _latest_completed_bold_deepprep_task(series["project_id"], series["id"])
    if source_task is None:
        raise RuntimeError("BOLD metrics require a completed bold_deepprep task for this series")
    source_root = PROJECTS_ROOT / str(source_task["project_id"]) / "derivatives" / str(source_task["id"]) / "output"
    func_dir = source_root / "BOLD" / f"sub-{SUBJECT}" / "func"
    qc_fig_dir = source_root / "QC" / f"sub-{SUBJECT}" / "figures"

    preproc_bold = _pick_existing_path(sorted(func_dir.glob("*space-MNI*_desc-preproc_bold.nii.gz")))
    if preproc_bold is None:
        preproc_bold = _pick_existing_path(sorted(func_dir.glob("*desc-preproc_bold.nii.gz")))
    bold_json = preproc_bold.with_name(preproc_bold.name.replace(".nii.gz", ".json")) if preproc_bold else None
    mni_preproc = preproc_bold is not None and "space-MNI" in preproc_bold.name
    brain_mask = _pick_existing_path(sorted(func_dir.glob("*space-MNI*_desc-brain_mask.nii.gz")))
    if brain_mask is None and not mni_preproc:
        brain_mask = _pick_existing_path(sorted(func_dir.glob("*desc-brain_mask.nii.gz")))
    confounds_tsv = _pick_existing_path(sorted(func_dir.glob("*desc-confounds_timeseries.tsv")))
    tsnr_source = _pick_existing_path(sorted(qc_fig_dir.glob("*desc-tsnr_bold.nii.gz")))
    required = {
        "preproc_bold": preproc_bold,
        "bold_json": bold_json,
        "confounds_tsv": confounds_tsv,
    }
    if not mni_preproc:
        required["brain_mask"] = brain_mask
    missing = [name for name, path in required.items() if path is None or not Path(path).exists()]
    if missing:
        raise RuntimeError(
            "BOLD metrics require DeepPrep outputs, but the following inputs are missing from task "
            f"{source_task['id']}: {', '.join(missing)}"
        )
    if log_path:
        _append(log_path, f"Resolved BOLD metrics source task {source_task['id']} from {source_root}")
    return {
        "source_task_id": source_task["id"],
        "source_root": source_root,
        "preproc_bold": preproc_bold,
        "bold_json": bold_json,
        "brain_mask": brain_mask,
        "confounds_tsv": confounds_tsv,
        "tsnr_source": tsnr_source,
        "brain_mask_generated": False,
    }


def _generate_bold_brain_mask(preproc_bold, mask_path):
    import nibabel as nib
    import numpy as np

    img = nib.load(str(preproc_bold))
    data = np.asarray(img.dataobj, dtype=np.float32)
    if data.ndim != 4:
        raise RuntimeError(f"Expected 4D BOLD image for generated mask, got shape {data.shape}")
    finite = np.isfinite(data).all(axis=3)
    dynamic = np.std(data, axis=3) > 1e-6
    nonzero = np.any(np.abs(data) > 1e-6, axis=3)
    mask = finite & dynamic & nonzero
    try:
        from nilearn.masking import compute_epi_mask

        epi_mask = np.asarray(compute_epi_mask(str(preproc_bold)).dataobj) > 0
        if int((mask & epi_mask).sum()) > 0:
            mask = mask & epi_mask
    except Exception:
        pass
    if int(mask.sum()) == 0:
        mask = finite & nonzero
    if int(mask.sum()) == 0:
        raise RuntimeError(f"Unable to derive a non-empty BOLD brain mask from {preproc_bold}")
    mask_path = Path(mask_path)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(mask.astype("uint8"), img.affine, img.header.copy()), str(mask_path))
    return mask_path


def _prepare_bold_metric_inputs(metric_inputs, dirs, log_path=None):
    import nibabel as nib

    prepared = dict(metric_inputs)
    preproc_bold = Path(prepared["preproc_bold"])
    brain_mask = prepared.get("brain_mask")
    needs_generated = brain_mask is None
    if brain_mask is not None:
        preproc_shape = nib.load(str(preproc_bold)).shape[:3]
        mask_shape = nib.load(str(brain_mask)).shape[:3]
        needs_generated = preproc_shape != mask_shape
        if needs_generated and log_path:
            _append(
                log_path,
                f"Ignoring BOLD mask with shape {mask_shape}; preprocessed BOLD shape is {preproc_shape}",
            )
    if needs_generated:
        mask_path = dirs["output"] / "masks" / preproc_bold.name.replace("_desc-preproc_bold.nii.gz", "_desc-brain_mask.nii.gz")
        prepared["brain_mask"] = _generate_bold_brain_mask(preproc_bold, mask_path)
        prepared["brain_mask_generated"] = True
        if log_path:
            _append(log_path, f"Generated BOLD brain mask from MNI preprocessed BOLD: {prepared['brain_mask']}")
    return prepared


def _stage_t1(series, dirs):
    main_file = _file_by_id(series["file_id"])
    src_path = Path(main_file["storage_path"])
    target = _stage_nifti_for_container(src_path, dirs["bids"] / f"sub-{SUBJECT}" / "anat" / f"sub-{SUBJECT}_T1w")
    _link_existing_sidecars(src_path, target, suffixes=(".json",))
    return target


def _stage_bold(series, dirs):
    main_file = _file_by_id(series["file_id"])
    src_path = Path(main_file["storage_path"])
    target = _stage_nifti_for_container(src_path, dirs["bids"] / f"sub-{SUBJECT}" / "func" / f"sub-{SUBJECT}_task-rest_bold")
    _link_existing_sidecars(src_path, target, suffixes=(".json",))
    return target


def _stage_dwi(series, dirs):
    metadata = json.loads(series["metadata_json"])
    main_file = _file_by_id(series["file_id"])
    src_path = Path(main_file["storage_path"])
    target = _stage_nifti_for_container(src_path, dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi")
    linked = {}
    if metadata.get("bval_file_id"):
        bval = _file_by_id(metadata["bval_file_id"])
        _link_or_copy(bval["storage_path"], dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bval")
        linked[".bval"] = dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bval"
    if metadata.get("bvec_file_id"):
        bvec = _file_by_id(metadata["bvec_file_id"])
        _link_or_copy(bvec["storage_path"], dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bvec")
        linked[".bvec"] = dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bvec"
    if metadata.get("json_file_id"):
        json_sidecar = _file_by_id(metadata["json_file_id"])
        _link_or_copy(json_sidecar["storage_path"], dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.json")
        linked[".json"] = dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.json"
    missing_suffixes = tuple(suffix for suffix in (".json", ".bval", ".bvec") if suffix not in linked)
    if missing_suffixes:
        linked.update(_link_existing_sidecars(src_path, target, suffixes=missing_suffixes))
    if not (dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bval").exists() or not (dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bvec").exists():
        raise RuntimeError("DWI workflow requires bval and bvec sidecars")
    return target


def _has_staged_t1(dirs):
    return (dirs["bids"] / f"sub-{SUBJECT}" / "anat" / f"sub-{SUBJECT}_T1w.nii.gz").exists()


def _infer_eddy_is_shelled(dirs):
    if DWI_QSIPREP_IS_SHELLED in {"true", "1", "yes"}:
        return True
    if DWI_QSIPREP_IS_SHELLED in {"false", "0", "no"}:
        return False
    bval_path = dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bval"
    if not bval_path.exists():
        return True
    try:
        bvals = [float(v) for v in bval_path.read_text(encoding="utf-8").split()]
    except ValueError:
        return True
    shells = []
    for bval in bvals:
        if bval <= 100:
            continue
        if not any(abs(bval - shell) <= 100 for shell in shells):
            shells.append(bval)
    return len(shells) <= 4


def _write_qsiprep_eddy_cuda_config(dirs):
    """Write eddy CUDA config for production DWI runs.

    QSIPrep currently forces CUDA eddy to --nthr=1 internally, so
    num_threads is a backstop for CPU eddy or future QSIPrep images. Defaults
    to DWI_QSIPREP_OMP_NTHREADS (4) with a floor of 2; override via
    IMAGE_AGENT_EDDY_NUM_THREADS.

    dont_peas=true skips post-eddy alignment QC estimation.  This does not
    affect core eddy correction quality and is a well-established production
    speed optimization for multi-shell data.

    cnr_maps must remain true because this QSIPrep version rejects eddy config
    files where cnr_maps is false. After repeated long-running eddy_cuda runs
    on 129-volume test data, niter defaults to 3 as a speed-oriented first-pass
    setting. Override via IMAGE_AGENT_DWI_QSIPREP_EDDY_NITER.
    """
    config_path = dirs["root"] / "eddy_cuda_config.json"
    is_shelled = _infer_eddy_is_shelled(dirs)
    config_path.write_text(
        json.dumps(
            {
                "flm": "quadratic",
                "slm": "linear",
                "fep": False,
                "interp": "spline",
                "nvoxhp": 1000,
                "fudge_factor": 10,
                "dont_sep_offs_move": False,
                "dont_peas": True,
                "niter": DWI_QSIPREP_EDDY_NITER,
                "method": "jac",
                "repol": True,
                "num_threads": DWI_QSIPREP_EDDY_NUM_THREADS,
                "is_shelled": is_shelled,
                "use_cuda": True,
                "cnr_maps": True,
                "residuals": False,
                "output_type": "NIFTI_GZ",
                "args": "",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return config_path


@contextmanager
def _workflow_lock(name, log_path=None):
    lock_dir = PROJECTS_ROOT / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{name}.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        if log_path:
            _append(log_path, f"Waiting for workflow lock: {lock_path}")
        if fcntl is not None:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        elif log_path:
            _append(log_path, f"fcntl unavailable on this platform; using cooperative no-op lock for: {lock_path}")
        if log_path:
            _append(log_path, f"Acquired workflow lock: {lock_path}")
        try:
            yield lock_path
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            if log_path:
                _append(log_path, f"Released workflow lock: {lock_path}")


def _build_bids(task, series):
    dirs = _task_dirs(task)
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    _dataset_description(dirs["bids"])
    if series["modality"] == "T1":
        _stage_t1(series, dirs)
    elif series["modality"] == "BOLD":
        t1 = _companion_series(series["project_id"], "T1", exclude_series_id=series["id"])
        if t1 is not None:
            _stage_t1(t1, dirs)
        _stage_bold(series, dirs)
    elif series["modality"] == "DWI":
        t1 = _companion_series(series["project_id"], "T1", exclude_series_id=series["id"])
        if t1 is not None:
            _stage_t1(t1, dirs)
        _stage_dwi(series, dirs)
    return dirs


def _dicom_dir(series):
    metadata = json.loads(series["metadata_json"])
    path = metadata.get("dicom_dir")
    if not path:
        raise RuntimeError("DICOM series is missing dicom_dir metadata")
    return Path(path)


def _sudo_docker_prefix():
    pw = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD")
    if not pw:
        raise RuntimeError("IMAGE_AGENT_SUDO_PASSWORD is required for real Docker workflows")
    return ["sudo", "-S", "docker"], pw


def _docker_image_exists(image):
    cmd = ["sudo", "-S", "docker", "image", "inspect", image]
    password = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD")
    if not password:
        return False, "IMAGE_AGENT_SUDO_PASSWORD is required for sudo docker image inspect"
    proc = subprocess.run(cmd, input=password + "\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    return proc.returncode == 0, proc.stdout[-2000:]



def _docker_image_has_eddy_cuda(image):
    script = r"""
import glob
import os
import sys

dirs = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
dirs.extend([
    "/app/.pixi/envs/qsiprep/bin",
    "/opt/conda/bin",
    "/usr/local/bin",
    "/usr/bin",
])
seen = set()
matches = []
for directory in dirs:
    for candidate in glob.glob(os.path.join(directory, "eddy_cuda*")):
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            matches.append(candidate)
if matches:
    print("Detected CUDA eddy executable: " + sorted(matches)[0])
    sys.exit(0)
print("No executable matching eddy_cuda* found in PATH or common QSIPrep/FSL locations")
sys.exit(1)
"""
    cmd = [
        "sudo",
        "-S",
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "python",
        image,
        "-c",
        script,
    ]
    password = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD")
    if not password:
        return False, "IMAGE_AGENT_SUDO_PASSWORD is required for sudo docker run"
    proc = subprocess.run(cmd, input=password + "\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    return proc.returncode == 0, proc.stdout[-2000:]

def _docker_gpu_visible(image):
    cmd = [
        "sudo",
        "-S",
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--entrypoint",
        "python",
        image,
        "-c",
        "import os,sys; sys.exit(0 if any(name.startswith('nvidia') for name in os.listdir('/dev')) else 1)",
    ]
    password = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD")
    if not password:
        return False, "IMAGE_AGENT_SUDO_PASSWORD is required for sudo docker run"
    proc = subprocess.run(cmd, input=password + "\n", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    return proc.returncode == 0, proc.stdout[-2000:]


def inspect_runtime() -> dict:
    checks = {}
    for workflow, image in IMAGES.items():
        if workflow == "bold_fmriprep":
            continue
        ok, detail = _docker_image_exists(image)
        checks[workflow] = {
            "image": image,
            "available": ok,
            "detail_tail": detail[-500:],
        }
    return {
        "docker_requires_sudo": True,
        "fs_license_path": str(FS_LICENSE),
        "fs_license_exists": FS_LICENSE.exists(),
        "qsirecon_profile": QSIRECON_PROFILE,
        "qsirecon_recon_spec": QSIRECON_PROFILE_RECON_SPECS.get(QSIRECON_PROFILE, QSIRECON_PROFILE_RECON_SPECS["dki"]),
        "workflows": checks,
    }


def _qsirecon_profile_settings():
    profile = QSIRECON_PROFILE
    if profile not in QSIRECON_PROFILE_RECON_SPECS:
        raise RuntimeError(
            "Unsupported IMAGE_AGENT_QSIRECON_PROFILE="
            f"{profile!r}. Supported values: {', '.join(sorted(QSIRECON_PROFILE_RECON_SPECS))}"
        )
    recon_spec = QSIRECON_PROFILE_RECON_SPECS[profile]
    if profile == "tractography":
        return {
            "profile": profile,
            "recon_spec": recon_spec,
            "extra_flags": [],
            "tractography_capable": True,
        }
    return {
        "profile": "dki",
        "recon_spec": QSIRECON_PROFILE_RECON_SPECS["dki"],
        "extra_flags": ["--skip-odf-reports", "--notrack"],
        "tractography_capable": False,
    }


def _write_qsirecon_legacy_snapshot(root_dir: Path) -> Path:
    snapshot_dir = root_dir / "knowledge_base" / "qsirecon"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / "qsirecon_legacy_dipy_dki_command.json"
    payload = {
        **QSIRECON_LEGACY_COMMAND,
        "image": IMAGES["dwi_qsirecon"],
        "input_type": "qsiprep",
        "participant_label": SUBJECT,
        "resource_args": {
            "nprocs": DWI_QSIRECON_NPROCS,
            "omp_nthreads": DWI_QSIRECON_OMP_NTHREADS,
            "mem_mb": DWI_QSIRECON_MEM_MB,
        },
        "mount_templates": {
            "input": "{qsiprep_output}:/data:ro",
            "output": "{output}:/out",
            "work": "{work}:/work",
            "fs_license": "{fs_license}:/opt/freesurfer/license.txt:ro",
        },
        "command_template": [
            "docker", "run", "--rm", "--gpus", "all", "--network", "host",
            "-e", "TEMPLATEFLOW_HOME=/templateflow",
            "-v", "{qsiprep_output}:/data:ro",
            "-v", "{output}:/out",
            "-v", "{work}:/work",
            "-v", "{fs_license}:/opt/freesurfer/license.txt:ro",
            IMAGES["dwi_qsirecon"], "/data", "/out", "participant",
            "--participant-label", SUBJECT,
            "--input-type", "qsiprep",
            "--recon-spec", "dipy_dki",
            "--fs-license-file", "/opt/freesurfer/license.txt",
            "--skip-odf-reports",
            "--nprocs", str(DWI_QSIRECON_NPROCS),
            "--omp-nthreads", str(DWI_QSIRECON_OMP_NTHREADS),
            "--mem", str(DWI_QSIRECON_MEM_MB),
            "-w", "/work",
            "--notrack",
        ],
    }
    snapshot_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return snapshot_path


def _docker_labels(task, workflow):
    if task is None:
        return []
    return [
        "--label", "image_agent.app=image_agent",
        "--label", f"image_agent.task_id={task['id']}",
        "--label", f"image_agent.project_id={task['project_id']}",
        "--label", f"image_agent.workflow_type={workflow}",
    ]


def _inject_labels(cmd, labels):
    if not labels:
        return cmd
    # Only inject into docker run commands
    if len(cmd) < 2 or cmd[0] != "docker" or cmd[1] != "run":
        return cmd
    if "--rm" in cmd:
        rm_idx = cmd.index("--rm")
        return cmd[: rm_idx + 1] + labels + cmd[rm_idx + 1 :]
    return cmd[:2] + labels + cmd[2:]


def _commands(workflow, dirs, qsiprep_output=None, task=None, metric_inputs=None):
    license_mount = f"{FS_LICENSE}:/opt/freesurfer/license.txt:ro"
    common_env = ["-e", "TEMPLATEFLOW_HOME=/templateflow"]
    gpu_args = ["--gpus", "all"]
    labels = _docker_labels(task, workflow)
    if workflow == "t1_deepprep":
        return [_inject_labels([
            "docker", "run", "--rm", *gpu_args, "--network", "host",
            "-v", f"{dirs['bids']}:/data:ro", "-v", f"{dirs['output']}:/output", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            IMAGES[workflow], "/data", "/output", "participant", "--fs_license_file", "/opt/freesurfer/license.txt", "--skip_bids_validation", "--anat_only", "--cpus", "8", "--memory", "24",
        ], labels)]
    if workflow == "bold_deepprep":
        return [_inject_labels([
            "docker", "run", "--rm", *gpu_args, "--network", "host",
            "-v", f"{dirs['bids']}:/data:ro", "-v", f"{dirs['output']}:/output", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            IMAGES[workflow], "/data", "/output", "participant", "--fs_license_file", "/opt/freesurfer/license.txt", "--skip_bids_validation", "--bold_task_type", "rest", "--cpus", "8", "--memory", "24",
        ], labels)]
    if workflow == "dwi_qsiprep":
        eddy_config = _write_qsiprep_eddy_cuda_config(dirs)
        qsiprep_bin = "/app/.pixi/envs/qsiprep/bin"
        qsiprep_args = (
            f"/data /out participant "
            f"--participant-label {SUBJECT} "
            f"--fs-license-file /opt/freesurfer/license.txt "
            f"--skip-bids-validation "
            f"--output-resolution 2 "
            f"--nthreads {DWI_QSIPREP_NTHREADS} "
            f"--omp-nthreads {DWI_QSIPREP_OMP_NTHREADS} "
            f"--mem {DWI_QSIPREP_MEM_MB} "
            f"-w /work "
            f"--notrack "
            f"--eddy-config /eddy_cuda_config.json"
        )
        if not _has_staged_t1(dirs):
            qsiprep_args += " --anat-modality none"
        wrapper_script = (
            f"ln -sf eddy_cuda11.0 {qsiprep_bin}/eddy_cuda && "
            f"ln -sf eddy_cuda11.0 {qsiprep_bin}/eddy_cuda10.2 && "
            f"exec {qsiprep_bin}/qsiprep {qsiprep_args}"
        )
        cmd = [
            "docker", "run", "--rm", *gpu_args, "--network", "host", *common_env,
            "-v", f"{dirs['bids']}:/data:ro", "-v", f"{dirs['output']}:/out", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            "-v", f"{eddy_config}:/eddy_cuda_config.json:ro",
            "--entrypoint", "bash",
            IMAGES[workflow], "-c", wrapper_script,
        ]
        return [_inject_labels(cmd, labels)]
    if workflow == "dwi_qsirecon":
        source = qsiprep_output or dirs["bids"]
        qsirecon = _qsirecon_profile_settings()
        cmd = [
            "docker", "run", "--rm", *gpu_args, "--network", "host", *common_env,
            "-v", f"{source}:/data:ro", "-v", f"{dirs['output']}:/out", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            IMAGES[workflow], "/data", "/out", "participant", "--participant-label", SUBJECT, "--input-type", "qsiprep", "--recon-spec", qsirecon["recon_spec"], "--fs-license-file", "/opt/freesurfer/license.txt", "--nprocs", str(DWI_QSIRECON_NPROCS), "--omp-nthreads", str(DWI_QSIRECON_OMP_NTHREADS), "--mem", str(DWI_QSIRECON_MEM_MB), "-w", "/work",
        ]
        cmd.extend(qsirecon["extra_flags"])
        return [_inject_labels(cmd, labels)]
    if workflow == "dwi_qsi_full":
        qsi_dirs = dict(dirs)
        qsi_dirs["output"] = dirs["output"] / "qsiprep"
        qsi_dirs["work"] = dirs["work"] / "qsiprep"
        recon_dirs = dict(dirs)
        recon_dirs["output"] = dirs["output"] / "qsirecon"
        recon_dirs["work"] = dirs["work"] / "qsirecon"
        return _commands("dwi_qsiprep", qsi_dirs, task=task) + _commands("dwi_qsirecon", recon_dirs, qsiprep_output=qsi_dirs["output"], task=task)
    if workflow == "dwi_fast_gpu_dti":
        runner_dirs = dict(dirs)
        if task is not None:
            runner_dirs["task_id"] = task["id"]
        return [dwi_fast_dti.build_command(runner_dirs, image=IMAGES[workflow])]
    if workflow == "bold_fmriprep":
        return [_inject_labels([
            "docker", "run", "--rm", *gpu_args, "--network", "host", *common_env,
            "-v", f"{dirs['bids']}:/data:ro", "-v", f"{dirs['output']}:/out", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            IMAGES[workflow], "/data", "/out", "participant", "--participant-label", SUBJECT, "--fs-license-file", "/opt/freesurfer/license.txt", "--skip-bids-validation", "--output-spaces", "MNI152NLin2009cAsym:res-2", "--nthreads", "8", "--omp-nthreads", "4", "--mem-mb", "24000", "-w", "/work", "--notrack",
        ], labels)]
    if workflow == "bold_fmriprep_xcpd_report":
        config = bold_remote_script_config()
        return [
            ["remote-script", "fmriprep", config["fmriprep_script"]],
            ["remote-script", "xcpd", config["xcpd_script"]],
        ]
    if workflow in {"bold_alff", "bold_falff", "bold_second_level"}:
        metric = "alff" if workflow == "bold_alff" else "falff" if workflow == "bold_falff" else None
        metrics = [metric] if metric else ["alff", "falff", "reho", "dmn", "seed_to_roi"]
        cmd = [
            sys.executable,
            "-m",
            "app.workflows.bold_metrics",
        ]
        if metric_inputs:
            primary_metric = "ALFF" if workflow != "bold_falff" else "fALFF"
            cmd += [
                "--metric",
                primary_metric,
                "--preproc-bold",
                str(metric_inputs["preproc_bold"]),
                "--bold-json",
                str(metric_inputs["bold_json"]),
                "--brain-mask",
                str(metric_inputs["brain_mask"]),
                "--confounds",
                str(metric_inputs["confounds_tsv"]),
                "--out",
                str(dirs["output"]),
            ]
            if metric_inputs.get("tsnr_source"):
                cmd += ["--tsnr", str(metric_inputs["tsnr_source"])]
            return [cmd]
        return [[
            *cmd,
            "--metrics",
            *metrics,
            "--seed-preset",
            "PCC_DMN",
            "--bids",
            str(dirs["bids"]),
            "--out",
            str(dirs["output"]),
        ]]
    raise RuntimeError(f"unsupported workflow: {workflow}")


def _dicom_commands(series, dirs):
    return [["dcm2niix", "-z", "y", "-o", str(dirs["output"] / "nifti"), str(_dicom_dir(series))]]


def _run_local_command(cmd, log_path):
    _append(log_path, "RUN " + " ".join(str(x) for x in cmd))
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=None)
    _append(log_path, proc.stdout[-12000:])
    if proc.returncode != 0:
        raise RuntimeError(f"local command failed rc={proc.returncode}")


def _write_bold_metric(task_id, workflow, dirs, log_path):
    from app.workflows.bold_metrics import run_metrics

    metric = "alff" if workflow == "bold_alff" else "falff" if workflow == "bold_falff" else None
    metrics = [metric] if metric else ["alff", "falff", "reho", "dmn", "seed_to_roi"]
    seed_presets = ["PCC_DMN"] if metric else None
    summary_path = run_metrics(
        bids_dir=dirs["bids"],
        out_dir=dirs["output"],
        metrics=metrics,
        seed_presets=seed_presets,
        subject_id=SUBJECT,
        task_label="rest",
    )
    _append(log_path, f"Wrote structured BOLD metric outputs: {summary_path}")
    _insert_output(task_id, "json", summary_path, {"metric": metric or "second_level", "kind": "bold_metrics_summary"})
    _insert_output(task_id, "tsv", dirs["output"] / "tables" / "seed_to_roi.tsv", {"metric": metric or "second_level", "kind": "seed_to_roi"})
    if workflow == "bold_second_level":
        _insert_output(task_id, "tsv", dirs["output"] / "tables" / "network_dmn.tsv", {"metric": "dmn", "kind": "network_summary"})


def _write_dwi_fast_validate(task_id, workflow_type, dirs, log_path):
    summary_path = dwi_fast_dti.write_validate_outputs(dirs["output"], task_id=task_id, workflow_type=workflow_type)
    _append(log_path, f"Wrote DWI fast GPU DTI validate output contract: {summary_path}")
    _insert_output(task_id, "json", summary_path, {"kind": "result_summary", "modality": "DWI"})


def _write_bold_fmriprep_xcpd_summary(task_id, workflow_type, dirs, log_path):
    from app.workflows.result_contract import build_result_summary

    output_dir = dirs["output"]
    outputs = discover_bold_fmriprep_xcpd_outputs(output_dir)
    summary_path = build_result_summary(
        output_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality="BOLD",
        spaces=["MNI152NLin6Asym", "MNI152NLin2009cAsym", "T1w"],
        feature_groups=["preprocessing", "motion_confounds", "xcpd_qc", "connectivity", "reports"],
        outputs=outputs,
        provenance={
            "pipeline": "fMRIPrep + XCP-D",
            "fmriprep_image": IMAGES["bold_fmriprep_xcpd_report"],
            "xcpd_image": IMAGES["bold_fmriprep_xcpd_report_xcpd"],
            "artifact_discovery_only": True,
            "note": "Feature values are registered from generated artifacts; no diagnostic claims are inferred.",
        },
    )
    _append(log_path, f"Wrote BOLD fMRIPrep + XCP-D result summary: {summary_path}")
    existing = _rows(
        "SELECT id FROM outputs WHERE task_id=? AND path=? AND metadata_json=? LIMIT 1",
        (task_id, str(summary_path), json.dumps({"kind": "result_summary", "modality": "BOLD"})),
    )
    if not existing:
        _insert_output(task_id, "json", summary_path, {"kind": "result_summary", "modality": "BOLD"})
    return summary_path


def _validate_bold_fmriprep_xcpd_artifacts(outputs: dict) -> None:
    required = {
        "reports": "at least one fMRIPrep/XCP-D HTML report",
        "tables": "at least one XCP-D TSV table",
        "maps": "at least one derivative NIfTI map",
        "logs": "at least one fMRIPrep/XCP-D execution log",
    }
    missing = [message for key, message in required.items() if not outputs.get(key)]
    if missing:
        raise RuntimeError("BOLD fMRIPrep + XCP-D completed without required artifacts: " + "; ".join(missing))


def _remote_bold_preflight_status(dirs):
    preflight = preflight_bold_fmriprep_xcpd_remote(
        bids_dir=dirs["bids"],
        output_dir=dirs["output"],
        work_dir=dirs["work"],
        require_bids=True,
    )
    inspect = json.dumps(path_safe_remote_preflight_summary(preflight), ensure_ascii=False)
    return bool(preflight.get("ok")), inspect[-2000:]


def _register_outputs(task_id, output_dir):
    patterns = [
        ("html_report", ["*.html"]),
        ("nifti", ["*.nii", "*.nii.gz"]),
        ("tsv", ["*.tsv"]),
        ("json", ["*.json"]),
        ("log", ["*.log"]),
        ("tractography", ["*.tck", "*.trk"]),
        ("connectome", ["*.csv"]),
    ]
    count = 0
    for output_type, globs in patterns:
        for pat in globs:
            for p in Path(output_dir).rglob(pat):
                _insert_output(task_id, output_type, p, {"source": "discovered"})
                count += 1
    return count


def _run_command(task, cmd, log_path):
    docker_prefix, password = _sudo_docker_prefix()
    full = docker_prefix + cmd[1:]
    _append(log_path, "RUN " + " ".join(str(x) for x in full))
    proc = subprocess.Popen(full, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdin is not None
    proc.stdin.write(password + "\n")
    proc.stdin.close()
    assert proc.stdout is not None
    for line in proc.stdout:
        _append(log_path, line.rstrip())
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"docker command failed rc={rc}")


def run_pipeline_task(task_id: int, qsiprep_task_id: int | None = None) -> None:
    task_row = _row("SELECT * FROM tasks WHERE id=?", (task_id,))
    if task_row is None:
        return
    task = dict(task_row)
    log_path = task["log_path"]
    workflow_type = task["workflow_type"]
    validate = workflow_type.endswith("_validate")
    workflow = workflow_type[:-9] if validate else workflow_type
    try:
        _update(task_id, status="running", progress=5, started_at=now_iso())
        _isolate_stale_task_workspace(task, log_path)
        series = dict(_row("SELECT * FROM imaging_series WHERE id=?", (task["series_id"],)))
        dirs = _task_dirs(task) if workflow == "dicom_convert" else _build_bids(task, series)
        legacy_snapshot = _write_qsirecon_legacy_snapshot(dirs["root"]) if workflow in ("dwi_qsirecon", "dwi_qsi_full") else None
        _append(log_path, f"Workspace ready: {dirs['root']}")
        if legacy_snapshot is not None:
            _append(log_path, f"Saved QSIRecon legacy command snapshot: {legacy_snapshot}")
        image = IMAGES.get(workflow)
        if image is None and workflow not in {"dicom_convert", "bold_alff", "bold_falff", "bold_second_level", "bold_fmriprep_xcpd_report"}:
            raise RuntimeError(f"unsupported workflow {workflow_type}")
        qsiprep_output = None
        if workflow == "dwi_qsirecon":
            qtask = _row("SELECT * FROM tasks WHERE id=?", (qsiprep_task_id or task.get("qsiprep_task_id"),))
            if qtask is None:
                raise RuntimeError("qsiprep_task_id not found")
            qsiprep_output = PROJECTS_ROOT / str(qtask["project_id"]) / "derivatives" / str(qtask["id"]) / "output"
        bold_metric_inputs = None
        if workflow in {"bold_alff", "bold_falff", "bold_second_level"} and not validate:
            bold_metric_inputs = _resolve_bold_metric_inputs(task, series, log_path)
            bold_metric_inputs = _prepare_bold_metric_inputs(bold_metric_inputs, dirs, log_path)
        cmds = _dicom_commands(series, dirs) if workflow == "dicom_convert" else _commands(workflow, dirs, qsiprep_output=qsiprep_output, task=task, metric_inputs=bold_metric_inputs)
        if validate:
            ok, inspect = (
                (True, "local dcm2niix workflow")
                if workflow == "dicom_convert"
                else (True, "local BOLD metric workflow")
                if workflow in {"bold_alff", "bold_falff", "bold_second_level"}
                else _remote_bold_preflight_status(dirs)
                if workflow == "bold_fmriprep_xcpd_report"
                else dwi_fast_dti.check_runtime()
                if workflow == "dwi_fast_gpu_dti"
                else _docker_image_exists(image)
            )
            if ok and workflow == "dwi_qsiprep":
                cuda_ok, cuda_detail = _docker_image_has_eddy_cuda(image)
                ok = cuda_ok
                inspect = (inspect + "\n" + cuda_detail)[-2000:]
                if not ok:
                    inspect += "\nQSIPrep image does not expose eddy_cuda*; use a CUDA-enabled QSIPrep/FSL image before real DWI processing."
            if ok and workflow == "dwi_qsirecon":
                gpu_ok, gpu_detail = _docker_gpu_visible(image)
                inspect = (inspect + f"\nQSIRecon GPU visible with Docker --gpus all: {gpu_ok}\n" + gpu_detail)[-2000:]
                inspect = (inspect + f"\nQSIRecon profile: {_qsirecon_profile_settings()['profile']} / recon-spec: {_qsirecon_profile_settings()['recon_spec']}")[-2000:]
            if ok and workflow == "dwi_qsi_full":
                cuda_ok, cuda_detail = _docker_image_has_eddy_cuda(image)
                ok = cuda_ok
                inspect = (inspect + "\n" + cuda_detail)[-2000:]
                if not ok:
                    inspect += "\nQSIPrep image does not expose eddy_cuda*; use a CUDA-enabled QSIPrep/FSL image before real DWI processing."
                qsirecon_image = IMAGES["dwi_qsirecon"]
                gpu_ok, gpu_detail = _docker_gpu_visible(qsirecon_image)
                inspect = (inspect + f"\nQSIRecon GPU visible with Docker --gpus all: {gpu_ok}\n" + gpu_detail)[-2000:]
                inspect = (inspect + f"\nQSIRecon profile: {_qsirecon_profile_settings()['profile']} / recon-spec: {_qsirecon_profile_settings()['recon_spec']}")[-2000:]
            if ok and workflow == "dwi_fast_gpu_dti":
                _write_dwi_fast_validate(task_id, workflow_type, dirs, log_path)
            for cmd in cmds:
                _append(log_path, "COMMAND " + " ".join(str(x) for x in cmd))
            output_metadata = {"image": image, "image_available": ok, "commands": cmds, "inspect_tail": inspect}
            if workflow in ("dwi_qsirecon", "dwi_qsi_full"):
                output_metadata["qsirecon_profile"] = _qsirecon_profile_settings()
            if workflow == "dwi_fast_gpu_dti":
                output_metadata["result_summary"] = load_result_summary(dirs["output"])
            if legacy_snapshot is not None:
                output_metadata["legacy_snapshot_path"] = str(legacy_snapshot)
            _insert_output(task_id, "command", None, output_metadata)
            if not ok:
                if workflow in ("dwi_qsiprep", "dwi_qsi_full"):
                    raise RuntimeError(f"QSIPrep GPU validation failed: container does not expose eddy_cuda* ({cuda_detail})")
                if workflow == "dwi_fast_gpu_dti":
                    raise RuntimeError(f"DWI fast GPU DTI validation failed: {inspect}")
                raise RuntimeError(f"docker image not available: {image}")
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        _update(task_id, progress=20)
        if workflow in ("dwi_qsiprep", "dwi_qsi_full"):
            cuda_ok, cuda_detail = _docker_image_has_eddy_cuda(image)
            if not cuda_ok:
                _append(log_path, cuda_detail)
                raise RuntimeError("QSIPrep GPU run requires eddy_cuda* inside the container; current image only supports CPU eddy")
            _append(log_path, f"CUDA eddy detected: {cuda_detail}")
        if workflow in ("dwi_qsirecon", "dwi_qsi_full"):
            qsirecon_image = IMAGES["dwi_qsirecon"]
            gpu_ok, gpu_detail = _docker_gpu_visible(qsirecon_image)
            if not gpu_ok:
                _append(log_path, gpu_detail)
                raise RuntimeError("QSIRecon GPU run requires Docker --gpus all; GPU not visible inside QSIRecon container")
        if workflow == "dwi_fast_gpu_dti":
            resources = dwi_fast_dti.prepare_mni_resources(dirs)
            _append(
                log_path,
                "Prepared DWI MNI resources: "
                f"template={resources['template']} atlas={resources['atlas']}",
            )
            _run_local_command(cmds[0], log_path)
            summary_path = dwi_fast_dti.write_result_summary_from_outputs(dirs["output"], task_id=task_id, workflow_type=workflow)
            _insert_output(task_id, "json", summary_path, {"kind": "result_summary", "modality": "DWI"})
            report_summary = dwi_fast_dti.write_scientific_report_summary_from_outputs(dirs["output"], task_id=task_id, workflow_type=workflow)
            _insert_output(task_id, "json", report_summary, {"kind": "scientific_report_summary", "modality": "DWI"})
            count = _register_outputs(task_id, dirs["output"])
            _append(log_path, f"Registered outputs: {count}")
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        if workflow == "dicom_convert":
            _run_local_command(cmds[0], log_path)
            count = _register_outputs(task_id, dirs["output"])
            _append(log_path, f"Registered outputs: {count}")
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        if workflow == "bold_fmriprep_xcpd_report":
            run_result = run_bold_fmriprep_xcpd_remote(
                task_id=task_id,
                bids_dir=dirs["bids"],
                output_dir=dirs["output"],
                work_dir=dirs["work"],
                log_path=log_path,
            )
            _validate_bold_fmriprep_xcpd_artifacts(run_result.get("outputs") or {})
            _append(log_path, f"Remote BOLD fMRIPrep/XCP-D wrapper completed: {run_result.get('scripts')}")
            _update(task_id, progress=90)
            summary_path = _write_bold_fmriprep_xcpd_summary(task_id, workflow_type, dirs, log_path)
            count = _register_outputs(task_id, dirs["output"])
            _append(log_path, f"Registered outputs: {count}; result_summary={summary_path}")
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        if workflow in {"bold_alff", "bold_falff", "bold_second_level"}:
            _run_local_command(cmds[0], log_path)
            summary_candidates = sorted(dirs["output"].glob("*_desc-bold_metrics_summary.json"))
            if not summary_candidates:
                raise RuntimeError("BOLD metric command completed but did not write a bold metrics summary")
            summary_path = summary_candidates[0]
            metric = "alff" if workflow == "bold_alff" else "falff" if workflow == "bold_falff" else "second_level"
            _insert_output(task_id, "json", summary_path, {"metric": metric, "kind": "bold_metrics_summary"})
            seed_to_roi = sorted(dirs["output"].glob("*_desc-seed_to_roi.tsv"))
            if seed_to_roi:
                _insert_output(task_id, "tsv", seed_to_roi[0], {"metric": metric, "kind": "seed_to_roi"})
            network_dmn = sorted(dirs["output"].glob("*_desc-network_dmn.tsv"))
            if network_dmn:
                _insert_output(task_id, "tsv", network_dmn[0], {"metric": "dmn", "kind": "network_summary"})
            result_summary_path = write_bold_result_summary_from_outputs(
                dirs["output"],
                task_id=task_id,
                workflow_type=workflow,
            )
            _insert_output(task_id, "json", result_summary_path, {"kind": "result_summary", "modality": "BOLD"})
            report_summary = write_bold_scientific_report_from_outputs(
                dirs["output"],
                task_id=task_id,
                workflow_type=workflow,
            )
            _insert_output(task_id, "json", report_summary, {"kind": "scientific_report_summary", "modality": "BOLD"})
            count = _register_outputs(task_id, dirs["output"])
            _append(log_path, f"Registered outputs: {count}")
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        lock_name = "dwi_qsiprep" if workflow in {"dwi_qsiprep", "dwi_qsi_full"} else None
        lock_context = _workflow_lock(lock_name, log_path) if lock_name else nullcontext()
        with lock_context:
            for i, cmd in enumerate(cmds, start=1):
                _append(log_path, f"Starting container step {i}/{len(cmds)}")
                _run_command(task, cmd, log_path)
                _update(task_id, progress=20 + int(70 * i / len(cmds)))
        if workflow == "t1_deepprep":
            summary_path = write_t1_result_summary(dirs["output"], task_id=task_id, workflow_type=workflow)
            _insert_output(task_id, "json", summary_path, {"kind": "result_summary", "modality": "T1"})
            report_summary = write_t1_scientific_report(dirs["output"], task_id=task_id, workflow_type=workflow)
            _insert_output(task_id, "json", report_summary, {"kind": "scientific_report_summary", "modality": "T1"})
        count = _register_outputs(task_id, dirs["output"])
        _append(log_path, f"Registered outputs: {count}")
        _update(task_id, status="completed", progress=100, finished_at=now_iso())
    except Exception as exc:
        _append(log_path, f"FAILED: {exc}")
        _update(task_id, status="failed", error_message=str(exc), finished_at=now_iso())
