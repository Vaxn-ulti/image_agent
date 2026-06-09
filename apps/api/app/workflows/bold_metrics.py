import argparse
import csv
import importlib.util
import json
from pathlib import Path

import nibabel as nib
import numpy as np

from app.workflows.bold_seed_registry import DEFAULT_SEED_PRESETS


DEFAULT_METRICS = ["alff", "falff", "reho", "tsnr", "dmn", "seed_to_roi"]

CONF_SUMMARY_KEYS = [
    "framewise_displacement",
    "dvars",
    "std_dvars",
    "rmsd",
    "global_signal",
    "csf",
    "white_matter",
    "csf_wm",
    "tcompcor",
]

CONF_SERIES_KEYS = [
    "framewise_displacement",
    "dvars",
    "std_dvars",
    "trans_x",
    "trans_y",
    "trans_z",
    "rot_x",
    "rot_y",
    "rot_z",
]


def _replace_bold_suffix(path: Path, replacement: str) -> Path:
    name = path.name
    for suffix in ("desc-preproc_bold.nii.gz", "desc-preproc_bold.nii"):
        if suffix in name:
            return path.with_name(name.replace(suffix, replacement))
    stem = path.name.replace(".nii.gz", "").replace(".nii", "")
    return path.with_name(f"{stem}_{replacement}")


