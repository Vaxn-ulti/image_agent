from pathlib import Path


def test_main_entrypoint_is_thin_and_routes_are_split():
    root = Path(__file__).resolve().parents[1]
    main_source = (root / "app" / "main.py").read_text(encoding="utf-8")

    assert len(main_source.splitlines()) <= 450
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
    for function_name in (
        "def health",
        "def list_workflows",
        "def get_result_contract",
        "def deployment",
        "def agent_model_status",
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
