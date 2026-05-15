import json
import os
import shutil
import subprocess
import gzip
import fcntl
from contextlib import contextmanager, nullcontext
from pathlib import Path

from app.core.config import FS_LICENSE, PROJECTS_ROOT
from app.db.database import connect, now_iso

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
    "bold_fmriprep": "nipreps/fmriprep:latest",
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
    linked = _link_existing_sidecars(src_path, target)
    if ".bval" not in linked and metadata.get("bval_file_id"):
        bval = _file_by_id(metadata["bval_file_id"])
        _link_or_copy(bval["storage_path"], dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bval")
    if ".bvec" not in linked and metadata.get("bvec_file_id"):
        bvec = _file_by_id(metadata["bvec_file_id"])
        _link_or_copy(bvec["storage_path"], dirs["bids"] / f"sub-{SUBJECT}" / "dwi" / f"sub-{SUBJECT}_dwi.bvec")
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
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if log_path:
            _append(log_path, f"Acquired workflow lock: {lock_path}")
        try:
            yield lock_path
        finally:
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
        "workflows": checks,
    }


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


def _commands(workflow, dirs, qsiprep_output=None, task=None):
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
        return [_inject_labels([
            "docker", "run", "--rm", *gpu_args, "--network", "host", *common_env,
            "-v", f"{source}:/data:ro", "-v", f"{dirs['output']}:/out", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            IMAGES[workflow], "/data", "/out", "participant", "--participant-label", SUBJECT, "--input-type", "qsiprep", "--recon-spec", "dipy_dki", "--fs-license-file", "/opt/freesurfer/license.txt", "--skip-odf-reports", "--nprocs", str(DWI_QSIRECON_NPROCS), "--omp-nthreads", str(DWI_QSIRECON_OMP_NTHREADS), "--mem", str(DWI_QSIRECON_MEM_MB), "-w", "/work", "--notrack",
        ], labels)]
    if workflow == "dwi_qsi_full":
        qsi_dirs = dict(dirs)
        qsi_dirs["output"] = dirs["output"] / "qsiprep"
        qsi_dirs["work"] = dirs["work"] / "qsiprep"
        recon_dirs = dict(dirs)
        recon_dirs["output"] = dirs["output"] / "qsirecon"
        recon_dirs["work"] = dirs["work"] / "qsirecon"
        return _commands("dwi_qsiprep", qsi_dirs, task=task) + _commands("dwi_qsirecon", recon_dirs, qsiprep_output=qsi_dirs["output"], task=task)
    if workflow == "bold_fmriprep":
        return [_inject_labels([
            "docker", "run", "--rm", *gpu_args, "--network", "host", *common_env,
            "-v", f"{dirs['bids']}:/data:ro", "-v", f"{dirs['output']}:/out", "-v", f"{dirs['work']}:/work", "-v", license_mount,
            IMAGES[workflow], "/data", "/out", "participant", "--participant-label", SUBJECT, "--fs-license-file", "/opt/freesurfer/license.txt", "--skip-bids-validation", "--output-spaces", "MNI152NLin2009cAsym:res-2", "--nthreads", "8", "--omp-nthreads", "4", "--mem-mb", "24000", "-w", "/work", "--notrack",
        ], labels)]
    if workflow in {"bold_alff", "bold_falff"}:
        metric = "ALFF" if workflow == "bold_alff" else "fALFF"
        return [["python", "-m", "app.workflows.bold_metrics", "--metric", metric, "--bids", str(dirs["bids"]), "--out", str(dirs["output"])]]
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
    dirs["output"].mkdir(parents=True, exist_ok=True)
    metric = "ALFF" if workflow == "bold_alff" else "fALFF"
    csv_path = dirs["output"] / f"sub-{SUBJECT}_{metric.lower()}_summary.csv"
    json_path = dirs["output"] / f"sub-{SUBJECT}_{metric.lower()}_metadata.json"
    csv_path.write_text("subject,metric,status\n" f"{SUBJECT},{metric},computed_placeholder\n", encoding="utf-8")
    json_path.write_text(json.dumps({"metric": metric, "method": "phase3 placeholder runner", "bids_dir": str(dirs["bids"])}, indent=2), encoding="utf-8")
    _append(log_path, f"Wrote {metric} metric placeholders: {csv_path}, {json_path}")
    _insert_output(task_id, "csv", csv_path, {"metric": metric})
    _insert_output(task_id, "json", json_path, {"metric": metric})


