import hashlib
import json
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

from app.core.config import PROJECTS_ROOT
from app.db.database import connect, now_iso
from app.imaging.detect import UNSUPPORTED_SEQUENCE_MESSAGE, detect_series, sequence_support


def is_dicom_file(path: Path) -> bool:
    if path.suffix.lower() in {".dcm", ".ima"}:
        return True
    try:
        with path.open("rb") as f:
            head = f.read(132)
        return len(head) >= 132 and head[128:132] == b"DICM"
    except OSError:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_bids_root(project_id: int) -> Path:
    root = PROJECTS_ROOT / str(project_id) / "bids" / "rawdata"
    root.mkdir(parents=True, exist_ok=True)
    desc = root / "dataset_description.json"
    if not desc.exists():
        desc.write_text(json.dumps({"Name": "Brain Image Agent", "BIDSVersion": "1.9.0", "DatasetType": "raw"}, indent=2), encoding="utf-8")
    participants = root / "participants.tsv"
    if not participants.exists():
        participants.write_text("participant_id\nsub-01\n", encoding="utf-8")
    return root


def bids_parts(modality: str, sequence_label: str, filename: str) -> tuple[str, str]:
    lower = filename.lower()
    if modality == "T1":
        return "anat", "T1w"
    if modality == "DWI":
        return "dwi", "dwi"
    if modality == "BOLD":
        return "func", "task-rest_bold" if "task-" not in lower else "bold"
    if modality == "T2":
        return "anat", "T2w"
    if modality == "FLAIR":
        return "anat", "FLAIR"
    if modality == "SWI":
        return "anat", "swi"
    if modality == "ASL":
        return "perf", "asl"
    if modality == "FMAP":
        return "fmap", "fieldmap"
    return "sourcedata", sequence_label.lower().replace("_", "-") or "unknown"


def unique_bids_path(bids_root: Path, modality: str, sequence_label: str, original_name: str, ext: str) -> Path:
    folder, suffix = bids_parts(modality, sequence_label, original_name)
    out_dir = bids_root / "sub-01" / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"sub-01_{suffix}"
    candidate = out_dir / f"{base}{ext}"
    if not candidate.exists():
        return candidate
    safe_acq = "".join(ch if ch.isalnum() else "" for ch in Path(original_name).stem)[:16].lower() or "scan"
    candidate = out_dir / f"sub-01_acq-{safe_acq}_{suffix}{ext}"
    if not candidate.exists():
        return candidate
    run = 2
    while True:
        candidate = out_dir / f"sub-01_acq-{safe_acq}_run-{run}_{suffix}{ext}"
        if not candidate.exists():
            return candidate
        run += 1


def copy_sidecars(src: Path, dst: Path) -> list[str]:
    copied = []
    src_base = src.name[:-7] if src.name.lower().endswith(".nii.gz") else src.stem
    dst_base = dst.name[:-7] if dst.name.lower().endswith(".nii.gz") else dst.stem
    for suffix in (".json", ".bval", ".bvec", ".tsv"):
        sidecar = src.with_name(src_base + suffix)
        if sidecar.exists():
            target = dst.with_name(dst_base + suffix)
            shutil.copy2(sidecar, target)
            copied.append(str(target))
    return copied


def register_bids_series(project_id: int, upload_session_id: int, src: Path, bids_path: Path, detection: dict) -> dict:
    rel_bids = bids_path.relative_to(PROJECTS_ROOT / str(project_id)).as_posix()
    metadata = detection["metadata"]
    sequence_label = metadata.get("sequence_label", "unknown")
    supported = bool(metadata.get("supported_for_processing"))
    unsupported_reason = metadata.get("unsupported_reason", "")
    with connect() as conn:
        fcur = conn.execute(
            "INSERT INTO files(project_id, original_name, storage_path, file_type, size, sha256, created_at) VALUES(?,?,?,?,?,?,?)",
            (project_id, src.name, str(bids_path), "NIFTI_BIDS", bids_path.stat().st_size, sha256_file(bids_path), now_iso()),
        )
        scur = conn.execute(
            "INSERT INTO imaging_series(project_id, file_id, upload_session_id, bids_path, sequence_label, supported_for_processing, unsupported_reason, modality, format, confidence, metadata_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                fcur.lastrowid,
                upload_session_id,
                rel_bids,
                sequence_label,
                1 if supported else 0,
                unsupported_reason,
                detection["modality"],
                "NIFTI_BIDS",
                detection["confidence"],
                json.dumps(metadata),
                "detected",
                now_iso(),
            ),
        )
        row = conn.execute("SELECT * FROM imaging_series WHERE id=?", (scur.lastrowid,)).fetchone()
    return dict(row)


