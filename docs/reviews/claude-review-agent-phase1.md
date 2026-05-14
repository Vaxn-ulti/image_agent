# Claude Review Agent — Phase 1 Real Processing Readiness

**Date:** 2026-05-13  
**Scope:** Skill/docs style, backend workflow support, real data risks, frontend correctness.  
**Outcome:** 3 critical, 9 high, 8 medium, 5 low findings. Backend workflow construction is solid; frontend gating and config hygiene need fixes before real data runs.

---

## Findings by Severity

### CRITICAL

#### C1. `.env` secrets exposed in repo root
- **File:** `.env` (root), `.gitignore`
- **Finding:** `.env` contains `IMAGE_AGENT_SUDO_PASSWORD=yyf123` and `DEEPSEEK_API_KEY=sk-...` in plaintext. The `.gitignore` file exists but does NOT list `.env`.
- **Fix:** Add `.env` to `.gitignore` immediately. Rotate the exposed API key. Never commit secrets.

#### C2. Frontend `latestBoldPreprocTask` checks wrong workflow types
- **File:** `apps/desktop/src/main.jsx:111-118`
- **Finding:** The frontend function `latestBoldPreprocTask` looks for `bold_fmriprep` / `bold_fmriprep_validate` / `t1_deepprep` / `t1_deepprep_validate`. The actual BOLD preprocessing backend workflow types are `bold_deepprep` and `bold_deepprep_validate`. The `bold_fmriprep` type exists in `pipeline.py` IMAGES dict and `_commands` but is NOT registered in the WORKFLOWS list exposed by `main.py:35-47`. This means:
  - The frontend will never find a completed BOLD preprocessing task.
  - `latestBoldPreprocTask` always returns null → ALFF/fALFF workflows are permanently gated as unavailable.
  - The QSIPrep gating logic (which uses `latestBoldPreprocTask` for BOLD metric prechecks) is also broken.
  - Additionally, checking `t1_deepprep` as a BOLD preprocessing prerequisite is semantically wrong — a completed T1 DeepPrep does not mean a completed BOLD DeepPrep.
- **Fix:** Change `latestBoldPreprocTask` filter to check for `bold_deepprep` / `bold_deepprep_validate` instead of `bold_fmriprep` / `bold_fmriprep_validate`. Remove `t1_deepprep` / `t1_deepprep_validate` from the BOLD preproc check (or add a separate function for T1 status). Update the error messages at main.jsx:137-138 which also reference `bold_fmriprep`.

#### C3. Hardcoded FreeSurfer license path breaks portability
- **File:** `apps/api/app/workflows/pipeline.py:10` (`FS_LICENSE = Path("/home/yyf/codex/license.txt")`), `apps/api/app/core/config.py:28` (`FS_LICENSE = Path(os.environ.get("IMAGE_AGENT_FS_LICENSE", "/home/yyf/codex/license.txt"))`)
- **Finding:** The hardcoded default `/home/yyf/codex/license.txt` is user-specific. Any deployment on a different machine will fail all Docker workflows that require a FreeSurfer license mount (T1 DeepPrep, BOLD DeepPrep, QSIPrep, QSIRecon).
- **Fix:** Remove the hardcoded default. Require `IMAGE_AGENT_FS_LICENSE` to be set and fail-fast on startup if it's missing and Docker workflows are enabled.

---

### HIGH

#### H1. Hardcoded subject ID causes cross-subject overwrites
- **File:** `apps/api/app/workflows/pipeline.py:11` (`SUBJECT = "01"`)
- **Finding:** All BIDS-like trees and Docker commands use `sub-01` regardless of the actual subject. Multiple real subjects will overwrite each other's derivatives since the output directory key is only `task_id`, not subject. This works for MVP single-subject testing but will silently corrupt multi-subject real data.
- **Fix:** Derive subject label from the series metadata or assign incrementing subject IDs per project. At minimum, document that only single-subject projects are supported in this MVP.

