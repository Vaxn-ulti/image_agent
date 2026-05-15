# Claude Dev Agent: sync DWI/QSI resource profile and continue real acceptance

Controller update:
- User chose QSIPrep `--nthreads 8 --omp-nthreads 4 --mem 24000`.
- QSIRecon should use `--nprocs 8 --omp-nthreads 4 --mem 24000`.
- Commit `6162be9` implements this and tests passed: 43 passed.
- Current real QSIPrep task 78 is running; task 77 is waiting on the DWI lock. Watcher `scripts_watch_qsirecon_77_78.sh` will submit QSIRecon after completion.
- Task 78 is in pre-eddy `dwidenoise -nthreads 4`; do not stop it without stale-log/container evidence.

Review code/docs against the reference scripts under /home/yyf/Project/cn_dwi_qsi_20260512 and /home/yyf/Project/qsitest_20260507. If you find a small bug, patch it, run focused tests, and report changed files. Preserve CUDA eddy detection, DWI lock, is_shelled auto-inference, cnr_maps true, dont_peas true, niter 3, and no eddy_cpu fallback. Do not count validation-only as acceptance.