def normalize_nifti(project_id: int, upload_session_id: int, src: Path) -> dict | None:
    try:
        detection = detect_series(src)
    except Exception as exc:
        sequence_label = "unknown"
        modality, supported, unsupported_reason = sequence_support(sequence_label)
        detection = {
            "modality": modality,
            "format": "NIFTI",
            "confidence": 0.0,
            "metadata": {"filename": src.name, "sequence_label": sequence_label, "supported_for_processing": supported, "unsupported_reason": str(exc) or unsupported_reason},
        }
    bids_root = ensure_bids_root(project_id)
    ext = ".nii.gz" if src.name.lower().endswith(".nii.gz") else ".nii"
    sequence_label = detection["metadata"].get("sequence_label", "unknown")
    dst = unique_bids_path(bids_root, detection["modality"], sequence_label, src.name, ext)
    shutil.copy2(src, dst)
    sidecars = copy_sidecars(src, dst)
    detection["metadata"]["bids_path"] = dst.relative_to(PROJECTS_ROOT / str(project_id)).as_posix()
    detection["metadata"]["sidecars"] = sidecars
    return register_bids_series(project_id, upload_session_id, src, dst, detection)


def extract_archive(archive: Path, extracted: Path) -> None:
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        root = extracted.resolve()
        for member in zf.infolist():
            target = (extracted / member.filename).resolve()
            if not str(target).startswith(str(root)):
                raise ValueError("Unsafe archive path")
        zf.extractall(extracted)


