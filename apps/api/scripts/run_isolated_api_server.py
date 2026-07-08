from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Image Agent API with an isolated IMAGE_AGENT_ROOT.")
    parser.add_argument("--root", required=True, help="Isolated Image Agent root directory.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port.")
    parser.add_argument("--env-file", default="", help="Optional env file. Defaults to <root>/.env.")
    parser.add_argument("--require-auth", action="store_true", help="Require console bearer auth.")
    parser.add_argument("--print-config", action="store_true", help="Print effective config JSON and exit.")
    return parser.parse_args()


def _configure_environment(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    env_file = Path(args.env_file).resolve() if args.env_file else root / ".env"
    os.environ["IMAGE_AGENT_ROOT"] = str(root)
    os.environ["IMAGE_AGENT_ENV_FILE"] = str(env_file)
    os.environ["IMAGE_AGENT_REQUIRE_AUTH"] = "1" if args.require_auth else "0"


def main() -> None:
    args = _parse_args()
    _configure_environment(args)

    from app.core import config
    from app.security import auth_required

    if args.print_config:
        print(
            json.dumps(
                {
                    "auth_required": auth_required(),
                    "db_path": str(config.DB_PATH),
                    "env_path": str(config.ENV_PATH),
                    "projects_root": str(config.PROJECTS_ROOT),
                    "root": str(config.ROOT),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
