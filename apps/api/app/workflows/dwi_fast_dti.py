from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.core.config import load_env_file
from app.workflows.native_qc import discover_native_qc_outputs
from app.workflows.result_contract import build_result_summary
from app.workflows.scientific_reports import build_scientific_report_summary

load_env_file()

MRTRIX_IMAGE = os.environ.get("IMAGE_AGENT_DWI_MRTRIX_IMAGE", "pennlinc/qsiprep:latest")
IMAGE = MRTRIX_IMAGE
FSL_DIR = Path(os.environ.get("IMAGE_AGENT_FSL_DIR", "/home/yyf/project/MCI_project/tools/fsl"))
MAX_RUNTIME_SEC = int(os.environ.get("IMAGE_AGENT_DWI_FAST_DTI_MAX_RUNTIME_SEC", "2100"))
SUBJECT = "01"
DTI_METRICS = ("fa", "md", "ad", "rd")
DEFAULT_ATLAS = os.environ.get("IMAGE_AGENT_DWI_DTI_ATLAS", "MNI152_Schaefer2018_200Parcels_7Networks")
FLIRT_REGISTRATION_ATTEMPTS = (
    {
        "method": "flirt_normmi_dof6",
        "args": ["-dof", "6", "-cost", "normmi"],
    },
    {
        "method": "flirt_mutualinfo_dof6",
        "args": ["-dof", "6", "-cost", "mutualinfo"],
    },
    {
        "method": "flirt_corratio_dof12",
        "args": ["-dof", "12"],
    },
)
RESOURCE_SUBDIR = "mni152_resources"
MNI_TEMPLATE_FILENAME = "tpl-MNI152NLin2009cAsym_res-02_T1w.nii.gz"
MNI_ATLAS_FILENAME = "dwi_dti_mni_atlas.nii.gz"
MNI_ATLAS_METADATA_FILENAME = "dwi_dti_mni_atlas.json"
MNI_TEMPLATE = f"/resources/{MNI_TEMPLATE_FILENAME}"
MNI_ATLAS = f"/resources/{MNI_ATLAS_FILENAME}"
MNI_ATLAS_METADATA = f"/resources/{MNI_ATLAS_METADATA_FILENAME}"
DEFAULT_TEMPLATE_CANDIDATES = [
    "/home/yyf/project/MCI_project/tools/fsl/data/standard/MNI152_T1_2mm.nii.gz",
    "/home/yyf/Project/qsitest_20260507/templateflow/tpl-MNI152NLin2009cAsym/tpl-MNI152NLin2009cAsym_res-02_T1w.nii.gz",
    "/home/yyf/Project/qsitest_20260507/templateflow/tpl-MNI152NLin6Asym/tpl-MNI152NLin6Asym_res-02_T1w.nii.gz",
]
DEFAULT_ATLAS_CANDIDATES = [
    (
        "MNI152_HarvardOxford_cort_maxprob_thr25_2mm",
        "/home/yyf/project/MCI_project/tools/fsl/data/atlases/HarvardOxford/HarvardOxford-cort-maxprob-thr25-2mm.nii.gz",
    ),
    (
        "MNI152_HarvardOxford_cort_maxprob_thr25_2mm",
        "/home/yyf/nilearn_data/fsl/data/atlases/HarvardOxford/HarvardOxford-cort-maxprob-thr25-2mm.nii.gz",
    ),
    (
        "MNI152_Schaefer2018_200Parcels_7Networks",
        "/home/yyf/nilearn_data/schaefer_2018/Schaefer2018_200Parcels_7Networks_order_FSLMNI152_2mm.nii.gz",
    ),
    (
        "MNI152_Juelich_maxprob_thr25_2mm",
        "/home/yyf/nilearn_data/fsl/data/atlases/Juelich/Juelich-maxprob-thr25-2mm.nii.gz",
    ),
]


def _dwi_dir(dirs: dict) -> Path:
    return Path(dirs["bids"]) / f"sub-{SUBJECT}" / "dwi"


def required_inputs(dirs: dict) -> list[Path]:
    dwi_dir = _dwi_dir(dirs)
    return [
        dwi_dir / f"sub-{SUBJECT}_dwi.nii.gz",
        dwi_dir / f"sub-{SUBJECT}_dwi.bval",
        dwi_dir / f"sub-{SUBJECT}_dwi.bvec",
        dwi_dir / f"sub-{SUBJECT}_dwi.json",
    ]


def validate_inputs(dirs: dict) -> None:
    missing = [path.name for path in required_inputs(dirs) if not path.exists()]
    if missing:
        raise RuntimeError("DWI fast GPU DTI requires " + ", ".join(missing))


def _read_bvals(path: Path) -> list[float]:
    return [float(value) for value in Path(path).read_text(encoding="utf-8").split()]


