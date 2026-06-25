from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from app.agent.runtime import runtime_probe

AUTO_PULL_MISSING_WORKFLOW_IMAGES_ENV = "IMAGE_AGENT_AUTO_PULL_MISSING_WORKFLOW_IMAGES"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Probe the local Image Agent deployment runtime.")
    parser.add_argument("--json", action="store_true", help="Emit the portable runtime probe as JSON.")
    parser.add_argument(
        "--prepare-missing-images",
        action="store_true",
        help="Pull missing fixed-workflow Docker images before reporting the runtime probe.",
    )
    args = parser.parse_args(argv)
    if args.prepare_missing_images:
        os.environ[AUTO_PULL_MISSING_WORKFLOW_IMAGES_ENV] = "1"
    payload = runtime_probe()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"status={payload['status']}")
    for code in payload.get("blocking_codes", []):
        print(f"blocking_code={code}")


if __name__ == "__main__":
    main()
