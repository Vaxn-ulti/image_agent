# QSIPrep Container-Task Map — 2026-05-14 17:38 CST

## 1. Task status

| ID | Project | Workflow | Status | Progress | Started (UTC) | Log lines | Log last modified |
|----|---------|----------|--------|----------|---------------|-----------|-------------------|
| 61 | 13 | dwi_qsiprep | running | 20 | 05:52:33 | 732 | 08:57 UTC (16:57 CST) — **stale 8.7h** |
| 62 | 15 | dwi_qsiprep | running | 20 | 05:52:36 | 588 | 06:46 UTC (14:46 CST) — **stale 10.8h** |

Both tasks are with `--participant-label 01`, `--anat-modality none` (62) / anat-from-T1w (61), and `--mem 24000`.

## 2. Container map

### Tasks 61 and 62 — `pennlinc/qsiprep:latest` with eddy_cuda symlink

| Task | Docker PID | QSIPrep PID | Work dir (host) | Eddy PID | Eddy type | GPU mem |
|------|-----------|-------------|-----------------|----------|-----------|---------|
| 61 | 2165421 | 2165464 | `data/projects/13/derivatives/61/work` | 2300269 | eddy_cuda10.2 | ~368 MiB |
| 62 | 2164763 | 2164806 | `data/projects/15/derivatives/62/work` | 2275921 | eddy_cuda10.2 | ~356 MiB |

Both share GPU 0. Commands use `ln -sf eddy_cuda11.0 .../eddy_cuda && ln -sf eddy_cuda11.0 .../eddy_cuda10.2` at entrypoint.

### Four old/other containers — `pennlinc/qsiprep:latest` (NOT tasks 61/62)

| Docker PID | Participant | Eddy PID | Eddy type | Work dir (host) |
|-----------|-------------|----------|-----------|-----------------|
| 2203280 | 067S6442 | 2460114 | eddy_cpu | `Project/cn_dwi_qsi_20260512/work/sub-067S6442` |
| 2203299 | 067S6518 | 2445595 | eddy_cpu | `Project/cn_dwi_qsi_20260512/work/sub-067S6518` |
| 2203312 | 067S6443 | 2505732 | eddy_cpu | `Project/cn_dwi_qsi_20260512/work/sub-067S6443` |
| 2203381 | 067S6957 | 2500912 | eddy_cpu | `Project/cn_dwi_qsi_20260512/work/sub-067S6957` |

These four come from a **different project directory** (`Project/cn_dwi_qsi_20260512/`), use `--anat-modality none` implicitly, and run `eddy_cpu` (not cuda). They have HTTP proxy settings configured. Each runs at 260-336% CPU.

**Total: 6 qsiprep containers × 24 GB = 144 GB requested on 91 GB RAM host.**

## 3. Stalled/failing evidence

### Task 61 — SynthSeg OOM crash (non-fatal)
```
mri_synthseg --cpu --i <t1w> --threads 1 --post <post> --qc <qc> --o <aseg>
Killed
```
- SynthSeg was killed by OOM killer at 06:40 UTC. The node raised `NodeExecutionError`. Crash file saved to `/out/sub-01/log/.../crash-...-synthseg-....txt`.
- Pipeline **continued** past the crash: anat_nlin_normalization finished at 08:57 UTC.
- After 08:57 UTC, no further log output. Pipeline is blocked waiting for the DWI eddy node to finish.

### Task 62 — silent at eddy
- Last log entry at 06:46 UTC: `[Node] Finished "mask_brain"` and `[Node] Executing "eddy"`.
- Since then: zero log output. Pipeline blocked on eddy completion.

### System memory crisis
- **Swap: 8.0/8.0 GiB fully saturated** (416 KiB free)
- **OOM killer active**: wireplumber, pipewire-pulse, dbus, cloudflared all killed at 15:47 CST
- 91 GiB RAM, 58 GiB used, but 6 qsiprep containers each requesting `--mem 24000` = 144 GiB total
- Memory overcommit ratio: ~1.6:1

### Eddy still making progress (slowly)
- Both eddy_cuda10.2 processes active on GPU 0 at 82-85% CPU
- Intermediate `eddy_post_eddy_shell_PE_translation_parameters` files updated at 16:17 (task 61) and 16:10 (task 62) — ~1-1.5h ago
- No final `.nii.gz` outputs yet; `_unfinished.json` still present
- Eddy `--niter=5` with `--data_is_shelled` — computationally heavy

### GPU
- GPU 0: 1020 MiB / 24576 MiB, two eddy_cuda10.2 processes, 2% utilization
- GPU 1: idle (8 MiB used)

## 4. Safe action recommendation

**Do NOT stop containers.** They are making progress, just slowly.

1. **Kill the 4 old `067S*` containers** (PIDs 2203280, 2203299, 2203312, 2203381). These are outside the image_agent project, use `eddy_cpu` (no GPU benefit), and each consumes ~2 GB RSS + Python worker memory. Freeing them would reclaim ~30-40 GB memory.

2. **After killing old containers, monitor swap**. If swap remains saturated, consider stopping either task 61 or 62 to let the other complete with adequate memory.

3. **For future runs**: limit concurrent qsiprep containers to ≤2 on this hardware (91 GB / 24 GB per container ≈ 3.8, but leave headroom for OS and GPU). Set `--mem 20000` instead of 24000 to reduce per-container footprint.

4. **Do not restart task 61** for the SynthSeg crash — the pipeline handled it gracefully and continued. Re-running would waste the ~3h of eddy computation already done.

## 5. Development fix needed

1. **Container concurrency guard**: The task launcher should check available system memory before starting a new container. A simple heuristic: `total_container_mem_limit < 0.7 * system_ram`.

2. **Progress reporting during eddy**: The progress stays at 20 throughout the entire eddy run (which can take hours). Add heartbeat updates or parse eddy iteration progress from its output to bump the progress counter.

3. **SynthSeg OOM resilience**: Consider setting `--threads 1` for mri_synthseg (already done) but also reduce its memory footprint or add a retry-on-OOM wrapper. The OOM kill produced a non-fatal crash that the pipeline recovered from, but the missing SynthSeg segmentation may degrade downstream anat-based normalization quality.
