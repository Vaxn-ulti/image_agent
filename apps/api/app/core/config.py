import os
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[4]


def _env_path_before_root() -> Path:
    configured = os.environ.get("IMAGE_AGENT_ENV_FILE", "").strip()
    if configured:
        return Path(configured)
    configured_root = Path(os.environ.get("IMAGE_AGENT_ROOT", _DEFAULT_ROOT))
    return configured_root / ".env"


def load_env_file(path: Path | None = None) -> None:
    path = path or Path(os.environ.get("IMAGE_AGENT_ENV_FILE", "") or Path(os.environ.get("IMAGE_AGENT_ROOT", _DEFAULT_ROOT)) / ".env")
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


ENV_PATH = _env_path_before_root()
load_env_file(ENV_PATH)

ROOT = Path(os.environ.get("IMAGE_AGENT_ROOT", _DEFAULT_ROOT))
DATA_ROOT = ROOT / "data"
DB_PATH = DATA_ROOT / "app.db"
PROJECTS_ROOT = DATA_ROOT / "projects"
ENV_PATH = Path(os.environ.get("IMAGE_AGENT_ENV_FILE", ROOT / ".env"))

SUDO_PASSWORD = os.environ.get("IMAGE_AGENT_SUDO_PASSWORD", "")
FS_LICENSE = Path(os.environ.get("IMAGE_AGENT_FS_LICENSE", "<IMAGE_AGENT_FS_LICENSE>"))
DOCKER_IMAGES = {
    "deepprep": "pbfslab/deepprep:25.1.0",
    "qsiprep": "pennlinc/qsiprep:26.0.0",
    "qsirecon": "pennlinc/qsirecon:26.0.0",
}
QSIRECON_PROFILE = os.environ.get("IMAGE_AGENT_QSIRECON_PROFILE", "dki").strip().lower() or "dki"
QSIRECON_PROFILE_RECON_SPECS = {
    "dki": "dipy_dki",
    "tractography": "mrtrix_multishell_msmt_noACT",
}
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_TIMEOUT_SECONDS = int(os.environ.get("DEEPSEEK_TIMEOUT_SECONDS", "12"))

DATA_ROOT.mkdir(parents=True, exist_ok=True)
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)

