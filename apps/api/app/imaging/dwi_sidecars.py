from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from app.db.queries import fetch_rows


def dwi_json_metadata(json_row: dict | None) -> dict:
    if json_row is None:
        return {"has_json": False, "has_dwi_eddy_metadata": False}
    path = Path(json_row["storage_path"])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "DWI JSON sidecar must be valid JSON") from exc
    phase_encoding = payload.get("PhaseEncodingDirection")
    total_readout = payload.get("TotalReadoutTime")
    return {
        "has_json": True,
        "json_file_id": json_row["id"],
        "has_dwi_eddy_metadata": phase_encoding is not None and total_readout is not None,
        "phase_encoding_direction": phase_encoding,
        "total_readout_time": total_readout,
    }


def dwi_has_required_sidecars(series: dict, metadata: dict) -> bool:
    sidecars = _dwi_sidecar_paths(series, metadata)
    return (
        bool(metadata.get("has_bval") or ".bval" in sidecars)
        and bool(metadata.get("has_bvec") or ".bvec" in sidecars)
        and _dwi_has_eddy_json_metadata(series, metadata)
    )


def _dwi_sidecar_paths(series: dict, metadata: dict) -> dict[str, Path]:
    sidecars: dict[str, Path] = {}
    for raw_path in metadata.get("sidecars") or []:
        path = Path(raw_path)
        suffix = path.suffix.lower()
        if suffix in {".json", ".bval", ".bvec"} and path.exists():
            sidecars[suffix] = path

    try:
        main_file = fetch_rows("SELECT storage_path, file_type FROM files WHERE id=?", (series["file_id"],))[0]
    except (IndexError, KeyError):
        main_file = None
    allow_same_stem_fallback = bool(
        metadata.get("sidecars")
        or metadata.get("bids_path")
        or series.get("format") == "NIFTI_BIDS"
        or (main_file and main_file.get("file_type") == "NIFTI_BIDS")
    )
    if main_file and allow_same_stem_fallback:
        src = Path(main_file["storage_path"])
        base = _sidecar_base(src)
        for suffix in (".json", ".bval", ".bvec"):
            candidate = src.with_name(base + suffix)
            if suffix not in sidecars and candidate.exists():
                sidecars[suffix] = candidate
    return sidecars


def _dwi_has_eddy_json_metadata(series: dict, metadata: dict) -> bool:
    if metadata.get("has_json") and metadata.get("has_dwi_eddy_metadata"):
        return True
    json_path = _dwi_sidecar_paths(series, metadata).get(".json")
    if json_path is None:
        return False
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("PhaseEncodingDirection") is not None and payload.get("TotalReadoutTime") is not None


def _sidecar_base(path: Path) -> str:
    return path.name[:-7] if path.name.lower().endswith(".nii.gz") else path.stem
