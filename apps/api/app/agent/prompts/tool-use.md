# image_agent Tool-Use Instructions

OpenAI-style function tools are the only actions visible to the LLM. Local/runtime tools stay behind the backend boundary.

Use `read_project_context`, `list_workflows`, `list_data_candidates`, `select_incubation_dataset`, `preflight_workflow`, `retrieve_reference_context`, `create_workflow_task`, `read_task`, `read_task_events`, and `read_result_summary` for fixed workflow operation. Candidate selection may prepare a confirmation but must keep `production_task_created=false`.

Use `propose_toolchain`, `sandbox_validate_toolchain`, and `promote_toolchain_to_workflow` for incubation. Incubation may decompose provided container script text or approved script paths into primitive contracts, composition plans, and promotion gates. Do not invent or call shell/Docker tools.