def _read_bvec_rows(path: Path) -> list[list[str]]:
    rows = [line.split() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 3:
        raise RuntimeError("DWI bvec sidecar must contain exactly 3 rows")
    return rows


def select_dti_volume_indices(
    bvals: list[float],
    *,
    max_b0: int = 3,
    max_directions: int = 36,
    min_directions: int = 12,
) -> tuple[list[int], dict[str, Any]]:
    """Choose a lightweight b0 + single-shell subset suitable for DTI fitting."""
    b0_indices = [index for index, bval in enumerate(bvals) if bval <= 50]
    if not b0_indices:
        raise RuntimeError("DWI fast GPU DTI requires at least one b0 volume")
    diffusion_indices = [index for index, bval in enumerate(bvals) if bval > 50]
    if len(diffusion_indices) < min_directions:
        raise RuntimeError(f"DWI fast GPU DTI requires at least {min_directions} diffusion directions")

    preferred = [index for index in diffusion_indices if 700 <= bvals[index] <= 1300]
    strategy = "target_bval_window"
    if len(preferred) < min_directions:
        shell_counts: dict[int, list[int]] = {}
        for index in diffusion_indices:
            rounded = int(round(bvals[index] / 100.0) * 100)
            shell_counts.setdefault(rounded, []).append(index)
        shell, preferred = max(shell_counts.items(), key=lambda item: (len(item[1]), -abs(item[0] - 1000)))
        strategy = f"largest_shell_rounded_b{shell}"

    if len(preferred) > max_directions:
        step = len(preferred) / max_directions
        selected_diffusion = [preferred[min(int(i * step), len(preferred) - 1)] for i in range(max_directions)]
    else:
        selected_diffusion = preferred
    selected = [*b0_indices[:max_b0], *selected_diffusion]
    selected = sorted(dict.fromkeys(selected))
    metadata = {
        "selection_strategy": strategy,
        "full_volume_count": len(bvals),
        "selected_volume_count": len(selected),
        "selected_b0_count": sum(1 for index in selected if bvals[index] <= 50),
        "selected_diffusion_count": sum(1 for index in selected if bvals[index] > 50),
        "selected_bval_min": min(bvals[index] for index in selected),
        "selected_bval_max": max(bvals[index] for index in selected),
        "max_directions": max_directions,
    }
    return selected, metadata


def write_dti_subset(dwi: Path, bval: Path, bvec: Path, json_path: Path, work_dir: Path) -> dict[str, Path]:
    import nibabel as nib
    import numpy as np

    bvals = _read_bvals(bval)
    bvec_rows = _read_bvec_rows(bvec)
    if any(len(row) != len(bvals) for row in bvec_rows):
        raise RuntimeError("DWI bval and bvec volume counts do not match")
    selected, metadata = select_dti_volume_indices(bvals)
    work_dir.mkdir(parents=True, exist_ok=True)
    subset_base = work_dir / f"sub-{SUBJECT}_dti_subset"
    subset_dwi = subset_base.with_suffix(".nii.gz")
    subset_bval = subset_base.with_suffix(".bval")
    subset_bvec = subset_base.with_suffix(".bvec")
    subset_json = subset_base.with_suffix(".json")

    img = nib.load(str(dwi))
    data = np.asanyarray(img.dataobj)
    if data.ndim != 4:
        raise RuntimeError(f"expected 4D DWI data, got shape {data.shape}")
    if data.shape[3] != len(bvals):
        raise RuntimeError(f"DWI volume count {data.shape[3]} does not match bval count {len(bvals)}")
    subset_data = data[..., selected]
    nib.save(nib.Nifti1Image(subset_data, img.affine, img.header.copy()), str(subset_dwi))
    subset_bval.write_text(" ".join(f"{bvals[index]:g}" for index in selected) + "\n", encoding="utf-8")
    subset_bvec.write_text(
        "\n".join(" ".join(row[index] for index in selected) for row in bvec_rows) + "\n",
        encoding="utf-8",
    )
    meta = json.loads(json_path.read_text(encoding="utf-8"))
    meta["ImageAgentDtiSubset"] = {
        **metadata,
        "selected_indices": selected,
        "reason": "lightweight DTI feature extraction within the 35 minute production target",
    }
    subset_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"dwi": subset_dwi, "bval": subset_bval, "bvec": subset_bvec, "json": subset_json}


def resource_paths(dirs: dict) -> dict[str, Path]:
    resource_dir = Path(dirs["root"]) / RESOURCE_SUBDIR
    return {
        "resource_dir": resource_dir,
        "template": resource_dir / MNI_TEMPLATE_FILENAME,
        "atlas": resource_dir / MNI_ATLAS_FILENAME,
        "atlas_metadata": resource_dir / MNI_ATLAS_METADATA_FILENAME,
    }


def _is_nonempty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def _configured_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if _is_nonempty_file(path) else None


def _first_existing(paths: list[str]) -> Path | None:
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if _is_nonempty_file(path):
            return path
    return None


def _copy_resource(src: Path, dst: Path) -> None:
    if src.resolve() == dst.resolve():
        return
    shutil.copy2(src, dst)


