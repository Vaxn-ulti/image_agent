import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA_ROOT = ROOT / "data"
DB_PATH = DATA_ROOT / "app.db"
PROJECTS_ROOT = DATA_ROOT / "projects"
ENV_PATH = ROOT / ".env"


def load_env_file(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

SUDO_PASSWORD = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD", "")
FS_LICENSE = Path(os.environ.get("IMAGE_AGENT_FS_LICENSE", "/home/yyf/codex/license.txt"))
DOCKER_IMAGES = {
    "deepprep": "pbfslab/deepprep:25.1.0",
    "qsiprep": "pennlinc/qsiprep:latest",
    "qsirecon": "pennlinc/qsirecon:latest",
}
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_TIMEOUT_SECONDS = int(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "12"))

DATA_ROOT.mkdir(parents=True, exist_ok=True)
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
