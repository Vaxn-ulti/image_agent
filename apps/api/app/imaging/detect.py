import json
from pathlib import Path
from typing import Any

from app.imaging.nifti import parse_nifti_header

UNSUPPORTED_SEQUENCE_MESSAGE = "Current software does not support radiomics/processing for this sequence."

SIDECAR_JSON_KEYS = {
    "B0FieldIdentifier",
    "EchoTime",
    "FlipAngle",
    "ImageType",
    "IntendedFor",
    "MRAcquisitionType",
    "Manufacturer",
    "Modality",
    "PhaseEncodingDirection",
    "ProtocolName",
    "RepetitionTime",
    "SeriesDescription",
    "SequenceName",
    "TaskName",
    "TotalReadoutTime",
}


def sequence_support(sequence_label: str) -> tuple[str, bool, str]:
    supported = {
        "T1w_MPRAGE": "T1",
        "DWI_multi_shell": "DWI",
        "DWI_single_shell": "DWI",
        "rsfMRI_BOLD": "BOLD",
        "task_fMRI_BOLD": "BOLD",
    }
    unsupported = {
        "T2w": "T2",
        "T2_FLAIR": "FLAIR",
        "SWI": "SWI",
        "ASL": "ASL",
        "PD": "PD",
        "MRA": "MRA",
        "DTI_ADC_MAP": "ADC",
        "fieldmap": "FMAP",
        "localizer_scout": "LOCALIZER",
    }
    if sequence_label in supported:
        return supported[sequence_label], True, ""
    if sequence_label in unsupported:
        return unsupported[sequence_label], False, UNSUPPORTED_SEQUENCE_MESSAGE
    return "unknown", False, "Unknown sequence; current software does not support processing for this sequence."


def infer_sequence_label(path: str | Path, metadata: dict[str, Any]) -> str:
    p = Path(path)
    lower = p.name.lower()
    shape = metadata.get("shape", [])
    ndim = int(metadata.get("ndim") or len(shape))
    timepoints = shape[3] if len(shape) >= 4 else 1
    sidecar_base = p.name[:-7] if lower.endswith(".nii.gz") else p.stem
    has_bval = metadata.get("has_bval") or (p.with_name(sidecar_base + ".bval")).exists()
    has_bvec = metadata.get("has_bvec") or (p.with_name(sidecar_base + ".bvec")).exists()
    sidecar_json = metadata.get("sidecar_json_summary") or {}
    sidecar_text = " ".join(
        str(sidecar_json.get(key, ""))
        for key in ("Modality", "SeriesDescription", "ProtocolName", "SequenceName", "TaskName")
    ).lower()
    if "flair" in lower:
        return "T2_FLAIR"
    if "swi" in lower or "suscept" in lower:
        return "SWI"
    if "asl" in lower or "perfusion" in lower:
        return "ASL"
    if "mra" in lower or "angi" in lower:
        return "MRA"
    if "adc" in lower:
        return "DTI_ADC_MAP"
    if "fieldmap" in lower or "fmap" in lower:
        return "fieldmap"
    if "localizer" in lower or "scout" in lower:
        return "localizer_scout"
    if "t2" in lower:
        return "T2w"
    if any(token in lower for token in ("t1", "t1w", "mprage", "bravo", "spgr", "anat")) or any(
        token in sidecar_text for token in ("t1", "mprage", "bravo", "spgr", "anat")
    ):
        return "T1w_MPRAGE"
    if "bold" in lower or "fmri" in lower or "func" in lower or any(
        token in sidecar_text for token in ("bold", "fmri", "functional")
    ) or sidecar_json.get("TaskName"):
        return "rsfMRI_BOLD" if "rest" in lower or "rs" in lower or str(sidecar_json.get("TaskName", "")).lower() in {"rest", "resting"} else "task_fMRI_BOLD"
    if "dwi" in lower or has_bval or has_bvec:
        return "DWI_multi_shell" if has_bval and has_bvec else "DWI_single_shell"
    if ndim >= 4 and timepoints >= 10:
        return "rsfMRI_BOLD" if "rest" in lower or "rs" in lower else "task_fMRI_BOLD"
    if ndim == 3:
        return "T1w_MPRAGE"
    return "unknown"


def _sidecar_base(path: Path) -> str:
    lower = path.name.lower()
    return path.name[:-7] if lower.endswith(".nii.gz") else path.stem


def read_json_summary_file(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists() or not json_path.is_file():
        return {}
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: raw[key] for key in SIDECAR_JSON_KEYS if key in raw and isinstance(raw[key], (str, int, float, bool, list))}


def _read_sidecar_json(path: Path) -> dict[str, Any]:
    return read_json_summary_file(path.with_name(_sidecar_base(path) + ".json"))


def detect_series(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    lower = p.name.lower()
    if not (lower.endswith(".nii") or lower.endswith(".nii.gz")):
        return {"modality": "unknown", "format": "UNKNOWN", "confidence": 0.0, "metadata": {"filename": p.name}}
    metadata = parse_nifti_header(p)
    shape = metadata.get("shape", [])
    ndim = int(metadata.get("ndim") or len(shape))
    timepoints = shape[3] if len(shape) >= 4 else 1
    sidecar_base = _sidecar_base(p)
    has_bval = (p.with_name(sidecar_base + ".bval")).exists()
    has_bvec = (p.with_name(sidecar_base + ".bvec")).exists()
    sidecar_json = _read_sidecar_json(p)
    detection_evidence = ["nifti_header"]
    if has_bval:
        detection_evidence.append("bval_sidecar")
    if has_bvec:
        detection_evidence.append("bvec_sidecar")
    if sidecar_json:
        detection_evidence.append("json_sidecar_summary")
    metadata.update({
        "timepoints": timepoints,
        "has_bval": has_bval,
        "has_bvec": has_bvec,
        "sidecar_json_summary": sidecar_json,
        "detection_evidence": detection_evidence,
    })
    sequence_label = infer_sequence_label(p, metadata)
    modality, supported, unsupported_reason = sequence_support(sequence_label)
    confidence = 0.9 if supported else 0.75 if sequence_label != "unknown" else 0.2
    metadata.update({
        "sequence_label": sequence_label,
        "supported_for_processing": supported,
        "unsupported_reason": unsupported_reason,
    })
    return {"modality": modality, "format": "NIFTI", "confidence": confidence, "metadata": metadata}