def prepare_mni_resources(
    dirs: dict,
    *,
    template_loader: Any | None = None,
    atlas_fetcher: Any | None = None,
    nib_module: Any | None = None,
) -> dict[str, Path]:
    """Prepare host-side MNI resources and mount them into the toolbox container."""
    paths = resource_paths(dirs)
    paths["resource_dir"].mkdir(parents=True, exist_ok=True)

    if not paths["template"].exists():
        template_source = _configured_path("IMAGE_AGENT_DWI_DTI_MNI_TEMPLATE") or _first_existing(DEFAULT_TEMPLATE_CANDIDATES)
        if template_source is not None:
            _copy_resource(template_source, paths["template"])
        elif template_loader is None or nib_module is None:
            from nilearn import datasets
            import nibabel as nib

            template_loader = datasets.load_mni152_template
            nib_module = nib
            template_img = template_loader(resolution=2)
            nib_module.save(template_img, paths["template"])
        else:
            template_img = template_loader(resolution=2)
            nib_module.save(template_img, paths["template"])

    atlas_name = os.environ.get("IMAGE_AGENT_DWI_DTI_ATLAS", DEFAULT_ATLAS)
    atlas_source_for_metadata: Path | None = None
    if not paths["atlas"].exists():
        atlas_source = _configured_path("IMAGE_AGENT_DWI_DTI_ATLAS_PATH")
        if atlas_source is None:
            for candidate_name, candidate_path in DEFAULT_ATLAS_CANDIDATES:
                path = Path(candidate_path).expanduser()
                if _is_nonempty_file(path):
                    atlas_name = candidate_name
                    atlas_source = path
                    break
        if atlas_source is not None:
            _copy_resource(atlas_source, paths["atlas"])
            atlas_source_for_metadata = atlas_source
        elif atlas_fetcher is not None:
            atlas = atlas_fetcher("cort-maxprob-thr25-2mm", symmetric_split=False)
            atlas_maps = Path(str(atlas.maps))
            if not atlas_maps.exists():
                raise RuntimeError(f"Atlas fetch did not produce a file: {atlas_maps}")
            atlas_name = "MNI152_HarvardOxford_cort_maxprob_thr25_2mm"
            _copy_resource(atlas_maps, paths["atlas"])
            atlas_source_for_metadata = atlas_maps
        else:
            raise RuntimeError(
                "DWI fast GPU DTI requires an offline MNI atlas. Set IMAGE_AGENT_DWI_DTI_ATLAS_PATH "
                "or install a cached Schaefer/Juelich/HarvardOxford atlas under /home/yyf/nilearn_data."
            )
    elif paths["atlas_metadata"].exists():
        try:
            existing = json.loads(paths["atlas_metadata"].read_text(encoding="utf-8"))
            atlas_name = existing.get("atlas") or atlas_name
        except json.JSONDecodeError:
            pass

    paths["atlas_metadata"].write_text(
        json.dumps(
            {
                "atlas": atlas_name,
                "mounted_path": MNI_ATLAS,
                "source": str(atlas_source_for_metadata or _configured_path("IMAGE_AGENT_DWI_DTI_ATLAS_PATH") or paths["atlas"]),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    missing = [
        str(path)
        for key, path in paths.items()
        if key != "resource_dir" and not _is_nonempty_file(path)
    ]
    if missing:
        raise RuntimeError("DWI fast GPU DTI MNI resources missing after preparation: " + ", ".join(missing))
    return paths


def build_command(dirs: dict, image: str = IMAGE) -> list[str]:
    validate_inputs(dirs)
    resources = resource_paths(dirs)
    return [
        sys.executable,
        "-m",
        "app.workflows.dwi_fast_dti",
        "run",
        "--bids",
        str(Path(dirs["bids"])),
        "--out",
        str(Path(dirs["output"])),
        "--work",
        str(Path(dirs["work"])),
        "--resources",
        str(resources["resource_dir"]),
        "--fsl-dir",
        str(FSL_DIR),
        "--mrtrix-image",
        image,
        "--max-runtime-sec",
        str(MAX_RUNTIME_SEC),
        "--task-id",
        str(dirs.get("task_id", 0)),
        "--require-gpu-eddy",
    ]


def _run_logged(
    cmd: list[str],
    log_path: Path,
    *,
    timeout: float | None = None,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(str(part) for part in cmd) + "\n")
        proc = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )
        log.write(proc.stdout)
        if proc.stdout and not proc.stdout.endswith("\n"):
            log.write("\n")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed rc={proc.returncode}: {' '.join(str(part) for part in cmd)}")


def check_runtime(
    *,
    fsl_dir: Path = FSL_DIR,
    mrtrix_image: str = MRTRIX_IMAGE,
) -> tuple[bool, str]:
    details: list[str] = []
    try:
        for command in ("eddy_cuda", "dtifit", "flirt", "applywarp", "fslmaths"):
            resolved = _fsl_bin(fsl_dir, command)
            details.append(f"FSL {command}: {resolved}")
    except Exception as exc:
        return False, "\n".join(details + [f"FSL check failed: {exc}"])
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
    )
    details.append("nvidia-smi: " + gpu.stdout[-1000:])
    if gpu.returncode != 0:
        return False, "\n".join(details + [f"GPU check failed rc={gpu.returncode}"])

    password = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD")
    if not password:
        return False, "\n".join(details + ["IMAGE_AGENT_SUDO_PASSWORD is required for MRtrix toolbox checks"])
    probe = "for c in mrinfo mrconvert dwi2mask dwi2tensor tensor2metric mrstats mrcalc; do command -v $c || exit 3; done"
    cmd = [
        "sudo",
        "-S",
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "bash",
        mrtrix_image,
        "-lc",
        probe,
    ]
    proc = subprocess.run(
        cmd,
        input=password + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
    )
    details.append(f"MRtrix toolbox image: {mrtrix_image}")
    details.append(proc.stdout[-2000:])
    if proc.returncode != 0:
        return False, "\n".join(details + [f"MRtrix toolbox check failed rc={proc.returncode}"])
    details.append("full_qsiprep_run: false")
    details.append("full_qsirecon_run: false")
    details.append(f"max_runtime_sec: {MAX_RUNTIME_SEC}")
    return True, "\n".join(details)


def _remaining_timeout(start: float, max_runtime_sec: int) -> float:
    remaining = max_runtime_sec - (time.monotonic() - start)
    if remaining <= 0:
        raise TimeoutError(f"DWI fast GPU DTI exceeded {max_runtime_sec} seconds")
    return remaining


def _fsl_env(fsl_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["FSLDIR"] = str(fsl_dir)
    env["FSLOUTPUTTYPE"] = "NIFTI_GZ"
    env["PATH"] = f"{fsl_dir / 'bin'}{os.pathsep}{fsl_dir / 'share' / 'fsl' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["LD_LIBRARY_PATH"] = f"{fsl_dir / 'lib'}{os.pathsep}{env.get('LD_LIBRARY_PATH', '')}"
    return env


def _fsl_bin(fsl_dir: Path, name: str) -> Path:
    for candidate in (fsl_dir / "bin" / name, fsl_dir / "share" / "fsl" / "bin" / name):
        if candidate.exists():
            return candidate
    raise RuntimeError(f"FSL command not found under {fsl_dir}: {name}")


def _sudo_password() -> str:
    password = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD")
    if not password:
        raise RuntimeError("IMAGE_AGENT_SUDO_PASSWORD is required for the MRtrix toolbox container")
    return password


def _mrtrix_command(
    image: str,
    bids_dir: Path,
    out_dir: Path,
    work_dir: Path,
    command: str,
) -> list[str]:
    return [
        "sudo",
        "-S",
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--network",
        "host",
        "-v",
        f"{bids_dir}:/data:ro",
        "-v",
        f"{out_dir}:/out",
        "-v",
        f"{work_dir}:/work",
        "--entrypoint",
        "bash",
        image,
        "-lc",
        command,
    ]


def _write_eddy_files(json_path: Path, bval_path: Path, work_dir: Path) -> None:
    meta = json.loads(Path(json_path).read_text(encoding="utf-8"))
    ped = meta.get("PhaseEncodingDirection")
    trt = meta.get("TotalReadoutTime")
    if ped is None or trt is None:
        raise RuntimeError("missing PhaseEncodingDirection or TotalReadoutTime")
    axis = ped[0]
    if axis not in {"i", "j", "k"}:
        raise RuntimeError(f"unsupported PhaseEncodingDirection: {ped}")
    sign = -1 if ped.endswith("-") else 1
    vec = {"i": [1, 0, 0], "j": [0, 1, 0], "k": [0, 0, 1]}[axis]
    vec = [value * sign for value in vec]
    bvals = Path(bval_path).read_text(encoding="utf-8").split()
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "acqparams.txt").write_text(" ".join(str(value) for value in vec) + f" {float(trt):.7f}\n", encoding="utf-8")
    (work_dir / "index.txt").write_text(" ".join(["1"] * len(bvals)) + "\n", encoding="utf-8")


def _derive_fallback_mask(dwi_path: Path, mask_path: Path, qc_dir: Path) -> None:
    import nibabel as nib
    import numpy as np
    from scipy import ndimage

    img = nib.load(str(dwi_path))
    data = np.asarray(img.dataobj, dtype=np.float32)
    if data.ndim != 4:
        raise RuntimeError(f"expected 4D DWI data, got shape {data.shape}")
    mean_img = np.nanmean(np.clip(data, 0, None), axis=3)
    finite = np.isfinite(mean_img)
    positive = mean_img[finite & (mean_img > 0)]
    if positive.size == 0:
        raise RuntimeError("cannot derive fallback mask from empty/zero DWI data")
    threshold = max(float(np.percentile(positive, 20)), float(positive.mean() * 0.05))
    mask_data = finite & (mean_img > threshold)
    mask_data = ndimage.binary_opening(mask_data, iterations=1)
    mask_data = ndimage.binary_closing(mask_data, iterations=2)
    labels, count = ndimage.label(mask_data)
    if count > 0:
        sizes = ndimage.sum(mask_data, labels, index=np.arange(1, count + 1))
        mask_data = labels == int(np.argmax(sizes) + 1)
    if int(mask_data.sum()) < 64:
        mask_data = finite & (mean_img > float(np.percentile(positive, 10)))
    if int(mask_data.sum()) < 64:
        raise RuntimeError(f"fallback mask too small: {int(mask_data.sum())} voxels")
    nib.save(nib.Nifti1Image(mask_data.astype(np.uint8), img.affine, img.header.copy()), str(mask_path))
    qc_dir.mkdir(parents=True, exist_ok=True)
    (qc_dir / "mask_fallback.json").write_text(
        json.dumps(
            {
                "method": "mean_dwi_percentile_fallback",
                "threshold": threshold,
                "voxel_count": int(mask_data.sum()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_region_tables(out_dir: Path, atlas_metadata_path: Path) -> None:
    import nibabel as nib
    import numpy as np

    maps_dir = out_dir / "maps"
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(atlas_metadata_path.read_text(encoding="utf-8"))
    atlas_name = metadata.get("atlas", DEFAULT_ATLAS)
    atlas_img = nib.load(str(atlas_metadata_path.parent / MNI_ATLAS_FILENAME))
    atlas_data = np.asarray(atlas_img.dataobj, dtype=np.int32)
    labels = [int(value) for value in sorted(np.unique(atlas_data)) if int(value) > 0]
    metrics: dict[str, Any] = {}
    for metric in DTI_METRICS:
        metric_data = np.asarray(nib.load(str(maps_dir / f"{metric}_mni152.nii.gz")).dataobj, dtype=np.float32)
        if metric_data.shape != atlas_data.shape:
            raise RuntimeError(f"{metric} MNI shape {metric_data.shape} does not match atlas shape {atlas_data.shape}")
        metrics[metric] = metric_data
        with (tables_dir / f"{metric}_regions.tsv").open("w", encoding="utf-8") as f:
            f.write("region\tatlas_index\tmetric\tmean\tstd\tvoxel_count\tatlas\n")
            for label in labels:
                values = metric_data[atlas_data == label]
                values = values[np.isfinite(values)]
                if values.size:
                    f.write(
                        f"{atlas_name}_{label}\t{label}\t{metric.upper()}\t"
                        f"{float(values.mean()):.8g}\t{float(values.std()):.8g}\t{int(values.size)}\t{atlas_name}\n"
                    )
    with (tables_dir / "combined_region_dti.tsv").open("w", encoding="utf-8") as f:
        f.write("region\tatlas_index\tfa\tmd\tad\trd\tvoxel_count\tatlas\n")
        for label in labels:
            values_by_metric = []
            count = 0
            for metric in DTI_METRICS:
                values = metrics[metric][atlas_data == label]
                values = values[np.isfinite(values)]
                count = max(count, int(values.size))
                values_by_metric.append(float(values.mean()) if values.size else float("nan"))
            f.write(
                f"{atlas_name}_{label}\t{label}\t{values_by_metric[0]:.8g}\t{values_by_metric[1]:.8g}\t"
                f"{values_by_metric[2]:.8g}\t{values_by_metric[3]:.8g}\t{count}\t{atlas_name}\n"
            )


def _valid_affine_matrix(path: Path) -> bool:
    try:
        rows = [
            [float(value) for value in line.split()]
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception:
        return False
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        return False
    if not all(math.isfinite(value) for row in rows for value in row):
        return False
    try:
        a = rows
        det3 = (
            a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
            - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
        )
        return abs(det3) > 1e-8
    except Exception:
        return False


def _mni_map_has_signal(path: Path, template_path: Path) -> bool:
    if not Path(path).exists():
        return False

    import nibabel as nib
    import numpy as np

    try:
        img = nib.load(str(path))
        template = nib.load(str(template_path))
        data = np.asarray(img.dataobj)
    except Exception:
        return False
    if img.shape[:3] != template.shape[:3]:
        return False
    finite = data[np.isfinite(data)]
    return bool(finite.size and np.count_nonzero(finite) > 0)


def _sanitize_metric_map(path: Path) -> dict[str, Any]:
    import nibabel as nib
    import numpy as np

    path = Path(path)
    img = nib.load(str(path))
    data = np.asarray(img.dataobj, dtype=np.float32)
    finite = np.isfinite(data)
    nonfinite_count = int((~finite).sum())
    if nonfinite_count:
        cleaned = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        if path.name.endswith(".nii.gz"):
            tmp_path = path.with_name(f".{path.name[:-7]}.sanitize.tmp.nii.gz")
        elif path.name.endswith(".nii"):
            tmp_path = path.with_name(f".{path.name[:-4]}.sanitize.tmp.nii")
        else:
            tmp_path = path.with_name(f".{path.name}.sanitize.tmp.nii.gz")
        try:
            nib.save(nib.Nifti1Image(cleaned, img.affine, img.header.copy()), str(tmp_path))
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
    return {
        "path": str(path),
        "nonfinite_replaced": nonfinite_count,
    }


def _sanitize_metric_maps(maps_dir: Path, suffix: str = "") -> dict[str, dict[str, Any]]:
    return {
        metric: _sanitize_metric_map(maps_dir / f"{metric}{suffix}.nii.gz")
        for metric in DTI_METRICS
    }


def _resample_metric_to_mni(metric_path: Path, template_path: Path, out_path: Path) -> None:
    import nibabel as nib
    from nilearn.image import resample_to_img

    metric_img = nib.load(str(metric_path))
    template_img = nib.load(str(template_path))
    resampled = resample_to_img(
        metric_img,
        template_img,
        interpolation="linear",
        force_resample=True,
        copy_header=True,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(resampled, str(out_path))


def _register_metrics_to_mni(
    maps_dir: Path,
    template: Path,
    *,
    flirt: Path,
    log_path: Path,
    timeout_start: float,
    max_runtime_sec: int,
    env: dict[str, str],
) -> dict[str, Any]:
    affine_mat = maps_dir / "dwi_to_mni_affine.mat"
    registration_attempts: list[dict[str, Any]] = []
    registration_method = "header_resample_fallback"
    for attempt in FLIRT_REGISTRATION_ATTEMPTS:
        cmd = [
            str(flirt),
            "-in",
            str(maps_dir / "fa.nii.gz"),
            "-ref",
            str(template),
            "-omat",
            str(affine_mat),
            "-out",
            str(maps_dir / "fa_mni152.nii.gz"),
            *attempt["args"],
        ]
        _run_logged(
            cmd,
            log_path,
            timeout=_remaining_timeout(timeout_start, max_runtime_sec),
            env=env,
        )
        affine_valid = _valid_affine_matrix(affine_mat)
        fa_has_signal = _mni_map_has_signal(maps_dir / "fa_mni152.nii.gz", template)
        registration_attempts.append(
            {
                "method": attempt["method"],
                "affine_matrix_valid": affine_valid,
                "fa_mni152_has_signal": fa_has_signal,
            }
        )
        if affine_valid and fa_has_signal:
            registration_method = attempt["method"]
            break

    if registration_method == "header_resample_fallback":
        registration_method = "header_resample_fallback"
        for metric in DTI_METRICS:
            _resample_metric_to_mni(maps_dir / f"{metric}.nii.gz", template, maps_dir / f"{metric}_mni152.nii.gz")
    else:
        for metric in ("md", "ad", "rd"):
            _run_logged(
                [
                    str(flirt),
                    "-in",
                    str(maps_dir / f"{metric}.nii.gz"),
                    "-ref",
                    str(template),
                    "-applyxfm",
                    "-init",
                    str(affine_mat),
                    "-out",
                    str(maps_dir / f"{metric}_mni152.nii.gz"),
                ],
                log_path,
                timeout=_remaining_timeout(timeout_start, max_runtime_sec),
                env=env,
            )
            if not _mni_map_has_signal(maps_dir / f"{metric}_mni152.nii.gz", template):
                _resample_metric_to_mni(maps_dir / f"{metric}.nii.gz", template, maps_dir / f"{metric}_mni152.nii.gz")
                registration_method = "flirt_affine_with_metric_resample_fallback"
    return {
        "mni_registration_method": registration_method,
        "affine_matrix_valid": _valid_affine_matrix(affine_mat),
        "mni_registration_attempts": registration_attempts,
    }


def run_fast_dti(
    bids_dir: Path,
    out_dir: Path,
    work_dir: Path,
    resources_dir: Path,
    *,
    fsl_dir: Path = FSL_DIR,
    mrtrix_image: str = MRTRIX_IMAGE,
    max_runtime_sec: int = MAX_RUNTIME_SEC,
    require_gpu_eddy: bool = True,
    task_id: int = 0,
) -> Path:
    start = time.monotonic()
    bids_dir = Path(bids_dir)
    out_dir = Path(out_dir)
    work_dir = Path(work_dir)
    resources_dir = Path(resources_dir)
    maps_dir = out_dir / "maps"
    qc_dir = out_dir / "qc"
    for path in (maps_dir, qc_dir, work_dir):
        path.mkdir(parents=True, exist_ok=True)
    log_path = qc_dir / "dwi_fast_gpu_dti_runner.log"

    dwi_dir = bids_dir / f"sub-{SUBJECT}" / "dwi"
    dwi = dwi_dir / f"sub-{SUBJECT}_dwi.nii.gz"
    bval = dwi_dir / f"sub-{SUBJECT}_dwi.bval"
    bvec = dwi_dir / f"sub-{SUBJECT}_dwi.bvec"
    json_path = dwi_dir / f"sub-{SUBJECT}_dwi.json"
    validate_inputs({"bids": bids_dir})
    prepare_mni_resources({"root": resources_dir.parent})
    subset = write_dti_subset(dwi, bval, bvec, json_path, work_dir)
    _write_eddy_files(subset["json"], subset["bval"], work_dir)
    shutil.copy2(subset["json"], qc_dir / "input_metadata.json")

    password = _sudo_password()
    try:
        _run_logged(
            _mrtrix_command(
                mrtrix_image,
                bids_dir,
                out_dir,
                work_dir,
                (
                    'dwi2mask /work/sub-01_dti_subset.nii.gz /out/maps/mask.mif '
                    '-fslgrad /work/sub-01_dti_subset.bvec /work/sub-01_dti_subset.bval -force && '
                    'mrconvert /out/maps/mask.mif /out/maps/mask.nii.gz -force'
                ),
            ),
            log_path,
            timeout=_remaining_timeout(start, max_runtime_sec),
            input_text=password + "\n",
        )
    except Exception:
        _derive_fallback_mask(subset["dwi"], maps_dir / "mask.nii.gz", qc_dir)
        _run_logged(
            _mrtrix_command(
                mrtrix_image,
                bids_dir,
                out_dir,
                work_dir,
                "mrconvert /out/maps/mask.nii.gz /out/maps/mask.mif -force",
            ),
            log_path,
            timeout=_remaining_timeout(start, max_runtime_sec),
            input_text=password + "\n",
        )

    eddy_cuda = _fsl_bin(fsl_dir, "eddy_cuda")
    eddy_cmd = [
        str(eddy_cuda),
        f"--imain={subset['dwi']}",
        f"--mask={maps_dir / 'mask.nii.gz'}",
        f"--acqp={work_dir / 'acqparams.txt'}",
        f"--index={work_dir / 'index.txt'}",
        f"--bvecs={subset['bvec']}",
        f"--bvals={subset['bval']}",
        f"--out={maps_dir / 'eddy_corrected'}",
        "--data_is_shelled",
        "--dont_peas",
        "--repol",
        "--niter=3",
        "--fwhm=0",
        "--flm=quadratic",
        "--slm=none",
        "--resamp=jac",
        "--interp=spline",
        "--nthr=1",
        "--verbose",
    ]
    if require_gpu_eddy and "eddy_cuda" not in eddy_cuda.name:
        raise RuntimeError(f"GPU eddy is required; resolved non-CUDA eddy command: {eddy_cuda}")
    fsl_env = _fsl_env(fsl_dir)
    _run_logged(eddy_cmd, log_path, timeout=_remaining_timeout(start, max_runtime_sec), env=fsl_env)

    _run_logged(
        _mrtrix_command(
            mrtrix_image,
            bids_dir,
            out_dir,
            work_dir,
            (
                'dwi2tensor /out/maps/eddy_corrected.nii.gz /out/maps/dti_tensor.mif '
                '-fslgrad /out/maps/eddy_corrected.eddy_rotated_bvecs /work/sub-01_dti_subset.bval '
                '-mask /out/maps/mask.mif -force && '
                'tensor2metric /out/maps/dti_tensor.mif '
                '-fa /out/maps/fa.nii.gz -adc /out/maps/md.nii.gz '
                '-ad /out/maps/ad.nii.gz -rd /out/maps/rd.nii.gz -force'
            ),
        ),
        log_path,
        timeout=_remaining_timeout(start, max_runtime_sec),
        input_text=password + "\n",
    )
    native_metric_sanitization = _sanitize_metric_maps(maps_dir)

    template = resources_dir / MNI_TEMPLATE_FILENAME
    registration_provenance = _register_metrics_to_mni(
        maps_dir,
        template,
        flirt=_fsl_bin(fsl_dir, "flirt"),
        log_path=log_path,
        timeout_start=start,
        max_runtime_sec=max_runtime_sec,
        env=fsl_env,
    )
    mni_metric_sanitization = _sanitize_metric_maps(maps_dir, suffix="_mni152")

    _write_region_tables(out_dir, resources_dir / MNI_ATLAS_METADATA_FILENAME)
    elapsed = int(time.monotonic() - start)
    (qc_dir / "qc_report.tsv").write_text(
        "metric\tstatus\n"
        "gpu_eddy\tcompleted\n"
        "tensor\tcompleted\n"
        "mni_registration\tcompleted\n"
        "atlas_statistics\tcompleted\n"
        f"runtime_sec\t{elapsed}\n"
        f"runtime_limit_sec\t{max_runtime_sec}\n",
        encoding="utf-8",
    )
    (qc_dir / "dwi_fast_gpu_dti_provenance.json").write_text(
        json.dumps(
            {
                "basis_script": "/home/yyf/project/MCI_project/scripts/run_fast_gpu_dti_features.sh",
                "mrtrix_toolbox_image": mrtrix_image,
                "fsl_dir": str(fsl_dir),
                "gpu_eddy": str(eddy_cuda),
                "runtime_sec": elapsed,
                "max_runtime_sec": max_runtime_sec,
                "dti_subset_metadata": json.loads(subset["json"].read_text(encoding="utf-8")).get("ImageAgentDtiSubset", {}),
                "metric_sanitization": {
                    "native": native_metric_sanitization,
                    "mni152": mni_metric_sanitization,
                },
                **registration_provenance,
                "full_qsiprep_run": False,
                "full_qsirecon_run": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return write_result_summary_from_outputs(out_dir, task_id=task_id, workflow_type="dwi_fast_gpu_dti")


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight fast GPU DTI feature extraction.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--bids", required=True, type=Path)
    run_parser.add_argument("--out", required=True, type=Path)
    run_parser.add_argument("--work", required=True, type=Path)
    run_parser.add_argument("--resources", required=True, type=Path)
    run_parser.add_argument("--fsl-dir", required=True, type=Path)
    run_parser.add_argument("--mrtrix-image", required=True)
    run_parser.add_argument("--max-runtime-sec", required=True, type=int)
    run_parser.add_argument("--task-id", type=int, default=0)
    run_parser.add_argument("--require-gpu-eddy", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run":
        run_fast_dti(
            bids_dir=args.bids,
            out_dir=args.out,
            work_dir=args.work,
            resources_dir=args.resources,
            fsl_dir=args.fsl_dir,
            mrtrix_image=args.mrtrix_image,
            max_runtime_sec=args.max_runtime_sec,
            require_gpu_eddy=args.require_gpu_eddy,
            task_id=args.task_id,
        )
        return 0
    raise RuntimeError(f"unsupported command: {args.command}")


def write_validate_outputs(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    tables_dir = out_dir / "tables"
    qc_dir = out_dir / "qc"
    for path in (maps_dir, tables_dir, qc_dir):
        path.mkdir(parents=True, exist_ok=True)

    for metric in DTI_METRICS:
        metric_map = maps_dir / f"{metric}.nii.gz"
        metric_mni_map = maps_dir / f"{metric}_mni152.nii.gz"
        if not metric_map.exists():
            metric_map.write_bytes(b"validate-placeholder-nifti")
        if not metric_mni_map.exists():
            metric_mni_map.write_bytes(b"validate-placeholder-nifti")
        metric_table = tables_dir / f"{metric}_regions.tsv"
        if not metric_table.exists():
            metric_table.write_text(
                f"region\tmetric\tmean\tatlas\nwhole_white_matter\t{metric.upper()}\t0.0\t{DEFAULT_ATLAS}\n",
                encoding="utf-8",
            )
    combined = tables_dir / "combined_region_dti.tsv"
    if not combined.exists():
        combined.write_text(
            "region\tfa\tmd\tad\trd\tatlas\n"
            f"whole_white_matter\t0.0\t0.0\t0.0\t0.0\t{DEFAULT_ATLAS}\n",
            encoding="utf-8",
        )
    qc_report = qc_dir / "qc_report.tsv"
    qc_report.write_text("check\tstatus\nvalidate\tplanned\n", encoding="utf-8")
    provenance = qc_dir / "dwi_fast_gpu_dti_provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "image": IMAGE,
                "script_source": "/home/yyf/project/MCI_project/scripts/run_fast_gpu_dti_features.sh",
                "atlas": DEFAULT_ATLAS,
                "method": "validate_output_contract",
                "validation_only": True,
                "placeholder_outputs": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    maps = [
        {"name": metric, "path": maps_dir / f"{metric}.nii.gz", "space": "DWI"}
        for metric in DTI_METRICS
    ] + [
        {"name": f"{metric}_mni152", "path": maps_dir / f"{metric}_mni152.nii.gz", "space": "MNI152"}
        for metric in DTI_METRICS
    ]
    tables = [{"name": "combined_region_dti", "path": combined, "space": "MNI152", "atlas": DEFAULT_ATLAS}]
    tables.extend({"name": f"{metric}_regions", "path": tables_dir / f"{metric}_regions.tsv", "space": "MNI152", "atlas": DEFAULT_ATLAS} for metric in DTI_METRICS)
    native_qc = discover_native_qc_outputs(out_dir, workflow_type)
    return build_result_summary(
        out_dir=out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality="DWI",
        spaces=["DWI", "MNI152"],
        feature_groups=["tensor_metrics", "mni152_registration", "atlas_statistics", "quality_control"],
        outputs={
            "maps": maps,
            "tables": tables,
            "qc": [{"name": "qc_report", "path": qc_report}, {"name": "provenance", "path": provenance}],
            **native_qc,
        },
        provenance={
            "method": "fast_gpu_dti_validate_contract",
            "tool_container": IMAGE,
            "basis_script": "/home/yyf/project/MCI_project/scripts/run_fast_gpu_dti_features.sh",
            "validation_only": True,
            "placeholder_outputs": True,
        },
    )


def write_result_summary_from_outputs(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    tables_dir = out_dir / "tables"
    qc_dir = out_dir / "qc"
    atlas = DEFAULT_ATLAS
    atlas_metadata = out_dir.parent / RESOURCE_SUBDIR / MNI_ATLAS_METADATA_FILENAME
    if atlas_metadata.exists():
        try:
            atlas = json.loads(atlas_metadata.read_text(encoding="utf-8")).get("atlas") or atlas
        except json.JSONDecodeError:
            pass
    required = [
        *(maps_dir / f"{metric}.nii.gz" for metric in DTI_METRICS),
        *(maps_dir / f"{metric}_mni152.nii.gz" for metric in DTI_METRICS),
        tables_dir / "combined_region_dti.tsv",
        *(tables_dir / f"{metric}_regions.tsv" for metric in DTI_METRICS),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("DWI fast GPU DTI finished without required real outputs: " + ", ".join(missing))

    maps = [
        {"name": metric, "path": maps_dir / f"{metric}.nii.gz", "space": "DWI"}
        for metric in DTI_METRICS
    ] + [
        {"name": f"{metric}_mni152", "path": maps_dir / f"{metric}_mni152.nii.gz", "space": "MNI152"}
        for metric in DTI_METRICS
    ]
    tables = [{"name": "combined_region_dti", "path": tables_dir / "combined_region_dti.tsv", "space": "MNI152", "atlas": atlas}]
    tables.extend(
        {"name": f"{metric}_regions", "path": tables_dir / f"{metric}_regions.tsv", "space": "MNI152", "atlas": atlas}
        for metric in DTI_METRICS
    )
    qc = []
    for path in sorted(qc_dir.glob("*")):
        if path.is_file():
            qc.append({"name": path.stem, "path": path})
    provenance_payload: dict[str, Any] = {}
    provenance_path = qc_dir / "dwi_fast_gpu_dti_provenance.json"
    if provenance_path.exists():
        try:
            provenance_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            provenance_payload = {}
    qc_metrics: dict[str, str] = {}
    qc_report = qc_dir / "qc_report.tsv"
    if qc_report.exists():
        for line in qc_report.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t", 1)
            if len(parts) == 2:
                qc_metrics[parts[0]] = parts[1]
    runtime_sec = provenance_payload.get("runtime_sec")
    if runtime_sec is None and qc_metrics.get("runtime_sec"):
        runtime_sec = int(float(qc_metrics["runtime_sec"]))
    max_runtime_sec = provenance_payload.get("max_runtime_sec")
    if max_runtime_sec is None and qc_metrics.get("runtime_limit_sec"):
        max_runtime_sec = int(float(qc_metrics["runtime_limit_sec"]))

    native_qc = discover_native_qc_outputs(out_dir, workflow_type)
    return build_result_summary(
        out_dir=out_dir,
        task_id=task_id,
        workflow_type=workflow_type,
        modality="DWI",
        spaces=["DWI", "MNI152"],
        feature_groups=["tensor_metrics", "mni152_registration", "atlas_statistics", "quality_control"],
        outputs={"maps": maps, "tables": tables, "qc": qc, **native_qc},
        provenance={
            "method": "fast_gpu_dti_real_outputs",
            "tool_container": IMAGE,
            "basis_script": "/home/yyf/project/MCI_project/scripts/run_fast_gpu_dti_features.sh",
            "validation_only": False,
            "atlas": atlas,
            "runtime_sec": runtime_sec,
            "max_runtime_sec": max_runtime_sec,
            "dti_subset_metadata": provenance_payload.get("dti_subset_metadata", {}),
            "mni_registration_method": provenance_payload.get("mni_registration_method"),
            "mni_registration_attempts": provenance_payload.get("mni_registration_attempts", []),
            "metric_sanitization": provenance_payload.get("metric_sanitization", {}),
        },
    )


def write_scientific_report_summary_from_outputs(out_dir: Path, task_id: int, workflow_type: str) -> Path:
    summary_path = write_result_summary_from_outputs(out_dir, task_id=task_id, workflow_type=workflow_type)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return build_scientific_report_summary(out_dir, task_id=task_id, workflow_type=workflow_type, summary=summary)


if __name__ == "__main__":  # pragma: no cover - exercised by pipeline subprocess
    raise SystemExit(_main())