#### H2. Output discovery `_register_outputs` is too generic — cannot distinguish output types
- **File:** `apps/api/app/workflows/pipeline.py:264-279`
- **Finding:** `_register_outputs` globs for `*.html`, `*.nii`, `*.nii.gz`, `*.tsv`, `*.json`, `*.tck`, `*.trk`, `*.csv` and assigns blanket `output_type` values (`html_report`, `nifti`, `tsv`, `json`, `tractography`, `connectome`). This means:
  - A DeepPrep segmentation NIfTI and a preprocessed BOLD NIfTI both get `output_type: "nifti"` — indistinguishable in the outputs API.
  - A QSIPrep HTML report and a QSIRecon HTML report both get `output_type: "html_report"`.
  - The workflow docs (`t1-deepprep-workflow.md`, `bold-fmri-workflow-draft.md`, `dwi-qsi-workflow.md`) specify distinct output types: `qc_report`, `segmentation`, `brain_mask`, `preprocessed_dwi`, `confounds`, `tractography`, `connectome`, `fa_map`, `md_map`. None of these are produced by the current implementation.
  - The mock DeepPrep (`deepprep.py:32-38`) DOES use specific output types (`qc_report`, `segmentation`, `chart`) which are inconsistent with both the workflow docs and the generic pipeline discovery.
- **Fix:** After real container execution, parse the known DeepPrep/QSIPrep/QSIRecon output structure using the documented output type names. Fall back to generic discovery only for unrecognized files and mark them with a distinct type like `unknown_file`.

#### H3. DeepSeek system prompt contradicts implemented BOLD support
- **File:** `apps/api/app/agent/deepseek.py:13`
- **Finding:** The system prompt says: *"BOLD/fMRI and other recognized sequences may be inventoried, but processing may be limited by the current MVP unless exposed by the backend."* This is stale — the backend now fully supports `bold_deepprep` and `bold_deepprep_validate` workflows with real Docker command construction. The prompt tells the agent to hedge on BOLD support when it should confidently recommend DeepPrep BOLD preprocessing.
- **Fix:** Update the system prompt to state: *"DeepPrep handles both T1 anatomical and fMRI/BOLD preprocessing. QSIPrep handles DWI preprocessing. QSIRecon handles DWI reconstruction from completed QSIPrep output."*

#### H4. DICOM upload does not group by `SeriesInstanceUID`
- **File:** `apps/api/app/main.py:188-212` (`upload_dicom`)
- **Finding:** The `upload_dicom` endpoint extracts a DICOM zip and treats the entire archive as a single `imaging_series` record with `sequence_label: "DICOM_ARCHIVE"`. It does not group DICOM files by `SeriesInstanceUID` as the ingest workflow docs specify (`dataset-ingest-workflow.md:29`: "Group DICOM by SeriesInstanceUID with patient/study guardrails"). Multi-series DICOM archives (e.g., a full study with T1, T2, DWI) will be lumped into one series, making per-modality workflow launching impossible.
- **Fix:** Either implement DICOM tag parsing to group by SeriesInstanceUID, or document that `upload_dicom` only supports single-series archives and users should use the dataset ingest path for multi-series DICOM.

#### H5. Ingest `is_dicom_file` silently trusts file extensions
- **File:** `apps/api/app/imaging/ingest.py:15-16`
- **Finding:** Files with `.dcm` or `.ima` extensions are classified as DICOM without verifying the DICM magic bytes at offset 128. Only files with other extensions go through the magic-byte check. A non-DICOM file renamed to `.dcm` would be passed to `dcm2niix`, which would fail or produce garbage.
- **Fix:** Always verify DICM magic bytes regardless of extension, or remove the extension shortcut entirely.

#### H6. DICOM conversion depends on host-installed `dcm2niix` without documentation
- **File:** `apps/api/app/imaging/ingest.py:168-170`
- **Finding:** `convert_dicom_dir` calls `dcm2niix` as a subprocess on the host. The deployment docs (`deployment.md`) do not list `dcm2niix` as a required dependency. A fresh deployment would silently fail DICOM conversion with no clear guidance.
- **Fix:** Add `dcm2niix` to deployment prerequisites in `deployment.md`. Consider wrapping it in a Docker container for isolation.

#### H7. Task queuing has no backpressure — unlimited concurrent containers
- **File:** `apps/api/app/main.py:340-342`
- **Finding:** Every `POST /series/{series_id}/run` spawns an immediate daemon thread with no limit on concurrent Docker containers. Multiple simultaneous DeepPrep/QSIPrep runs (each requesting `--cpus 8 --memory 24`) would oversubscribe the host.
- **Fix:** Add a semaphore or task queue that limits concurrent container launches to 1 (or a configurable number). Incrementing a counter in the DB would be sufficient for MVP.

#### H8. Chat endpoint logic race condition with DeepSeek and rules
- **File:** `apps/api/app/main.py:366-408`
- **Finding:** The chat handler:
  1. Calls `complete_chat` first and captures its reply.
  2. Then runs keyword-based rules that unconditionally overwrite `reply` when keywords match — even if DeepSeek already produced a good response. The `used_provider` tracking is inconsistent: if DeepSeek succeeds but a keyword triggers, `used_provider` gets reset to `"rules"` despite DeepSeek having run.
  3. If DeepSeek is unavailable, `reply` is set to a fallback string but is immediately overwritten by the keyword rules that follow.
