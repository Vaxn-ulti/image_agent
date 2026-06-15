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
