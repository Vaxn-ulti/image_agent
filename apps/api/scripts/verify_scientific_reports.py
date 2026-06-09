from __future__ import annotations

import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.scripts.verify_scientific_reports import (  # noqa: E402
    CheckResult,
    check_output,
    main,
    resolve_task_output_dirs,
)

__all__ = ["CheckResult", "check_output", "main", "resolve_task_output_dirs"]


if __name__ == "__main__":
    raise SystemExit(main())