def convert_dicom_dir(dicom_root: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["dcm2niix", "-z", "y", "-ba", "y", "-o", str(output_dir), str(dicom_root)]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    return {"returncode": proc.returncode, "command": cmd, "log_tail": proc.stdout[-4000:]}


def store_inventory(project_id: int, upload_session_id: int, inventory: dict) -> None:
    inv_dir = PROJECTS_ROOT / str(project_id) / "inventory"
    inv_dir.mkdir(parents=True, exist_ok=True)
    (inv_dir / f"{upload_session_id}.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    with connect() as conn:
        conn.execute(
            "UPDATE upload_sessions SET status=?, progress=?, inventory_json=?, error_message=?, finished_at=? WHERE id=?",
            (inventory["inventory_status"], 100, json.dumps(inventory), inventory.get("error_message"), now_iso(), upload_session_id),
        )
        conn.execute("DELETE FROM sequence_findings WHERE upload_session_id=?", (upload_session_id,))
        for sequence, count in inventory["post_conversion_counts"]["by_sequence"].items():
            item = next((s for s in inventory["series"] if s["sequence_label"] == sequence), None)
            modality = item["modality"] if item else "unknown"
            supported = bool(item and item["supported_for_processing"])
            message = "" if supported else UNSUPPORTED_SEQUENCE_MESSAGE if sequence != "unknown" else "Unknown sequence; current software does not support processing for this sequence."
            conn.execute(
                "INSERT INTO sequence_findings(upload_session_id, project_id, sequence_label, modality, count, supported_for_processing, message, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (upload_session_id, project_id, sequence, modality, count, 1 if supported else 0, message, now_iso()),
            )


def process_upload_session(project_id: int, upload_session_id: int, archive_path: Path) -> dict:
    with connect() as conn:
        conn.execute("UPDATE upload_sessions SET status='running', progress=5, started_at=? WHERE id=?", (now_iso(), upload_session_id))
    session_root = PROJECTS_ROOT / str(project_id) / "uploads" / str(upload_session_id)
    extracted = session_root / "extracted"
    conversion_out = session_root / "converted"
    try:
        extract_archive(archive_path, extracted)
        all_files = [p for p in extracted.rglob("*") if p.is_file()]
        dicom_files = [p for p in all_files if is_dicom_file(p)]
        nifti_files = [p for p in all_files if p.name.lower().endswith((".nii", ".nii.gz"))]
        conversion_status = "not_applicable"
        conversion = {"found_files": len(dicom_files), "conversion_status": conversion_status, "converted_series": 0, "failed_series": 0, "failures": []}
        if dicom_files:
            result = convert_dicom_dir(extracted, conversion_out)
            converted = [p for p in conversion_out.rglob("*") if p.name.lower().endswith((".nii", ".nii.gz"))]
            nifti_files.extend(converted)
            if result["returncode"] == 0:
                conversion_status = "completed"
            elif converted:
                conversion_status = "completed_with_partial_failures"
                conversion["failed_series"] = 1
                conversion["failures"].append({"source": str(extracted), "log_tail": result["log_tail"]})
            else:
                conversion_status = "failed"
                conversion["failed_series"] = 1
                conversion["failures"].append({"source": str(extracted), "log_tail": result["log_tail"]})
            conversion.update({"conversion_status": conversion_status, "converted_series": len(converted)})
        series_rows = []
        for nifti in nifti_files:
            row = normalize_nifti(project_id, upload_session_id, nifti)
            if row:
                md = json.loads(row["metadata_json"])
                series_rows.append({
                    "series_id": row["id"],
                    "source_format": "DICOM" if str(nifti).startswith(str(conversion_out)) else "NIFTI",
                    "normalized_format": "NIFTI",
                    "bids_path": row["bids_path"],
                    "modality": row["modality"],
                    "sequence_label": row["sequence_label"] or md.get("sequence_label", "unknown"),
                    "supported_for_processing": bool(row["supported_for_processing"]),
                    "unsupported_reason": row["unsupported_reason"] or "",
                })
        by_modality = Counter(s["modality"] for s in series_rows)
        by_sequence = Counter(s["sequence_label"] for s in series_rows)
        unsupported = []
        for sequence, count in sorted(by_sequence.items()):
            examples = [s for s in series_rows if s["sequence_label"] == sequence]
            if examples and not examples[0]["supported_for_processing"]:
                unsupported.append({"sequence": sequence, "count": count, "message": UNSUPPORTED_SEQUENCE_MESSAGE if sequence != "unknown" else examples[0]["unsupported_reason"]})
        if conversion_status in {"completed_with_partial_failures", "failed"} and series_rows:
            inventory_status = "completed_with_partial_failures"
        elif conversion_status == "failed":
            inventory_status = "failed"
        else:
            inventory_status = "completed"
        inventory = {
            "upload_session_id": upload_session_id,
            "project_id": project_id,
            "inventory_status": inventory_status,
            "total_files": len(all_files),
            "dicom": conversion,
            "post_conversion_counts": {"by_modality": dict(by_modality), "by_sequence": dict(by_sequence)},
            "recognized_unsupported_sequences": unsupported,
            "bids_dataset_root": str((PROJECTS_ROOT / str(project_id) / "bids" / "rawdata")),
            "series": series_rows,
        }
        store_inventory(project_id, upload_session_id, inventory)
        return inventory
    except Exception as exc:
        inventory = {
            "upload_session_id": upload_session_id,
            "project_id": project_id,
            "inventory_status": "failed",
            "total_files": 0,
            "dicom": {"found_files": 0, "conversion_status": "failed", "converted_series": 0, "failed_series": 0, "failures": []},
            "post_conversion_counts": {"by_modality": {}, "by_sequence": {}},
            "recognized_unsupported_sequences": [],
            "bids_dataset_root": str((PROJECTS_ROOT / str(project_id) / "bids" / "rawdata")),
            "series": [],
            "error_message": str(exc),
        }
        store_inventory(project_id, upload_session_id, inventory)
        return inventory
