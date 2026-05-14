You are the Claude review/test agent for image_agent. Work in /home/yyf/project/image_agent.

Diagnose the current real DWI QSIPrep task 65 stall and recommend the safest next action. Do not stop containers and do not edit files.

Facts:
- task 65 project 13 series 24 dwi_qsiprep, container b0aaeabd76b0, BIDS DWI about 87MB with 129 bvals.
- Container command uses QSIPrep with --gpus all, --nthreads 4 --omp-nthreads 2 --mem 16000, --eddy-config use_cuda true.
- eddy_cuda10.2 process PID 2595560 has been running ~3.5h at 100% CPU, GPU memory ~368 MiB, low GPU utilization.
- Docker/QSIPrep logs last reported entering eddy at 19:01 and later anat_nlin completed at 12:49 UTC; host eddy directory last modified 19:35 CST with only small eddy parameter files and an unfinished json. No task log updates because task 65 is orphaned after API restart; watchdog is waiting docker exit.
- task 66 waits for lock and should not start until task 65 is resolved.
- Previous tasks 61/62 were killed after memory pressure; current task 65 was rerun serially.

Please inspect logs/work dirs/code as needed and answer:
1. Is task 65 likely making real progress or effectively hung?
2. If hung, what exact evidence justifies stopping only b0aaeabd76b0?
3. What QSIPrep/eddy config changes should the dev agent make for faster/stabler real runs? Consider eddy nthreads, CUDA binary selection, output resolution, skipping optional expensive steps only if scientifically acceptable for MVP validation.
4. What rerun plan should be used after stopping 65, preserving task/data safety and not touching unrelated containers?

Return concrete commands/patch recommendations, not a generic explanation.
