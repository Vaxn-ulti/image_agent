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
