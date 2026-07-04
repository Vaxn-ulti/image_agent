import os
import subprocess
import sys
from pathlib import Path


def test_image_agent_root_overrides_persistent_data_paths(tmp_path):
    app_root = tmp_path / "deployed-root"
    app_root.mkdir()
    env = {**os.environ, "IMAGE_AGENT_ROOT": str(app_root), "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core import config; "
                "print(config.ROOT); "
                "print(config.DATA_ROOT); "
                "print(config.DB_PATH); "
                "print(config.PROJECTS_ROOT)"
            ),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    root, data_root, db_path, projects_root = result.stdout.strip().splitlines()
    assert Path(root) == app_root
    assert Path(data_root) == app_root / "data"
    assert Path(db_path) == app_root / "data" / "app.db"
    assert Path(projects_root) == app_root / "data" / "projects"


def test_image_agent_root_overrides_agent_repo_root_and_main_compat(tmp_path):
    app_root = tmp_path / "deployed-root"
    app_root.mkdir()
    env = {**os.environ, "IMAGE_AGENT_ROOT": str(app_root), "PYTHONPATH": str(Path(__file__).resolve().parents[1])}

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.services import agent_service; "
                "print(agent_service._repo_root()); "
                "import app.main as main; "
                "print(main.REPO_ROOT); "
                "print(agent_service._repo_root())"
            ),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    service_root, main_root, patched_service_root = result.stdout.strip().splitlines()
    assert Path(service_root) == app_root
    assert Path(main_root) == app_root
    assert Path(patched_service_root) == app_root


def test_release_root_overrides_repo_root_without_moving_persistent_data(tmp_path):
    live_root = tmp_path / "live-root"
    release_root = tmp_path / "release-overlay"
    live_root.mkdir()
    release_root.mkdir()
    env = {
        **os.environ,
        "IMAGE_AGENT_ROOT": str(live_root),
        "IMAGE_AGENT_RELEASE_ROOT": str(release_root),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core import config; "
                "from app.services import agent_service; "
                "import app.main as main; "
                "print(config.ROOT); "
                "print(config.PROJECTS_ROOT); "
                "print(agent_service._repo_root()); "
                "print(main.REPO_ROOT)"
            ),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    config_root, projects_root, service_root, main_root = result.stdout.strip().splitlines()
    assert Path(config_root) == live_root
    assert Path(projects_root) == live_root / "data" / "projects"
    assert Path(service_root) == release_root
    assert Path(main_root) == release_root


def test_image_agent_env_file_can_define_live_root_before_paths_are_computed(tmp_path):
    live_root = tmp_path / "live-root"
    release_root = tmp_path / "release-overlay"
    env_file = tmp_path / "deploy.env"
    live_root.mkdir()
    release_root.mkdir()
    env_file.write_text(
        f"IMAGE_AGENT_ROOT={live_root}\n"
        "IMAGE_AGENT_MODEL_PROVIDER=rawchat\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "IMAGE_AGENT_ENV_FILE": str(env_file),
        "IMAGE_AGENT_RELEASE_ROOT": str(release_root),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    env.pop("IMAGE_AGENT_ROOT", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core import config; "
                "from app.services import agent_service; "
                "print(config.ENV_PATH); "
                "print(config.ROOT); "
                "print(config.DB_PATH); "
                "print(config.PROJECTS_ROOT); "
                "print(agent_service._repo_root())"
            ),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    env_path, root, db_path, projects_root, service_root = result.stdout.strip().splitlines()
    assert Path(env_path) == env_file
    assert Path(root) == live_root
    assert Path(db_path) == live_root / "data" / "app.db"
    assert Path(projects_root) == live_root / "data" / "projects"
    assert Path(service_root) == release_root
