from __future__ import annotations

import sys

from app.services import legacy_service


PATCHABLE_MAIN_ATTRS = (
    "PROJECTS_ROOT",
    "REPO_ROOT",
    "AgentRunner",
    "ModelGateway",
    "complete_chat",
    "build_rag_response",
    "run_pipeline_task",
    "run_mock_deepprep",
    "local_rag_index_status",
    "build_local_rag_index",
    "resolve_task_output_dirs",
    "check_scientific_report_output",
    "run_group_analysis",
    "run_descriptive_review",
    "read_project_context",
)


def legacy():
    main = sys.modules.get("app.main")
    if main is not None:
        for attr in PATCHABLE_MAIN_ATTRS:
            if hasattr(main, attr):
                setattr(legacy_service, attr, getattr(main, attr))
    return legacy_service
