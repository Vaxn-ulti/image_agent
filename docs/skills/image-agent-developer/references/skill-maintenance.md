# Skill Maintenance

Update skills when execution or review exposes a repeatable failure point that another agent could avoid.

## Failure Update Flow

1. Capture the failing task id, command, image tag, logs, and observed status transition.
2. Classify the failure as code defect, container/runtime capability, data/input eligibility, documentation gap, or orchestration gap.
3. Update the narrowest skill reference that would have prevented the repeated mistake.
4. Keep `SKILL.md` concise; add only a pointer when a new reference is needed.
5. Update workflow docs when the product contract changed.
6. Re-run skill validation if available, then run a Markdown sanity check and the relevant test matrix.
7. Hand off with changed skill files, why the guidance changed, and which agent must act next.

## Current Recorded Failures

- DWI QSIPrep tasks `46` and `47` used `eddy_cpu`, ran too long, were stopped, and are marked `failed`.
- The remediation is not to retry CPU eddy. Use CUDA eddy config plus a CUDA-enabled QSIPrep/FSL image.
- `pennlinc/qsiprep:latest` exposes `eddy_cuda11.0` at `/app/.pixi/envs/qsiprep/bin/`. Detection uses `eddy_cuda*` glob to accept versioned binaries. Backend symlinks `eddy_cuda` → `eddy_cuda11.0` for QSIPrep compatibility.
- Real DWI tasks 61 and 62 are running with GPU/CUDA eddy.

## Acceptance Checklist

- Agent role boundaries are clear.
- DWI/QSI GPU policy names both command behavior and the eddy_cuda* versioned binary strategy.
- Review/test matrix includes backend, desktop, and container validation checks.
- Remaining blockers are assigned to the orchestrator rather than hidden in skill text.
- Final acceptance requires real container processing (not validate-only) with real data and registered outputs.
- QSIPrep commands include `--eddy-config /eddy_cuda_config.json` with `use_cuda: true`.
- QSIRecon commands include `--recon-spec`.
- Tests run with `apps/api/.venv/bin/pytest -q apps/api/tests`.
