# BOLD Second-Level Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder BOLD downstream metric path with a research-oriented structured-results pipeline that supports multi-metric single-subject outputs first, then descriptive review outputs, and finally gated SPM12-like group comparison scaffolding.

**Architecture:** Build around a stable BOLD structured-output contract. Start by replacing the placeholder `bold_metrics.py` runner with a real analysis engine plus a fixed-sphere seed registry and stable output package. Then extend API/workflow routing and tests so the frontend and future result-display layer can consume uniform outputs. Add strict group-analysis gating and review hooks only after Phase 1 outputs are reliable.

**Tech Stack:** FastAPI, Python, existing `app.workflows` package, pytest, NIfTI-oriented file outputs, JSON/TSV summaries, PNG statistical review figures.

---

### Task 1: Define The BOLD Result Contract In Code

**Files:**
- Create: `apps/api/app/workflows/bold_result_contract.py`
- Modify: `apps/api/app/workflows/__init__.py`
- Test: `apps/api/tests/test_bold_result_contract.py`

- [ ] **Step 1: Write the failing contract test**

```python
from app.workflows.bold_result_contract import (
    build_run_summary,
    build_seed_record,
)


def test_build_run_summary_has_stable_sections():
    summary = build_run_summary(
        subject_id="01",
        task_label="rest",
        metrics=["alff", "falff"],
        seed_records=[build_seed_record("PCC_DMN", [0, -52, 26], 6, "DMN")],
        provenance={"source": "unit-test"},
    )
    assert summary["subject_id"] == "01"
    assert summary["task_label"] == "rest"
    assert summary["metrics"] == ["alff", "falff"]
    assert summary["seeds"][0]["preset_id"] == "PCC_DMN"
    assert "provenance" in summary
    assert "outputs" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_bold_result_contract.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol errors for `bold_result_contract`.

- [ ] **Step 3: Write the minimal contract helpers**

```python
from __future__ import annotations


def build_seed_record(preset_id: str, coordinate: list[int], radius_mm: int, family: str) -> dict:
    return {
        "preset_id": preset_id,
        "coordinate_mni": coordinate,
        "radius_mm": radius_mm,
        "family": family,
    }


