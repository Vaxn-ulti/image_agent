from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_remote_restart_script_has_drain_port_and_health_safety_gates():
    script = (REPO_ROOT / "tools" / "restart_remote_image_agent_api.sh").read_text(encoding="utf-8")

    for phrase in (
        "check_no_active_tasks",
        "IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS",
        "status IN ('queued','running')",
        "check_port_owner",
        "IMAGE_AGENT_ALLOW_FOREIGN_PORT_OWNER",
        "foreign port owner",
        "wait_for_exit",
        "IMAGE_AGENT_STOP_TIMEOUT_SECONDS",
        "wait_for_health",
        "IMAGE_AGENT_START_TIMEOUT_SECONDS",
        "/health",
        "app=image_agent",
        "reconcile_stale_tasks.py",
        "--check-containers",
    ):
        assert phrase in script


def test_remote_restart_script_supports_release_overlay_without_dirty_worktree():
    script = (REPO_ROOT / "tools" / "restart_remote_image_agent_api.sh").read_text(encoding="utf-8")

    for phrase in (
        "IMAGE_AGENT_RELEASE_ROOT",
        "IMAGE_AGENT_ENV_FILE",
        "IMAGE_AGENT_SHARED_VENV_BIN",
        "IMAGE_AGENT_API_DIR:-$RELEASE_ROOT/apps/api",
        "IMAGE_AGENT_ENV_FILE:-$ROOT/.env",
        "IMAGE_AGENT_SHARED_VENV_BIN:-$ROOT/apps/api/.venv/bin",
    ):
        assert phrase in script


def test_remote_restart_safety_is_documented_for_agent_use():
    production_doc = (REPO_ROOT / "docs" / "deployment" / "remote-agent-production.md").read_text(encoding="utf-8")

    for phrase in (
        "restart/drain safety gate",
        "`IMAGE_AGENT_ALLOW_RESTART_WITH_ACTIVE_TASKS=1`",
        "`IMAGE_AGENT_ALLOW_FOREIGN_PORT_OWNER=1`",
        "`IMAGE_AGENT_STOP_TIMEOUT_SECONDS`",
        "`IMAGE_AGENT_START_TIMEOUT_SECONDS`",
        "refuses to restart while tasks are `queued` or `running`",
        "refuses to stop a foreign process on port 8000",
        "post-restart `/health` must return `app=image_agent`",
    ):
        assert phrase in production_doc


def test_release_overlay_restart_is_documented_for_agent_use():
    production_doc = (REPO_ROOT / "docs" / "deployment" / "remote-agent-production.md").read_text(encoding="utf-8")

    for phrase in (
        "release overlay",
        "`IMAGE_AGENT_RELEASE_ROOT`",
        "`IMAGE_AGENT_API_DIR`",
        "`IMAGE_AGENT_ENV_FILE`",
        "`IMAGE_AGENT_SHARED_VENV_BIN`",
        "keeps the dirty remote main worktree out of the serving path",
    ):
        assert phrase in production_doc
