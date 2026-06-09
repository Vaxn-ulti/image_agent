from __future__ import annotations


def build_seed_record(preset_id: str, coordinate: list[int], radius_mm: int, family: str) -> dict:
    return {
        "preset_id": preset_id,
        "coordinate_mni": coordinate,
        "radius_mm": radius_mm,
        "family": family,
        "space": "MNI152",
    }


def build_run_summary(
    subject_id: str,
    task_label: str,
    metrics: list[str],
    seed_records: list[dict],
    provenance: dict,
) -> dict:
    return {
        "contract_version": "1.0",
        "modality": "BOLD",
        "subject_id": subject_id,
        "task_label": task_label,
        "metrics": metrics,
        "spaces": ["MNI152"],
        "seeds": seed_records,
        "provenance": provenance,
        "outputs": {},
    }