def _register_outputs(task_id, output_dir):
    patterns = [
        ("html_report", ["*.html"]),
        ("nifti", ["*.nii", "*.nii.gz"]),
        ("tsv", ["*.tsv"]),
        ("json", ["*.json"]),
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
        series = dict(_row("SELECT * FROM imaging_series WHERE id=?", (task["series_id"],)))
        dirs = _task_dirs(task) if workflow == "dicom_convert" else _build_bids(task, series)
        _append(log_path, f"Workspace ready: {dirs['root']}")
        image = IMAGES.get(workflow)
        if image is None and workflow not in {"dicom_convert", "bold_alff", "bold_falff"}:
            raise RuntimeError(f"unsupported workflow {workflow_type}")
        qsiprep_output = None
        if workflow == "dwi_qsirecon":
            qtask = _row("SELECT * FROM tasks WHERE id=?", (qsiprep_task_id or task.get("qsiprep_task_id"),))
            if qtask is None:
                raise RuntimeError("qsiprep_task_id not found")
            qsiprep_output = PROJECTS_ROOT / str(qtask["project_id"]) / "derivatives" / str(qtask["id"]) / "output"
        cmds = _dicom_commands(series, dirs) if workflow == "dicom_convert" else _commands(workflow, dirs, qsiprep_output=qsiprep_output, task=task)
        if validate:
            ok, inspect = (True, "local dcm2niix workflow") if workflow == "dicom_convert" else (True, "local BOLD metric workflow") if workflow in {"bold_alff", "bold_falff"} else _docker_image_exists(image)
            if ok and workflow == "dwi_qsiprep":
                cuda_ok, cuda_detail = _docker_image_has_eddy_cuda(image)
                ok = cuda_ok
                inspect = (inspect + "\n" + cuda_detail)[-2000:]
                if not ok:
                    inspect += "\nQSIPrep image does not expose eddy_cuda*; use a CUDA-enabled QSIPrep/FSL image before real DWI processing."
            if ok and workflow == "dwi_qsirecon":
                gpu_ok, gpu_detail = _docker_gpu_visible(image)
                inspect = (inspect + f"\nQSIRecon GPU visible with Docker --gpus all: {gpu_ok}\n" + gpu_detail)[-2000:]
            if ok and workflow == "dwi_qsi_full":
                cuda_ok, cuda_detail = _docker_image_has_eddy_cuda(image)
                ok = cuda_ok
                inspect = (inspect + "\n" + cuda_detail)[-2000:]
                if not ok:
                    inspect += "\nQSIPrep image does not expose eddy_cuda*; use a CUDA-enabled QSIPrep/FSL image before real DWI processing."
                qsirecon_image = IMAGES["dwi_qsirecon"]
                gpu_ok, gpu_detail = _docker_gpu_visible(qsirecon_image)
                inspect = (inspect + f"\nQSIRecon GPU visible with Docker --gpus all: {gpu_ok}\n" + gpu_detail)[-2000:]
            for cmd in cmds:
                _append(log_path, "COMMAND " + " ".join(str(x) for x in cmd))
            _insert_output(task_id, "command", None, {"image": image, "image_available": ok, "commands": cmds, "inspect_tail": inspect})
            if not ok:
                if workflow in ("dwi_qsiprep", "dwi_qsi_full"):
                    raise RuntimeError(f"QSIPrep GPU validation failed: container does not expose eddy_cuda* ({cuda_detail})")
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
        if workflow == "dicom_convert":
            _run_local_command(cmds[0], log_path)
            count = _register_outputs(task_id, dirs["output"])
            _append(log_path, f"Registered outputs: {count}")
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        if workflow in {"bold_alff", "bold_falff"}:
            _write_bold_metric(task_id, workflow, dirs, log_path)
            _update(task_id, status="completed", progress=100, finished_at=now_iso())
            return
        lock_name = "dwi_qsiprep" if workflow in {"dwi_qsiprep", "dwi_qsi_full"} else None
        lock_context = _workflow_lock(lock_name, log_path) if lock_name else nullcontext()
        with lock_context:
            for i, cmd in enumerate(cmds, start=1):
                _append(log_path, f"Starting container step {i}/{len(cmds)}")
                _run_command(task, cmd, log_path)
                _update(task_id, progress=20 + int(70 * i / len(cmds)))
        count = _register_outputs(task_id, dirs["output"])
        _append(log_path, f"Registered outputs: {count}")
        _update(task_id, status="completed", progress=100, finished_at=now_iso())
    except Exception as exc:
        _append(log_path, f"FAILED: {exc}")
        _update(task_id, status="failed", error_message=str(exc), finished_at=now_iso())
