You are the Claude review agent for image_agent. Work in /home/yyf/project/image_agent.

Review the uncommitted orphan recovery patch. Do not edit files. Focus on correctness and safety.

Context:
- Developer added Docker labels in apps/api/app/workflows/pipeline.py and recovery script apps/api/app/workflows/recovery.py.
- Real task 65 is still running in existing unlabeled container b0aaeabd76b0; do not stop or touch it.
- Future recovery must avoid unrelated containers and patient data. It must not kill containers.
- Containers can mount project dirs plus read-only support files such as the FreeSurfer license outside PROJECTS_ROOT.

Please review:
1. Can recovery.py actually recover future image_agent containers that mount read-only support files outside PROJECTS_ROOT?
2. Are label injection and /admin/containers safe and correct?
3. Any regression risk in scripts_monitor_task.sh and scripts_watch_qsirecon_65_66.sh?
4. Are tests sufficient, or are safety predicates over/under strict?

Return findings with file/function references and concrete fix recommendations. Do not commit.