- **Fix:** Only use rule-based replies when `used_provider` is NOT `"deepseek"` (i.e., when DeepSeek failed or wasn't configured). Do not overwrite a successful DeepSeek response.

#### H9. `t1_deepprep_mock` exposed to end users via `/workflows`
- **File:** `apps/api/app/main.py:46`
- **Finding:** The mock DeepPrep workflow appears in the public `/workflows` endpoint and is rendered as a button in the frontend for T1 series. This is an internal testing artifact that should not be user-facing.
- **Fix:** Remove `t1_deepprep_mock` from the WORKFLOWS list, or gate it behind a debug flag. Keep it available only via direct API calls for tests.

---

### MEDIUM

#### M1. Skill SKILL.md files are documentation, not registered Claude Code skills
- **Files:** `docs/skills/image-agent-operator/SKILL.md`, `docs/skills/image-agent-developer/SKILL.md`, `docs/skills/neuroimaging-workflow-runner/SKILL.md`
- **Finding:** The three SKILL.md files follow the skill-creator pattern (concise SKILL.md + detailed references + concrete examples/evals) and the content quality is good. However, they are plain markdown files under `docs/` — there is no indication they are registered as Claude Code skills via `settings.json` hooks or `.claude/skills/`. The "Reference Loading" sections instruct the reader to read reference files, but this only works if the skill system loads them. The `image-agent-operator` skill specifically targets "the built-in DeepSeek agent," but the operator's rules (grounding in backend data, metadata precedence, exact limitation sentence) are enforced in backend code, not by the skill itself.
- **Fix:** Clarify in a readme whether these skills are:
  - (a) Design documents for humans implementing the agent behavior, or
  - (b) Actual Claude Code skills to be registered via `.claude/settings.json`.
  If (b), move them to the correct location and register them. If (a), remove the `---` YAML frontmatter and "Reference Loading" sections, or note they are implementation specs.

#### M2. `bold_fmriprep` is dead code in the pipeline but present
- **File:** `apps/api/app/workflows/pipeline.py:19,228-233`
- **Finding:** The IMAGES dict includes `"bold_fmriprep": "nipreps/fmriprep:latest"` and `_commands` has a full `bold_fmriprep` command construction. This workflow type is not in the WORKFLOWS list, not gated by `validate_run_request`, and has no frontend button. Its presence is confusing — it suggests fMRIPrep might be the BOLD preprocessing path, contradicting every document and the actual `bold_deepprep` implementation.
- **Fix:** Remove `bold_fmriprep` from IMAGES and `_commands`, or add a comment explaining it is a future alternative path. The docs consistently say DeepPrep handles BOLD, so dead fMRIPrep code undermines that message.

#### M3. Workflow docs reference DeepPrep `--anat_only` flag but pipeline code does not use it
- **File:** `docs/workflows/t1-deepprep-workflow.md:45` vs `apps/api/app/workflows/pipeline.py:199`
- **Finding:** The T1 workflow doc says `--anat_only` should be passed to DeepPrep. The actual pipeline code passes `--anat_only` (line 199). OK, this is actually consistent. Let me re-check.

Actually, let me re-read the command. The doc says `--anat_only` and the code at line 199 has `"--anat_only"`. That's consistent.

But the workflow doc's command pattern uses `{fs_license}:/opt/freesurfer/license.txt:ro` while the pipeline code uses explicit `--fs_license_file /opt/freesurfer/license.txt`. The doc doesn't show `--fs_license_file`, `--skip_bids_validation`, `--cpus`, or `--memory` flags. This is a documentation gap — the actual Docker commands have more flags than the documented patterns.

#### M4. Log path inconsistency during task creation
- **File:** `apps/api/app/main.py:329-337`
- **Finding:** Task creation first writes `log_path = PROJECTS_ROOT / str(project_id) / "logs" / "pending.log"`, inserts the task, then immediately updates it to `{task_id}.log`. If a reader or concurrent process reads the task between INSERT and UPDATE, they see an incorrect log path. Additionally, `pending.log` is never cleaned up.
- **Fix:** Compute the final log path upfront before the INSERT.

#### M5. `_commands` for `dwi_qsirecon` doesn't match the QSIRecon doc's mount pattern
- **File:** `docs/workflows/dwi-qsi-workflow.md:68` vs `apps/api/app/workflows/pipeline.py:213-219`
- **Finding:** The doc says QSIRecon mounts `{qsiprep_output}:/data:ro`, but the pipeline code mounts `{source}:/data:ro` where `source` is `qsiprep_output or dirs["bids"]`. The fallback to `dirs["bids"]` is a silent wrong behavior — if `qsiprep_output` is None (shouldn't happen due to the guard in `run_pipeline_task`), QSIRecon would run on raw BIDS data instead of QSIPrep output. This is a defensive-coding issue.

#### M6. No work-directory cleanup after task completion
- **File:** `apps/api/app/workflows/pipeline.py` (no cleanup logic)
- **Finding:** Docker work directories under `data/projects/{project_id}/derivatives/{task_id}/work` are never cleaned up. DeepPrep and QSIPrep work directories can be tens of gigabytes. The MVP will exhaust disk space with repeated runs.
- **Fix:** Add a cleanup step after successful completion that removes the work directory (or make it configurable). At minimum, document the need for manual cleanup.

#### M7. `validate_run_request` checks `bold_alff`/`bold_falff` prerequisites against `bold_fmriprep` and `t1_deepprep`
- **File:** `apps/api/app/main.py:300-317`
- **Finding:** The ALFF/fALFF validate check (line 306) looks for `bold_fmriprep_validate`, `bold_fmriprep`, `t1_deepprep_validate`, or `t1_deepprep` as prerequisite tasks. It should check for `bold_deepprep` / `bold_deepprep_validate` instead of `bold_fmriprep`. The inclusion of `t1_deepprep` as a BOLD metric prerequisite is semantically wrong — a T1 anatomical preprocessing task is not a valid prerequisite for a BOLD-derived metric.
- **Fix:** Change `bold_fmriprep` references to `bold_deepprep`. Remove `t1_deepprep` from BOLD metric prerequisite checks.

#### M8. Container resource limits are hardcoded
- **File:** `apps/api/app/workflows/pipeline.py:199,205,211,218,229`
- **Finding:** DeepPrep commands hardcode `--cpus 8 --memory 24`. QSIPrep/QSIRecon commands hardcode `--nthreads 8 --omp-nthreads 4 --mem 24000`. These cannot be adjusted without code changes.
- **Fix:** Make CPU/memory limits configurable via environment variables.

---

### LOW

#### L1. `.gitignore` is incomplete
- **File:** `.gitignore`
- **Finding:** The `.gitignore` file is nearly empty. It should cover at minimum: `.env`, `__pycache__/`, `node_modules/`, `*.pyc`, `.venv/`, `data/`, `logs/`, `dist/`, `*.pid`, and `.claude/`.
- **Fix:** Add standard Python/Node/git ignore patterns.

#### L2. Doc references mention `bold_fmriprep` as an alternative
- **Files:** `docs/skills/image-agent-developer/references/examples-evals.md:63`, `docs/skills/image-agent-operator/references/dialogue-policy.md:line mentioning fMRIPrep`
- **Finding:** The developer eval checklist says *"No README or broad process document is added for skills"* — good. But some reference docs still mention fMRIPrep as if it's an active path when only DeepPrep is actually wired.
- **Fix:** Grep for `fmriprep` across all docs and either remove or clearly mark as "future path."

#### L3. `dataset_description.json` `DatasetType` is always `"raw"`, even for derivatives
- **File:** `apps/api/app/workflows/pipeline.py:102-104` (`_dataset_description`)
- **Finding:** The BIDS-like trees built under `derivatives/{task_id}/bids` are marked as `"DatasetType": "raw"`. Per BIDS spec, derived data should have `"DatasetType": "derivative"`.
- **Fix:** Change to `"derivative"` for task-scoped BIDS trees (or accept this as a deliberate simplification for container compatibility — but document it).

#### L4. Frontend T1 series row shows `t1_deepprep_mock` button alongside real workflow buttons
- **File:** `apps/desktop/src/main.jsx:254`
- **Finding:** `SeriesRow` shows `t1_deepprep_mock` for T1 series. This is an internal testing workflow visible to all users.
- **Fix:** Remove `t1_deepprep_mock` from the frontend buttons array.

#### L5. `_docker_prefix` and `_run_command` API key exposure risk in logs
- **File:** `apps/api/app/workflows/pipeline.py:157-161,282-296`
- **Finding:** `_sudo_docker_prefix` reads `IMAGE_AGENT_SUDO_PASSWORD` from the environment and pipes it to sudo's stdin. The `_run_command` function writes the full command (including `sudo -S docker ...`) to task logs via `_append`. While the password itself isn't echoed in the command string, if sudo or Docker emits the password in stderr/stdout, it would be captured in logs.
- **Fix:** Verify that sudo's stdin password is not echoed in the output. Consider using a sudoers NOPASSWD rule for Docker instead of piping the password.

---

## Summary by Focus Area

### 1. Workflow Docs and Skills

**Verdict: Good structure, minor gaps.**

- All three SKILL.md files follow the concise + references + examples/evals pattern. The operator skill's rules (backend grounding, exact limitation sentence, BOLD → DeepPrep) are well-defined.
- The workflow docs (`t1-deepprep-workflow.md`, `bold-fmri-workflow-draft.md`, `dwi-qsi-workflow.md`, `dataset-ingest-workflow.md`) each include purpose, eligibility rules, BIDS-like paths, Docker commands, progress steps, outputs, and concrete eval cases. This is exactly the pattern requested.
- **Gap:** Docker command patterns in workflow docs omit flags present in the actual pipeline code (`--skip_bids_validation`, `--cpus`, `--memory`, `--fs_license_file`, `--bold_task_type`). The docs and code will diverge further if not kept in sync.
- **Gap:** Skills are not registered as Claude Code skills — they function as implementation specs for human developers. Clarify intent.

### 2. Backend Workflow Support

**Verdict: Core paths implemented, three correctness bugs.**

- T1 DeepPrep: real Docker command construction ✅, validate mode ✅, mock fallback ✅.
- BOLD/fMRI DeepPrep: real Docker command construction ✅, validate mode ✅, BIDS-like func tree ✅.
- DWI QSIPrep: real Docker command construction ✅, bval/bvec requirement enforced ✅, validate mode ✅.
- DWI QSIRecon: real Docker command construction ✅, QSIPrep-output-as-input ✅, validate mode ✅.
- DWI Full chain: sequential QSIPrep→QSIRecon ✅, skip-on-failure ✅.
- **Bug:** Chat and ALFF/fALFF gating reference `bold_fmriprep` instead of `bold_deepprep` (C2, M7).
- **Bug:** DICOM upload doesn't group by SeriesInstanceUID (H4).
- **Bug:** Chat endpoint overwrites DeepSeek response with rules (H8).

### 3. Real Data Risks

**Verdict: Config and isolation issues must be addressed before real data.**

| Risk | Severity |
|------|----------|
| `.env` secrets in repo root | Critical |
| Hardcoded FS_LICENSE path | Critical |
| Hardcoded subject ID (sub-01 overwrites) | High |
| dcm2niix host dependency not documented | High |
| DICOM extension trust without magic-byte check | High |
| Generic output type discovery can't distinguish results | High |
| No task concurrency limit | High |
| No work-directory cleanup | Medium |
| Log path inconsistency during task creation | Medium |

### 4. Frontend Correctness

**Verdict: One critical bug, one exposure, otherwise correct.**

- **Critical:** `latestBoldPreprocTask` looks for `bold_fmriprep` not `bold_deepprep` — breaks BOLD metric gating (C2).
- **Exposure:** `t1_deepprep_mock` button visible to users (L4).
- The workflow button mapping per modality (T1→DeepPrep, BOLD→DeepPrep, DWI→QSIPrep/QSIRecon/full) is correct.
- The inventory panel correctly surfaces modalities, sequences, conversion status, and unsupported sequences.
- The runtime panel correctly reports Docker image availability and FreeSurfer license status.
- Upload paths (single NIfTI, DWI set, DICOM zip, mixed dataset zip) are all wired.

---

## Recommended Fix Order

1. **Immediately:** Add `.env` to `.gitignore`; rotate exposed API key (C1).
2. **Before real data:** Fix `latestBoldPreprocTask` to use `bold_deepprep` (C2), remove hardcoded FS_LICENSE default (C3), fix Hardcoded subject ID (H1), fix validate_run_request ALFF/fALFF gating (M7), fix chat race condition (H8).
3. **Before multi-user:** Add task concurrency limiting (H7), implement work-directory cleanup (M6), update DeepSeek system prompt (H3).
4. **Before production:** Fix output discovery specificity (H2), implement DICOM SeriesInstanceUID grouping (H4), containerize or document dcm2niix (H6), remove `t1_deepprep_mock` from user-facing endpoints (H9, L4).
5. **Cleanup:** Remove dead `bold_fmriprep` code (M2), sync Docker command flags between docs and code (M3), complete `.gitignore` (L1).
