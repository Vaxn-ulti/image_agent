from pathlib import Path


def test_main_entrypoint_is_thin_and_routes_are_split():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert len(main_source.splitlines()) <= 450
    assert "legacy_service" not in main_source
    assert "_legacy" not in main_source
    for route_name in (
        "system",
        "agent",
        "auth",
        "projects",
        "uploads",
        "series",
        "tasks",
        "results",
        "reports",
        "chat",
    ):
        assert (root / "app" / "routes" / f"{route_name}.py").exists()

    for service_name in (
        "project_service",
        "upload_service",
        "task_service",
        "result_service",
        "agent_service",
    ):
        assert (root / "app" / "services" / f"{service_name}.py").exists()


def test_low_risk_services_do_not_delegate_simple_logic_to_legacy_service():
    root = Path(__file__).resolve().parents[1]
    project_service = (root / "app" / "services" / "project_service.py").read_text(encoding="utf-8")
    agent_service = (root / "app" / "services" / "agent_service.py").read_text(encoding="utf-8")
    task_service = (root / "app" / "services" / "task_service.py").read_text(encoding="utf-8")
    result_service = (root / "app" / "services" / "result_service.py").read_text(encoding="utf-8")
    upload_service = (root / "app" / "services" / "upload_service.py").read_text(encoding="utf-8")

    assert "legacy" not in project_service
    assert "from app.services.compat import legacy" not in result_service
    assert "legacy()" not in result_service
    assert "from app.services.compat import legacy" not in agent_service
    assert "legacy()" not in agent_service
    for function_name in (
        "def health",
        "def list_workflows",
        "def get_result_contract",
        "def deployment",
        "def agent_rag_status",
        "def agent_rag_rebuild",
        "def agent_model_status",
        "def agent_rag_query",
        "def agent_verify_scientific_reports",
        "def runtime_containers",
        "def admin_containers",
    ):
        start = agent_service.index(function_name)
        next_function = agent_service.find("\ndef ", start + 1)
        body = agent_service[start:] if next_function == -1 else agent_service[start:next_function]
        assert "legacy()" not in body

    for function_name in (
        "def list_project_tasks",
        "def get_series",
        "def validate_run_request",
        "def create_series_task",
        "def run_series",
        "def get_task",
    ):
        start = task_service.index(function_name)
        next_function = task_service.find("\ndef ", start + 1)
        body = task_service[start:] if next_function == -1 else task_service[start:next_function]
        assert "legacy()" not in body

    for function_name in (
        "def get_logs",
        "def get_outputs",
        "def get_result_summary",
        "def get_task_artifact_manifest",
        "def get_task_artifact",
        "def bold_group_analysis",
        "def bold_descriptive_review",
    ):
        start = result_service.index(function_name)
        next_function = result_service.find("\ndef ", start + 1)
        body = result_service[start:] if next_function == -1 else result_service[start:next_function]
        assert "legacy()" not in body

    for function_name in (
        "def upload",
        "def upload_dwi",
        "def upload_dicom",
        "def create_upload_session",
        "def ingest_dataset",
        "def get_inventory",
        "def list_series",
    ):
        start = upload_service.index(function_name)
        next_function = upload_service.find("\ndef ", start + 1)
        body = upload_service[start:] if next_function == -1 else upload_service[start:next_function]
        assert "legacy()" not in body


def test_legacy_bridge_modules_are_removed():
    root = Path(__file__).resolve().parents[1]

    assert not (root / "app" / "services" / "compat.py").exists()
    assert not (root / "app" / "services" / "legacy_service.py").exists()

    dependencies_source = (root / "app" / "dependencies.py").read_text(encoding="utf-8")
    assert "services.compat" not in dependencies_source
    assert "legacy_service" not in dependencies_source
    assert "legacy()" not in dependencies_source


