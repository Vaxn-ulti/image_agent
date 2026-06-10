from __future__ import annotations

import argparse
import json

from app.workflows import stale_tasks

running_container_task_ids_from_docker = stale_tasks.running_container_task_ids_from_docker


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Audit or reconcile stale queued/running workflow tasks.")
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--apply", action="store_true", help="Mark stale active tasks failed after a successful container-label check.")
    parser.add_argument(
        "--check-containers",
        action="store_true",
        help="Run the Docker label check in dry-run mode and include running task ids in the JSON report.",
    )
    parser.add_argument(
        "--reason",
        default="operator confirmed no matching running Image Agent container",
        help="Audit reason stored in task error_message when --apply is used.",
    )
    args = parser.parse_args(argv)

    should_check_containers = args.apply or args.check_containers
    running_task_ids = running_container_task_ids_from_docker() if should_check_containers else None
    report = stale_tasks.reconcile_stale_active_tasks(
        max_age_hours=args.max_age_hours,
        apply=args.apply,
        running_container_task_ids=running_task_ids,
        container_check_status="passed" if should_check_containers else "not_requested",
        reason=args.reason,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
