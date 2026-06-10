from __future__ import annotations

import argparse
import json

from app.workflows.stale_tasks import reconcile_stale_active_tasks, running_container_task_ids_from_docker


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit or reconcile stale queued/running workflow tasks.")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--apply", action="store_true", help="Mark stale active tasks failed after a successful container-label check.")
    parser.add_argument(
        "--reason",
        default="operator confirmed no matching running Image Agent container",
        help="Audit reason stored in task error_message when --apply is used.",
    )
    args = parser.parse_args()

    running_task_ids = running_container_task_ids_from_docker() if args.apply else None
    report = reconcile_stale_active_tasks(
        max_age_hours=args.max_age_hours,
        apply=args.apply,
        running_container_task_ids=running_task_ids,
        reason=args.reason,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