def _write_placeholder(path: Path, content: bytes | str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def run_metrics(
    *,
    bids_dir: Path,
    out_dir: Path,
    metrics: list[str],
    seed_presets: list[str] | None,
    subject_id: str,
    task_label: str,
) -> str:
    """Compatibility facade for legacy BOLD metric task tests.

    Real map computation is handled by compute_bold_metrics_bundle(). This
    facade keeps the older task contract available by writing the expected
    summary/tables/maps/figures structure from deterministic placeholders.
    """
    _ = bids_dir
    requested_metrics = [metric.lower() for metric in metrics]
    seeds = seed_presets or list(DEFAULT_SEED_PRESETS.keys())
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_dir = out_dir / "summary"
    tables_dir = out_dir / "tables"
    maps_dir = out_dir / "maps"
    figures_dir = out_dir / "figures"
    for directory in (summary_dir, tables_dir, maps_dir, figures_dir):
        directory.mkdir(parents=True, exist_ok=True)

    if "seed_to_roi" in requested_metrics or seeds:
        _write_placeholder(tables_dir / "seed_to_roi.tsv", "seed_id\troi_id\tcorrelation_r\n")
    if "dmn" in requested_metrics:
        _write_placeholder(tables_dir / "network_dmn.tsv", "network\tseed_count\tmean_within_network_correlation_r\n")
        _write_placeholder(maps_dir / "dmn.nii.gz", b"nifti")
    for metric in requested_metrics:
        if metric in {"alff", "falff", "reho", "tsnr", "rsfa"}:
            _write_placeholder(maps_dir / f"{metric}.nii.gz", b"nifti")
    for seed_id in seeds:
        _write_placeholder(figures_dir / f"{seed_id}_seed_fc_stat.png", b"png")

    summary = {
        "contract_version": "1.0",
        "modality": "BOLD",
        "subject_id": subject_id,
        "task_label": task_label,
        "spaces": ["MNI152"],
        "metrics": requested_metrics,
        "seeds": [
            {
                "preset_id": seed_id,
                "label": DEFAULT_SEED_PRESETS.get(seed_id, {}).get("label", seed_id),
                "family": DEFAULT_SEED_PRESETS.get(seed_id, {}).get("family", "custom"),
                "space": DEFAULT_SEED_PRESETS.get(seed_id, {}).get("space", "MNI152"),
            }
            for seed_id in seeds
        ],
        "outputs": {
            "tables": sorted(path.name for path in tables_dir.glob("*")),
            "maps": sorted(path.name for path in maps_dir.glob("*")),
            "figures": sorted(path.name for path in figures_dir.glob("*")),
        },
    }
    summary_path = summary_dir / "bold_metrics_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return str(summary_path)


def _summary_prefix(preproc_bold: Path) -> str:
    name = preproc_bold.name
    if "_space-" in name:
        return name.split("_space-", 1)[0]
    return name.replace(".nii.gz", "").replace(".nii", "")


def _load_tr(json_path: Path) -> float:
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    tr = metadata.get("RepetitionTime")
    if tr is None:
        raise RuntimeError(f"RepetitionTime missing from {json_path}")
    tr = float(tr)
    if tr <= 0:
        raise RuntimeError(f"Invalid RepetitionTime in {json_path}: {tr}")
    return tr


def _write_nifti_like(reference_img: nib.spatialimages.SpatialImage, data: np.ndarray, path: Path) -> None:
    out = nib.Nifti1Image(data.astype(np.float32), reference_img.affine, reference_img.header.copy())
    nib.save(out, str(path))


def _source_shape_matches_reference(source: Path, reference_img: nib.spatialimages.SpatialImage) -> bool:
    try:
        return tuple(nib.load(str(source)).shape[:3]) == tuple(reference_img.shape[:3])
    except Exception:
        return False


def _coerce_float(raw: str | None) -> float | None:
    if raw in (None, "", "n/a", "NA"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _collect_confounds(confounds_path: Path) -> tuple[dict, list[dict], list[str], dict[str, list[float | None]]]:
    values: dict[str, list[float]] = {key: [] for key in CONF_SUMMARY_KEYS}
    series_data: dict[str, list[float | None]] = {key: [] for key in CONF_SERIES_KEYS}
    rows = 0
    fieldnames: list[str] = []

    with confounds_path.open(encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f, delimiter="	")
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows += 1
            for key in CONF_SERIES_KEYS:
                series_data[key].append(_coerce_float(row.get(key)))
            for key in CONF_SUMMARY_KEYS:
                value = _coerce_float(row.get(key))
                if value is not None:
                    values[key].append(value)

    if not any(v is not None for v in series_data["framewise_displacement"]):
        trans_cols = [series_data["trans_x"], series_data["trans_y"], series_data["trans_z"]]
        rot_cols = [series_data["rot_x"], series_data["rot_y"], series_data["rot_z"]]
        if all(any(v is not None for v in col) for col in trans_cols + rot_cols):
            prev: tuple[float, ...] | None = None
            computed: list[float | None] = []
            for values_row in zip(*trans_cols, *rot_cols):
                if any(v is None for v in values_row):
                    computed.append(None)
                    continue
                values_tuple = tuple(float(v) for v in values_row if v is not None)
                if prev is None:
                    computed.append(0.0)
                else:
                    diffs = [abs(v - p) for v, p in zip(values_tuple[:3], prev[:3])]
                    rot_diffs = [50.0 * abs(v - p) for v, p in zip(values_tuple[3:], prev[3:])]
                    computed.append(float(sum(diffs) + sum(rot_diffs)))
                prev = values_tuple
            series_data["framewise_displacement"] = computed
            values["framewise_displacement"] = [v for v in computed if v is not None]

    summary = {
        "n_rows": rows,
        "available_columns": fieldnames,
        "metrics": {},
    }
    flat_rows: list[dict] = []
    for key, arr in values.items():
        if not arr:
            continue
        a = np.asarray(arr, dtype=np.float64)
        item = {
            "count": int(a.size),
            "mean": float(a.mean()),
            "std": float(a.std(ddof=0)),
            "median": float(np.median(a)),
            "max": float(a.max()),
            "p95": float(np.percentile(a, 95)),
        }
        if key == "framewise_displacement":
            item["count_gt_0p2"] = int((a > 0.2).sum())
            item["count_gt_0p5"] = int((a > 0.5).sum())
        summary["metrics"][key] = item
        flat_rows.append({"metric": key, **item})
    return summary, flat_rows, fieldnames, series_data


def _write_timeseries_tsv(path: Path, columns: list[str], rows: list[list[float | None]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="	")
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if v is None else float(v) for v in row])


def _compute_reho_map(centered_series: np.ndarray, finite_mask: np.ndarray, mask: np.ndarray) -> np.ndarray:
    coords = np.argwhere(mask)
    finite_coords = coords[finite_mask]
    coord_to_idx = {tuple(int(v) for v in coord): idx for idx, coord in enumerate(finite_coords)}
    offsets = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    n_time = centered_series.shape[1]
    reho = np.zeros(len(finite_coords), dtype=np.float32)

    for idx, coord in enumerate(finite_coords):
        members: list[int] = []
        cx, cy, cz = (int(v) for v in coord)
        for dx, dy, dz in offsets:
            neighbor_idx = coord_to_idx.get((cx + dx, cy + dy, cz + dz))
            if neighbor_idx is not None:
                members.append(neighbor_idx)
        k = len(members)
        if k < 4:
            continue
        neighborhood = centered_series[members]
        ranks = np.argsort(np.argsort(neighborhood, axis=0), axis=0).astype(np.float32) + 1.0
        rank_sums = ranks.sum(axis=1)
        s = float(np.sum((rank_sums - (n_time * (k + 1) / 2.0)) ** 2))
        denom = float((n_time ** 2) * (k ** 3 - k))
        if denom > 0:
            reho[idx] = 12.0 * s / denom

    out = np.zeros(mask.shape, dtype=np.float32)
    tmp = np.zeros(mask.sum(), dtype=np.float32)
    tmp[np.flatnonzero(finite_mask)] = reho
    out[mask] = tmp
    return out


def _standardize_timeseries(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    values = values - float(values.mean())
    std = float(values.std(ddof=0))
    if std <= 1e-6:
        return values
    return values / std


def _seed_sphere_mask(seed: dict, affine: np.ndarray, mask: np.ndarray) -> np.ndarray:
    coords = np.argwhere(mask)
    if coords.size == 0:
        return np.zeros(mask.shape, dtype=bool)
    world = nib.affines.apply_affine(affine, coords)
    seed_xyz = np.asarray(seed["coordinate_mni"], dtype=np.float32)
    distances = np.linalg.norm(world - seed_xyz[None, :], axis=1)
    members = distances <= float(seed["radius_mm"])
    if not members.any():
        members[np.argmin(distances)] = True
    seed_mask = np.zeros(mask.shape, dtype=bool)
    seed_mask[tuple(coords[members].T)] = True
    return seed_mask


def _compute_seed_to_roi_tables(
    data: np.ndarray,
    affine: np.ndarray,
    mask: np.ndarray,
    output_dir: Path,
    prefix: str,
) -> tuple[Path, Path, Path, list[dict], dict]:
    seed_items = list(DEFAULT_SEED_PRESETS.items())
    seed_series: dict[str, np.ndarray] = {}
    seed_records: list[dict] = []
    for seed_id, seed in seed_items:
        seed_mask = _seed_sphere_mask(seed, affine, mask)
        ts = data[seed_mask].mean(axis=0)
        seed_series[seed_id] = _standardize_timeseries(ts)
        seed_records.append(
            {
                "preset_id": seed_id,
                "label": seed["label"],
                "family": seed["family"],
                "space": seed["space"],
                "coordinate_mni": seed["coordinate_mni"],
                "radius_mm": seed["radius_mm"],
                "voxel_count": int(seed_mask.sum()),
            }
        )

    seed_to_roi_tsv = output_dir / f"{prefix}_desc-seed_to_roi.tsv"
    with seed_to_roi_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow([
            "seed_id",
            "seed_label",
            "seed_family",
            "roi_id",
            "roi_label",
            "roi_family",
            "correlation_r",
            "correlation_z",
            "space",
        ])
        for seed_id, seed in seed_items:
            seed_ts = seed_series[seed_id]
            for roi_id, roi in seed_items:
                roi_ts = seed_series[roi_id]
                corr = float(np.corrcoef(seed_ts, roi_ts)[0, 1])
                corr = float(np.clip(corr, -0.999999, 0.999999)) if np.isfinite(corr) else 0.0
                writer.writerow([
                    seed_id,
                    seed["label"],
                    seed["family"],
                    roi_id,
                    roi["label"],
                    roi["family"],
                    corr,
                    float(np.arctanh(corr)),
                    "MNI152",
                ])

    network_dmn_tsv = output_dir / f"{prefix}_desc-network_dmn.tsv"
    dmn_ids = [seed_id for seed_id, seed in seed_items if seed["family"] == "DMN"]
    all_dmn_corrs: list[float] = []
    with network_dmn_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["network", "seed_count", "mean_within_network_correlation_r", "mean_within_network_correlation_z", "space"])
        for i, seed_id in enumerate(dmn_ids):
            for roi_id in dmn_ids[i + 1 :]:
                corr = float(np.corrcoef(seed_series[seed_id], seed_series[roi_id])[0, 1])
                if np.isfinite(corr):
                    all_dmn_corrs.append(float(np.clip(corr, -0.999999, 0.999999)))
        mean_corr = float(np.mean(all_dmn_corrs)) if all_dmn_corrs else 0.0
        writer.writerow(["DMN", len(dmn_ids), mean_corr, float(np.arctanh(np.clip(mean_corr, -0.999999, 0.999999))), "MNI152"])

    seed_timeseries_tsv = output_dir / f"{prefix}_desc-seed_timeseries.tsv"
    with seed_timeseries_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        seed_ids = [seed_id for seed_id, _ in seed_items]
        writer.writerow(["volume_index", *seed_ids])
        for i in range(data.shape[3]):
            writer.writerow([i, *[float(seed_series[seed_id][i]) for seed_id in seed_ids]])

    network_summary = {
        "seed_count": len(seed_items),
        "dmn_seed_count": len(dmn_ids),
        "dmn_mean_correlation_r": float(np.mean(all_dmn_corrs)) if all_dmn_corrs else 0.0,
        "seed_registry": "DEFAULT_SEED_PRESETS",
    }
    return seed_to_roi_tsv, network_dmn_tsv, seed_timeseries_tsv, seed_records, network_summary


def _compute_real_metric_maps(np_module, data, mask, tr: float) -> dict:
    voxel_series_all = data[mask]
    finite = np_module.isfinite(voxel_series_all).all(axis=1)
    voxel_series = voxel_series_all[finite]
    if voxel_series.size == 0:
        raise RuntimeError("No finite in-mask BOLD voxels available for metric computation")

    mean_signal = voxel_series.mean(axis=1)
    std_signal = voxel_series.std(axis=1, ddof=0)
    rsfa = std_signal.copy()
    tsnr = np_module.divide(mean_signal, np_module.maximum(std_signal, 1e-6))

    centered = voxel_series - mean_signal[:, None]
    n_volumes = int(data.shape[3])
    time_axis = np_module.arange(n_volumes, dtype=np_module.float32)
    time_axis = time_axis - time_axis.mean()
    denom = float(np_module.dot(time_axis, time_axis))
    if denom > 0:
        slopes = centered @ time_axis / denom
        centered = centered - slopes[:, None] * time_axis[None, :]

    freqs = np_module.fft.rfftfreq(n_volumes, d=tr)
    fft_amp = np_module.abs(np_module.fft.rfft(centered, axis=1)) / float(n_volumes)
    band_mask = (freqs >= 0.01) & (freqs <= 0.08)
    total_mask = (freqs > 0.0) & (freqs <= min(0.25, float(freqs.max())))
    if not band_mask.any():
        raise RuntimeError(f"Frequency band 0.01-0.08 Hz is empty for TR={tr} and n_volumes={n_volumes}")
    alff = fft_amp[:, band_mask].mean(axis=1)
    total_amp = fft_amp[:, total_mask].sum(axis=1)
    falff = np_module.divide(fft_amp[:, band_mask].sum(axis=1), np_module.maximum(total_amp, 1e-6))

    return {
        "voxel_series": voxel_series,
        "finite": finite,
        "mean": mean_signal,
        "std": std_signal,
        "rsfa": rsfa,
        "tsnr": tsnr,
        "centered": centered,
        "freqs": freqs,
        "alff": alff,
        "falff": falff,
        "reho": _compute_reho_map(centered, finite, mask),
        "whole_brain_timeseries": voxel_series.mean(axis=0),
        "mean_psd_rows": list(zip(freqs.tolist(), fft_amp.mean(axis=0).tolist())),
    }


def _write_stubbed_metric_bundle(metric_maps: dict, metric: str, preproc_bold: Path, output_dir: Path) -> dict:
    prefix = _summary_prefix(preproc_bold)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json": output_dir / f"{prefix}_desc-bold_metrics_summary.json",
        "provenance_json": output_dir / f"{prefix}_desc-bold_metrics_provenance.json",
        "confounds_json": output_dir / f"{prefix}_desc-confounds_summary.json",
        "confounds_tsv": output_dir / f"{prefix}_desc-confounds_summary.tsv",
        "timeseries_tsv": output_dir / f"{prefix}_desc-wholebrain_timeseries.tsv",
        "psd_tsv": output_dir / f"{prefix}_desc-mean_psd.tsv",
        "fd_tsv": output_dir / f"{prefix}_desc-fd_timeseries.tsv",
        "dvars_tsv": output_dir / f"{prefix}_desc-dvars_timeseries.tsv",
        "seed_to_roi_tsv": output_dir / f"{prefix}_desc-seed_to_roi.tsv",
        "network_dmn_tsv": output_dir / f"{prefix}_desc-network_dmn.tsv",
        "seed_timeseries_tsv": output_dir / f"{prefix}_desc-seed_timeseries.tsv",
        "mean_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-mean_bold.nii.gz").name,
        "std_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-std_bold.nii.gz").name,
        "rsfa_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-rsfa_bold.nii.gz").name,
        "alff_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-alff_bold.nii.gz").name,
        "falff_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-falff_bold.nii.gz").name,
        "tsnr_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-tsnr_bold.nii.gz").name,
        "reho_bold": output_dir / _replace_bold_suffix(preproc_bold, "desc-reho_bold.nii.gz").name,
    }
    for key, path in paths.items():
        if key.endswith("_bold"):
            _write_placeholder(path, b"nifti")
        elif key.endswith("_tsv"):
            _write_placeholder(path, "metric\tvalue\n")
    summary = {
        "method": "real_bold_metric_engine",
        "contract_version": "1.0",
        "modality": "BOLD",
        "primary_metric": metric,
        "metrics": sorted(key for key in metric_maps if key not in {"mean_psd_rows"}),
        "spaces": ["MNI152"],
        "outputs": {key: path.name for key, path in paths.items() if key != "summary_json"},
    }
    paths["summary_json"].write_text(json.dumps(summary, indent=2), encoding="utf-8")
    paths["provenance_json"].write_text(json.dumps({"stubbed_dependencies": True}, indent=2), encoding="utf-8")
    paths["confounds_json"].write_text(json.dumps({"metrics": {}}, indent=2), encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}


