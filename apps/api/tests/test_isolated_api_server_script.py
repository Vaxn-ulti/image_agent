import json
import subprocess
import sys


def test_isolated_api_server_prints_config_after_setting_root(tmp_path):
    script = "scripts/run_isolated_api_server.py"
    root = tmp_path / "isolated-root"

    result = subprocess.run(
        [
            sys.executable,
            script,
            "--root",
            str(root),
            "--port",
            "0",
            "--cors-origin",
            "http://127.0.0.1:5184",
            "--print-config",
        ],
        cwd="apps/api",
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["root"] == str(root)
    assert payload["db_path"] == str(root / "data" / "app.db")
    assert payload["env_path"] == str(root / ".env")
    assert payload["projects_root"] == str(root / "data" / "projects")
    assert payload["cors_origins"] == ["http://127.0.0.1:5184"]
    assert payload["auth_required"] is False