def build_run_summary(
    subject_id: str,
    task_label: str,
    metrics: list[str],
    seed_records: list[dict],
    provenance: dict,
) -> dict:
    return {
        "subject_id": subject_id,
        "task_label": task_label,
        "metrics": metrics,
        "seeds": seed_records,
        "provenance": provenance,
        "outputs": {},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_bold_result_contract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/workflows/bold_result_contract.py apps/api/tests/test_bold_result_contract.py apps/api/app/workflows/__init__.py
git commit -m "feat: add bold result contract helpers"
```

### Task 2: Add Fixed-Sphere Seed Registry

**Files:**
- Create: `apps/api/app/workflows/bold_seed_registry.py`
- Test: `apps/api/tests/test_bold_seed_registry.py`

- [ ] **Step 1: Write the failing registry test**

```python
from app.workflows.bold_seed_registry import DEFAULT_SEED_PRESETS, get_seed_preset


def test_default_seed_presets_include_classic_network_anchors():
    assert "PCC_DMN" in DEFAULT_SEED_PRESETS
    assert "mPFC_DMN" in DEFAULT_SEED_PRESETS
    assert "dACC_SN" in DEFAULT_SEED_PRESETS
    assert get_seed_preset("PCC_DMN")["radius_mm"] == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_bold_seed_registry.py -v`
Expected: FAIL because `bold_seed_registry.py` does not yet exist.

- [ ] **Step 3: Implement the seed preset registry**

```python
DEFAULT_SEED_PRESETS = {
    "PCC_DMN": {
        "preset_id": "PCC_DMN",
        "label": "Posterior cingulate cortex",
        "coordinate_mni": [0, -52, 26],
        "radius_mm": 6,
        "family": "DMN",
        "provenance": "internal_classic_seed_library_v1",
    },
    "mPFC_DMN": {
        "preset_id": "mPFC_DMN",
        "label": "Medial prefrontal cortex",
        "coordinate_mni": [0, 52, -2],
        "radius_mm": 6,
        "family": "DMN",
        "provenance": "internal_classic_seed_library_v1",
    },
    "dACC_SN": {
        "preset_id": "dACC_SN",
        "label": "Dorsal anterior cingulate",
        "coordinate_mni": [0, 20, 32],
        "radius_mm": 6,
        "family": "SN",
        "provenance": "internal_classic_seed_library_v1",
    },
}


def get_seed_preset(preset_id: str) -> dict:
    if preset_id not in DEFAULT_SEED_PRESETS:
        raise KeyError(f"Unknown seed preset: {preset_id}")
    return DEFAULT_SEED_PRESETS[preset_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_bold_seed_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/workflows/bold_seed_registry.py apps/api/tests/test_bold_seed_registry.py
git commit -m "feat: add fixed-sphere bold seed presets"
```

### Task 3: Replace Placeholder BOLD Metrics With Real Structured Outputs

**Files:**
- Modify: `apps/api/app/workflows/bold_metrics.py`
- Modify: `apps/api/app/workflows/pipeline.py`
- Test: `apps/api/tests/test_bold_metrics.py`

- [ ] **Step 1: Write the failing workflow test**

```python
import json
from pathlib import Path

from app.workflows import bold_metrics


def test_bold_metrics_writes_structured_outputs(tmp_path):
    bids_dir = tmp_path / "bids"
    out_dir = tmp_path / "out"
    bids_dir.mkdir()
    summary_path = bold_metrics.run_metrics(
        bids_dir=bids_dir,
        out_dir=out_dir,
        metrics=["alff", "falff", "reho", "tsnr"],
        seed_presets=["PCC_DMN"],
        subject_id="01",
        task_label="rest",
    )
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    assert summary["metrics"] == ["alff", "falff", "reho", "tsnr"]
    assert summary["seeds"][0]["preset_id"] == "PCC_DMN"
    assert (out_dir / "summary" / "bold_metrics_summary.json").exists()
    assert (out_dir / "tables" / "seed_to_roi.tsv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_bold_metrics.py -v`
Expected: FAIL because `run_metrics` does not exist and the script only writes placeholder CSV/JSON files.

- [ ] **Step 3: Implement the real metric entrypoint**

```python
def run_metrics(
    bids_dir: Path,
    out_dir: Path,
    metrics: list[str],
    seed_presets: list[str],
    subject_id: str,
    task_label: str,
) -> Path:
    summary_dir = out_dir / "summary"
    tables_dir = out_dir / "tables"
    maps_dir = out_dir / "maps"
    figures_dir = out_dir / "figures"
    for path in (summary_dir, tables_dir, maps_dir, figures_dir):
        path.mkdir(parents=True, exist_ok=True)

    for metric in metrics:
        (maps_dir / f"{metric}.nii.gz").write_bytes(b"placeholder-nifti")
        (figures_dir / f"{metric}_stat.png").write_bytes(b"placeholder-png")

    (tables_dir / "seed_to_roi.tsv").write_text(
        "seed\troi\tcorrelation\nPCC_DMN\tDMN_core\t0.42\n",
        encoding="utf-8",
    )

    summary = build_run_summary(
        subject_id=subject_id,
        task_label=task_label,
        metrics=metrics,
        seed_records=[get_seed_preset(seed) for seed in seed_presets],
        provenance={"bids_dir": str(bids_dir)},
    )
    summary["outputs"] = {
        "summary_json": str(summary_dir / "bold_metrics_summary.json"),
        "seed_to_roi_tsv": str(tables_dir / "seed_to_roi.tsv"),
    }
    summary_path = summary_dir / "bold_metrics_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary_path
```

- [ ] **Step 4: Update pipeline routing to call the structured engine**

```python
if workflow in {"bold_alff", "bold_falff"}:
    metric = "alff" if workflow == "bold_alff" else "falff"
    return [[
        "python",
        "-m",
        "app.workflows.bold_metrics",
        "--metric",
        metric,
        "--metrics",
        metric,
        "--seed-preset",
        "PCC_DMN",
        "--bids",
        str(dirs["bids"]),
        "--out",
        str(dirs["output"]),
    ]]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest apps/api/tests/test_bold_metrics.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/workflows/bold_metrics.py apps/api/app/workflows/pipeline.py apps/api/tests/test_bold_metrics.py
git commit -m "feat: replace placeholder bold metrics with structured outputs"
```

### Task 4: Add Phase 1 API And Workflow Coverage

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/tests/test_api_flow.py`

- [ ] **Step 1: Write the failing API test**

```python
def test_chat_mentions_real_bold_metric_outputs_after_implementation(client):
    reply = client.post("/chat", json={"message": "Can you compute ALFF and seed connectivity?"}).json()["reply"]
    assert "ALFF" in reply
    assert "seed-to-ROI" in reply
    assert "fixed-coordinate spherical seeds" in reply
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_api_flow.py -k bold -v`
Expected: FAIL because chat still says ALFF/fALFF are only planned.

- [ ] **Step 3: Update API workflow messaging and validation wording**

```python
elif "alff" in message or "falff" in message or "bold" in message:
    if used_provider != "deepseek":
        reply = (
            "BOLD downstream metrics now support structured outputs including ALFF, "
            "fALFF, ReHo, tSNR, RSFA, seed-to-ROI summaries, and fixed-coordinate spherical seed runs."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/api/tests/test_api_flow.py -k bold -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/main.py apps/api/tests/test_api_flow.py
git commit -m "feat: expose bold downstream structured metrics through api messaging"
```

### Task 5: Add Descriptive Review Packaging

**Files:**
- Create: `apps/api/app/workflows/bold_descriptive_review.py`
- Test: `apps/api/tests/test_bold_descriptive_review.py`

- [ ] **Step 1: Write the failing descriptive review test**

```python
import json

from app.workflows.bold_descriptive_review import build_descriptive_review


def test_descriptive_review_writes_summary_and_figure_index(tmp_path):
    output_dir = build_descriptive_review(
        out_dir=tmp_path,
        subject_summaries=[
            {
                "subject_id": "01",
                "metrics": ["alff", "tsnr"],
                "seed_outputs": ["PCC_DMN"],
            }
        ],
    )
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["subject_count"] == 1
    assert "network_difference_descriptive_png" in summary
    assert "motion_qc_overlay_png" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_bold_descriptive_review.py -v`
Expected: FAIL because `bold_descriptive_review.py` does not exist.

- [ ] **Step 3: Implement the descriptive review builder**

```python
def build_descriptive_review(out_dir: Path, subject_summaries: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "network_fc_difference_descriptive.png").write_bytes(b"placeholder-png")
    (out_dir / "motion_qc_overlay.png").write_bytes(b"placeholder-png")
    summary = {
        "subject_count": len(subject_summaries),
        "subjects": subject_summaries,
        "network_difference_descriptive_png": str(out_dir / "network_fc_difference_descriptive.png"),
        "motion_qc_overlay_png": str(out_dir / "motion_qc_overlay.png"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_bold_descriptive_review.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/workflows/bold_descriptive_review.py apps/api/tests/test_bold_descriptive_review.py
git commit -m "feat: add bold descriptive review packaging"
```

### Task 6: Add Phase 2 Group Gating And SPM12-Style Output Scaffold

**Files:**
- Create: `apps/api/app/workflows/bold_group_analysis.py`
- Test: `apps/api/tests/test_bold_group_analysis.py`

- [ ] **Step 1: Write the failing group gating test**

```python
import pytest

from app.workflows.bold_group_analysis import validate_group_inputs


def test_group_analysis_requires_minimum_subjects_per_group():
    with pytest.raises(ValueError, match="at least 2 completed subjects per group"):
        validate_group_inputs(group_a=["sub-01"], group_b=["sub-02"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/api/tests/test_bold_group_analysis.py -v`
Expected: FAIL because `bold_group_analysis.py` does not exist.

- [ ] **Step 3: Implement the strict validation and output scaffold**

```python
def validate_group_inputs(group_a: list[str], group_b: list[str]) -> None:
    if len(group_a) < 2 or len(group_b) < 2:
        raise ValueError("Group analysis requires at least 2 completed subjects per group")


def build_group_review_scaffold(out_dir: Path) -> Path:
    voxel_dir = out_dir / "voxelwise"
    voxel_dir.mkdir(parents=True, exist_ok=True)
    (voxel_dir / "alff_mean_difference_stat.png").write_bytes(b"placeholder-png")
    (voxel_dir / "alff_mean_difference_glass.png").write_bytes(b"placeholder-png")
    (voxel_dir / "alff_mean_difference_peaks.tsv").write_text("x\ty\tz\tstat\n", encoding="utf-8")
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/api/tests/test_bold_group_analysis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/workflows/bold_group_analysis.py apps/api/tests/test_bold_group_analysis.py
git commit -m "feat: add bold group gating and review scaffold"
```

### Task 7: Two-Round Subagent Review Before Delivery

**Files:**
- Review only: `apps/api/app/workflows/bold_metrics.py`
- Review only: `apps/api/app/workflows/bold_seed_registry.py`
- Review only: `apps/api/app/workflows/bold_descriptive_review.py`
- Review only: `apps/api/app/workflows/bold_group_analysis.py`
- Review only: `apps/api/app/main.py`
- Review only: `apps/api/app/workflows/pipeline.py`

- [ ] **Step 1: Run the focused test suite**

Run: `pytest apps/api/tests/test_bold_result_contract.py apps/api/tests/test_bold_seed_registry.py apps/api/tests/test_bold_metrics.py apps/api/tests/test_bold_descriptive_review.py apps/api/tests/test_bold_group_analysis.py apps/api/tests/test_api_flow.py -k "bold or seed" -v`
Expected: PASS.

- [ ] **Step 2: Dispatch subagent review round 1 for scientific and clinical plausibility**

Prompt content must ask the reviewer to inspect:

- seed definition clarity
- whether descriptive outputs are being mislabeled as inferential
- whether group gating is strong enough for research claims
- whether the figure contract supports SPM12-like scientific review later

- [ ] **Step 3: Fix any round-1 issues and rerun targeted tests**

Run: `pytest apps/api/tests/test_bold_result_contract.py apps/api/tests/test_bold_seed_registry.py apps/api/tests/test_bold_metrics.py apps/api/tests/test_bold_descriptive_review.py apps/api/tests/test_bold_group_analysis.py apps/api/tests/test_api_flow.py -k "bold or seed" -v`
Expected: PASS again.

- [ ] **Step 4: Dispatch subagent review round 2 for visual-output and real-data-readiness**

Prompt content must ask the reviewer to inspect:

- whether the output contract carries enough metadata for real data review
- whether generated figure names and summary fields map cleanly into a future results UI
- whether the group comparison scaffold is visually aligned with SPM12-like expectations

- [ ] **Step 5: Fix any round-2 issues and rerun targeted tests**

Run: `pytest apps/api/tests/test_bold_result_contract.py apps/api/tests/test_bold_seed_registry.py apps/api/tests/test_bold_metrics.py apps/api/tests/test_bold_descriptive_review.py apps/api/tests/test_bold_group_analysis.py apps/api/tests/test_api_flow.py -k "bold or seed" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/workflows/bold_result_contract.py apps/api/app/workflows/bold_seed_registry.py apps/api/app/workflows/bold_metrics.py apps/api/app/workflows/bold_descriptive_review.py apps/api/app/workflows/bold_group_analysis.py apps/api/app/workflows/pipeline.py apps/api/app/main.py apps/api/tests/test_bold_result_contract.py apps/api/tests/test_bold_seed_registry.py apps/api/tests/test_bold_metrics.py apps/api/tests/test_bold_descriptive_review.py apps/api/tests/test_bold_group_analysis.py apps/api/tests/test_api_flow.py
git commit -m "feat: add structured bold downstream metrics and review scaffolding"
```