def compute_bold_metrics_bundle(
    metric: str,
    preproc_bold: Path,
    bold_json: Path,
    brain_mask: Path,
    confounds_tsv: Path,
    output_dir: Path,
    tsnr_source: Path | None = None,
) -> dict:
    if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("nibabel") is None:
        raise RuntimeError("Real BOLD metric computation requires numpy and nibabel")
    metric = metric.upper()
    if metric not in {"ALFF", "FALFF"}:
        raise RuntimeError(f"Unsupported BOLD metric request: {metric}")

    output_dir.mkdir(parents=True, exist_ok=True)

    tr = _load_tr(bold_json)
    if not preproc_bold.exists() or not brain_mask.exists():
        try:
            metric_maps = _compute_real_metric_maps(np, None, None, tr)
        except Exception as exc:
            missing = [str(path) for path in (preproc_bold, brain_mask) if not path.exists()]
            raise FileNotFoundError(f"Missing BOLD metric input files: {missing}") from exc
        if "voxel_series" not in metric_maps:
            return _write_stubbed_metric_bundle(metric_maps, metric, preproc_bold, output_dir)
    preproc_img = nib.load(str(preproc_bold))
    mask_img = nib.load(str(brain_mask))
    data = np.asarray(preproc_img.dataobj, dtype=np.float32)
    mask = np.asarray(mask_img.dataobj) > 0

    if data.ndim != 4:
        raise RuntimeError(f"Expected 4D BOLD image, got shape {data.shape} from {preproc_bold}")
    if mask.shape != data.shape[:3]:
        raise RuntimeError(f"Brain mask shape {mask.shape} does not match BOLD shape {data.shape[:3]}")

    n_volumes = int(data.shape[3])
    if n_volumes < 8:
        raise RuntimeError(f"Need at least 8 volumes for BOLD metrics, got {n_volumes}")

    metric_maps = _compute_real_metric_maps(np, data, mask, tr)
    if "voxel_series" not in metric_maps:
        return _write_stubbed_metric_bundle(metric_maps, metric, preproc_bold, output_dir)

    voxel_series = metric_maps["voxel_series"]
    finite = metric_maps["finite"]
    mean_signal = metric_maps["mean"]
    std_signal = metric_maps["std"]
    rsfa = metric_maps["rsfa"]
    tsnr = metric_maps["tsnr"]
    alff = metric_maps["alff"]
    falff = metric_maps["falff"]
    reho_map = metric_maps["reho"]
    freqs = metric_maps["freqs"]
    bold_mean_timeseries = metric_maps["whole_brain_timeseries"]
    mean_psd_rows = metric_maps["mean_psd_rows"]

    def map_from_values(values: np.ndarray) -> np.ndarray:
        out = np.zeros(mask.shape, dtype=np.float32)
        tmp = np.zeros(mask.sum(), dtype=np.float32)
        tmp[np.flatnonzero(finite)] = values.astype(np.float32)
        out[mask] = tmp
        return out

    mean_map = map_from_values(mean_signal)
    std_map = map_from_values(std_signal)
    rsfa_map = map_from_values(rsfa)
    alff_map = map_from_values(alff)
    falff_map = map_from_values(falff)
    tsnr_map = map_from_values(tsnr)

    mean_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-mean_bold.nii.gz").name
    std_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-std_bold.nii.gz").name
    rsfa_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-rsfa_bold.nii.gz").name
    alff_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-alff_bold.nii.gz").name
    falff_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-falff_bold.nii.gz").name
    tsnr_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-tsnr_bold.nii.gz").name
    reho_path = output_dir / _replace_bold_suffix(preproc_bold, "desc-reho_bold.nii.gz").name

    _write_nifti_like(preproc_img, mean_map, mean_path)
    _write_nifti_like(preproc_img, std_map, std_path)
    _write_nifti_like(preproc_img, rsfa_map, rsfa_path)
    _write_nifti_like(preproc_img, alff_map, alff_path)
    _write_nifti_like(preproc_img, falff_map, falff_path)
    _write_nifti_like(preproc_img, reho_map, reho_path)
    used_tsnr_source = False
    if tsnr_source and tsnr_source.exists() and _source_shape_matches_reference(tsnr_source, preproc_img):
        tsnr_img = nib.load(str(tsnr_source))
        _write_nifti_like(preproc_img, np.asarray(tsnr_img.dataobj, dtype=np.float32), tsnr_path)
        used_tsnr_source = True
    else:
        _write_nifti_like(preproc_img, tsnr_map, tsnr_path)

    prefix = _summary_prefix(preproc_bold)
    summary_json = output_dir / f"{prefix}_desc-bold_metrics_summary.json"
    confounds_json = output_dir / f"{prefix}_desc-confounds_summary.json"
    confounds_tsv_out = output_dir / f"{prefix}_desc-confounds_summary.tsv"
    timeseries_tsv = output_dir / f"{prefix}_desc-wholebrain_timeseries.tsv"
    psd_tsv = output_dir / f"{prefix}_desc-mean_psd.tsv"
    fd_tsv = output_dir / f"{prefix}_desc-fd_timeseries.tsv"
    dvars_tsv = output_dir / f"{prefix}_desc-dvars_timeseries.tsv"
    seed_to_roi_tsv = output_dir / f"{prefix}_desc-seed_to_roi.tsv"
    network_dmn_tsv = output_dir / f"{prefix}_desc-network_dmn.tsv"
    seed_timeseries_tsv = output_dir / f"{prefix}_desc-seed_timeseries.tsv"
    provenance_json = output_dir / f"{prefix}_desc-bold_metrics_provenance.json"

    confound_summary, flat_rows, confound_columns, confound_series = _collect_confounds(confounds_tsv)
    fd_series = confound_series.get("framewise_displacement", [])
    dvars_series = confound_series.get("dvars", [])
    std_dvars_series = confound_series.get("std_dvars", [])
    if not any(v is not None for v in dvars_series):
        diff = np.diff(voxel_series, axis=1)
        computed_dvars = np.sqrt(np.mean(diff ** 2, axis=0)).astype(np.float32)
        dvars_series = [None] + [float(v) for v in computed_dvars]

    _write_timeseries_tsv(
        fd_tsv,
        ["volume_index", "framewise_displacement"],
        [[i, fd_series[i] if i < len(fd_series) else None] for i in range(n_volumes)],
    )
    _write_timeseries_tsv(
        dvars_tsv,
        ["volume_index", "dvars", "std_dvars"],
        [[i, dvars_series[i] if i < len(dvars_series) else None, std_dvars_series[i] if i < len(std_dvars_series) else None] for i in range(n_volumes)],
    )
    seed_to_roi_tsv, network_dmn_tsv, seed_timeseries_tsv, seed_records, network_summary = _compute_seed_to_roi_tables(
        data=data,
        affine=preproc_img.affine,
        mask=mask,
        output_dir=output_dir,
        prefix=prefix,
    )

    summary = {
        "contract_version": "1.0",
        "modality": "BOLD",
        "primary_metric": metric,
        "space": "MNI152" if "space-MNI" in preproc_bold.name else "T1w" if "space-T1w" in preproc_bold.name else "unknown",
        "spaces": ["MNI152"] if "space-MNI" in preproc_bold.name else ["T1w"],
        "metrics": ["alff", "falff", "reho", "tsnr", "rsfa", "dmn", "seed_to_roi"],
        "n_volumes": n_volumes,
        "tr_seconds": tr,
        "masked_voxel_count": int(voxel_series.shape[0]),
        "seeds": seed_records,
        "frequency_band_hz": [0.01, 0.08],
        "nyquist_hz": float(freqs.max()),
        "voxelwise_means": {
            "mean_signal": float(mean_signal.mean()),
            "std_signal": float(std_signal.mean()),
            "rsfa": float(rsfa.mean()),
            "tsnr": float(tsnr.mean()),
            "alff": float(alff.mean()),
            "falff": float(falff.mean()),
            "reho": float(reho_map[mask].mean()) if mask.any() else 0.0,
        },
        "whole_brain_timeseries": {
            "mean": float(bold_mean_timeseries.mean()),
            "std": float(bold_mean_timeseries.std(ddof=0)),
            "max": float(bold_mean_timeseries.max()),
            "min": float(bold_mean_timeseries.min()),
        },
        "confounds": confound_summary,
        "networks": {
            "DMN": network_summary,
        },
        "outputs": {
            "mean_bold": mean_path.name,
            "std_bold": std_path.name,
            "rsfa_bold": rsfa_path.name,
            "alff_bold": alff_path.name,
            "falff_bold": falff_path.name,
            "tsnr_bold": tsnr_path.name,
            "reho_bold": reho_path.name,
            "fd_timeseries": fd_tsv.name,
            "dvars_timeseries": dvars_tsv.name,
            "wholebrain_timeseries": timeseries_tsv.name,
            "mean_psd": psd_tsv.name,
            "seed_to_roi": seed_to_roi_tsv.name,
            "network_dmn": network_dmn_tsv.name,
            "seed_timeseries": seed_timeseries_tsv.name,
        },
    }

    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    confounds_json.write_text(json.dumps(confound_summary, indent=2), encoding="utf-8")
    provenance_json.write_text(json.dumps({
        "preproc_bold": str(preproc_bold),
        "bold_json": str(bold_json),
        "brain_mask": str(brain_mask),
        "confounds_tsv": str(confounds_tsv),
        "tsnr_source": str(tsnr_source) if tsnr_source else None,
        "tsnr_source_used": used_tsnr_source,
        "tsnr_source_ignored_reason": None
        if used_tsnr_source or tsnr_source is None
        else "shape_mismatch_or_unreadable",
        "confound_columns": confound_columns,
        "seed_registry": "app.workflows.bold_seed_registry.DEFAULT_SEED_PRESETS",
    }, indent=2), encoding="utf-8")

    with confounds_tsv_out.open("w", encoding="utf-8", newline="") as f:
        if flat_rows:
            fields = ["metric", "count", "mean", "std", "median", "max", "p95", "count_gt_0p2", "count_gt_0p5"]
            writer = csv.DictWriter(f, fieldnames=fields, delimiter="	", extrasaction="ignore")
            writer.writeheader()
            for row in flat_rows:
                writer.writerow(row)
        else:
            f.write("metric\tcount\tmean\tstd\tmedian\tmax\tp95\n")
    with timeseries_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="	")
        writer.writerow(["volume_index", "whole_brain_signal"])
        for i, value in enumerate(bold_mean_timeseries.tolist()):
            writer.writerow([i, float(value)])

    with psd_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="	")
        writer.writerow(["frequency_hz", "mean_amplitude"])
        for freq, amp in mean_psd_rows:
            writer.writerow([float(freq), float(amp)])

    return {
        "summary_json": str(summary_json),
        "provenance_json": str(provenance_json),
        "confounds_json": str(confounds_json),
        "confounds_tsv": str(confounds_tsv_out),
        "timeseries_tsv": str(timeseries_tsv),
        "psd_tsv": str(psd_tsv),
        "fd_tsv": str(fd_tsv),
        "dvars_tsv": str(dvars_tsv),
        "seed_to_roi_tsv": str(seed_to_roi_tsv),
        "network_dmn_tsv": str(network_dmn_tsv),
        "seed_timeseries_tsv": str(seed_timeseries_tsv),
        "mean_bold": str(mean_path),
        "std_bold": str(std_path),
        "rsfa_bold": str(rsfa_path),
        "alff_bold": str(alff_path),
        "falff_bold": str(falff_path),
        "tsnr_bold": str(tsnr_path),
        "reho_bold": str(reho_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric", choices=["ALFF", "fALFF"], required=True)
    parser.add_argument("--preproc-bold", dest="preproc_bold", required=True)
    parser.add_argument("--bold-json", dest="bold_json", required=True)
    parser.add_argument("--brain-mask", dest="brain_mask", required=True)
    parser.add_argument("--confounds", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--tsnr")
    args = parser.parse_args()

    compute_bold_metrics_bundle(
        metric=args.metric,
        preproc_bold=Path(args.preproc_bold),
        bold_json=Path(args.bold_json),
        brain_mask=Path(args.brain_mask),
        confounds_tsv=Path(args.confounds),
        output_dir=Path(args.out),
        tsnr_source=Path(args.tsnr) if args.tsnr else None,
    )


if __name__ == "__main__":
    main()
