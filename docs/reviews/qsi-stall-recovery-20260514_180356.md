# QSI Stall Recovery 20260514_180356

## Evidence
2026-05-14 16:57:41.789669567 +0800 75950 data/projects/13/logs/61.log
2026-05-14 14:46:30.598463608 +0800 59351 data/projects/15/logs/62.log

## Task status before
{'id': 61, 'project_id': 13, 'series_id': 24, 'workflow_type': 'dwi_qsiprep', 'status': 'running', 'progress': 20, 'error_message': None, 'started_at': '2026-05-14T05:52:33.109369+00:00', 'finished_at': None, 'log_path': '/home/yyf/project/image_agent/data/projects/13/logs/61.log'}
{'id': 62, 'project_id': 15, 'series_id': 27, 'workflow_type': 'dwi_qsiprep', 'status': 'running', 'progress': 20, 'error_message': None, 'started_at': '2026-05-14T05:52:36.210013+00:00', 'finished_at': None, 'log_path': '/home/yyf/project/image_agent/data/projects/15/logs/62.log'}

## Target containers before
CONTAINER ID                                                       IMAGE                     COMMAND                                                                                                                                                                                                                                                                                                                                                                                                                                                CREATED       STATUS       PORTS     NAMES
8081cd8c2f30d754fc858292870f5d43f1755b14dd7226f426301ecf7793982d   pennlinc/qsiprep:latest   "bash -c 'ln -sf eddy_cuda11.0 /app/.pixi/envs/qsiprep/bin/eddy_cuda && ln -sf eddy_cuda11.0 /app/.pixi/envs/qsiprep/bin/eddy_cuda10.2 && exec /app/.pixi/envs/qsiprep/bin/qsiprep /data /out participant --participant-label 01 --fs-license-file /opt/freesurfer/license.txt --skip-bids-validation --output-resolution 2 --nthreads 8 --omp-nthreads 4 --mem 24000 -w /work --notrack --eddy-config /eddy_cuda_config.json'"                        4 hours ago   Up 4 hours             gallant_wilson
49c539854f71de19a7cea469b9c94e05781cd6a7062489f81f3fcedce50b79e1   pennlinc/qsiprep:latest   "bash -c 'ln -sf eddy_cuda11.0 /app/.pixi/envs/qsiprep/bin/eddy_cuda && ln -sf eddy_cuda11.0 /app/.pixi/envs/qsiprep/bin/eddy_cuda10.2 && exec /app/.pixi/envs/qsiprep/bin/qsiprep /data /out participant --participant-label 01 --fs-license-file /opt/freesurfer/license.txt --skip-bids-validation --output-resolution 2 --nthreads 8 --omp-nthreads 4 --mem 24000 -w /work --notrack --eddy-config /eddy_cuda_config.json --anat-modality none'"   4 hours ago   Up 4 hours             amazing_galois

## System pressure
               total        used        free      shared  buff/cache   available
Mem:            91Gi        59Gi        18Gi        30Gi        44Gi        31Gi
Swap:          8.0Gi       8.0Gi       1.3Mi
0, NVIDIA TITAN RTX, 3, 1020, 24576
1, NVIDIA TITAN RTX, 0, 8, 24576

## Stop log
8081cd8c2f30
49c539854f71

## Task status after
{'id': 61, 'status': 'failed', 'progress': 20, 'error_message': 'stalled: real QSIPrep container stopped after stale logs, full swap, low GPU use, and SynthSeg killed evidence; rerun with reduced DWI concurrency/resources', 'finished_at': '2026-05-14T10:04:10.236172+00:00'}
{'id': 62, 'status': 'failed', 'progress': 20, 'error_message': 'stalled: real QSIPrep container stopped after stale logs, full swap, low GPU use, and SynthSeg killed evidence; rerun with reduced DWI concurrency/resources', 'finished_at': '2026-05-14T10:04:10.236919+00:00'}