def test_services_delegate_background_execution_to_executor_boundary():
    root = Path(__file__).resolve().parents[1]

    assert (root / "app" / "services" / "background.py").exists()
    for service_name in ("task_service.py", "upload_service.py"):
        service_source = (root / "app" / "services" / service_name).read_text(encoding="utf-8")
        assert "from threading import Thread" not in service_source
        assert "Thread(" not in service_source
        assert "submit_background" in service_source


def test_services_use_shared_runtime_overrides_for_main_patch_compatibility():
    root = Path(__file__).resolve().parents[1]

    assert (root / "app" / "services" / "runtime_overrides.py").exists()
    for service_name in (
        "agent_service.py",
        "project_service.py",
        "result_service.py",
        "task_service.py",
        "upload_service.py",
    ):
        service_source = (root / "app" / "services" / service_name).read_text(encoding="utf-8")
        assert 'sys.modules.get("app.main")' not in service_source
        assert "main_patch_attr" in service_source or "main_projects_root" in service_source


def test_services_use_shared_db_query_helpers_for_row_reads():
    root = Path(__file__).resolve().parents[1]

    assert (root / "app" / "db" / "queries.py").exists()
    for service_name in (
        "agent_service.py",
        "result_service.py",
        "task_service.py",
        "upload_service.py",
    ):
        service_source = (root / "app" / "services" / service_name).read_text(encoding="utf-8")
        assert "def _rows(" not in service_source
        assert "fetch_rows" in service_source


def test_main_compatibility_exports_live_outside_fastapi_entrypoint():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert (root / "app" / "main_compat.py").exists()
    assert "install_main_compat_exports" in main_source
    for forbidden_import in (
        "from app.agent.deepseek",
        "from app.agent.graph",
        "from app.agent.model_gateway",
        "from app.agent.rag_index",
        "from app.agent.rag_orchestration",
        "from app.agent.tools",
        "from app.schemas import",
        "from app.workflows.deepprep",
        "from app.workflows.pipeline",
        "from app.workflows.bold_group_analysis",
        "from app.workflows.bold_descriptive_review",
    ):
        assert forbidden_import not in main_source


def test_main_lifecycle_and_error_handlers_live_outside_entrypoint():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")
    factory_source = (root / "app" / "app_factory.py").read_text(encoding="utf-8")

    assert (root / "app" / "app_hooks.py").exists()
    assert "register_app_hooks(app)" in factory_source
    for forbidden in (
        "from app.db.database import init_db",
        "from app.agent.contracts import agent_api_error_detail",
        "RequestValidationError",
        "request_validation_exception_handler",
        "@app.on_event",
        "@app.exception_handler",
    ):
        assert forbidden not in main_source


def test_fastapi_app_factory_owns_middleware_routes_and_hooks():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert (root / "app" / "app_factory.py").exists()
    assert "app = create_app()" in main_source
    for forbidden in (
        "from fastapi import FastAPI",
        "from fastapi.middleware.cors import CORSMiddleware",
        "from app.routes import",
        "register_app_hooks(app)",
        "app.add_middleware",
        "app.include_router",
    ):
        assert forbidden not in main_source


def test_services_use_shared_imaging_series_parser():
    root = Path(__file__).resolve().parents[1]

    assert (root / "app" / "imaging" / "series_records.py").exists()
    for service_name in ("task_service.py", "upload_service.py"):
        service_source = (root / "app" / "services" / service_name).read_text(encoding="utf-8")
        assert "def _parse_series_row(" not in service_source
        assert "parse_series_row" in service_source


def test_project_existence_checks_live_in_project_service():
    root = Path(__file__).resolve().parents[1]
    project_service = (root / "app" / "services" / "project_service.py").read_text(encoding="utf-8")

    assert "def require_project(" in project_service
    for service_name in ("upload_service.py", "result_service.py"):
        service_source = (root / "app" / "services" / service_name).read_text(encoding="utf-8")
        assert "require_project" in service_source
        assert "Project not found" not in service_source
        assert "SELECT * FROM projects WHERE id=?" not in service_source
