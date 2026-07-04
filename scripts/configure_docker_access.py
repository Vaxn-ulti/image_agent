from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from pathlib import PurePosixPath


PLAN_ID = "image_agent_docker_access_policy_v1"
DEFAULT_SUDOERS_DIR = Path("/etc/sudoers.d")
DEFAULT_RULE_NAME = "image-agent-docker"
DEFAULT_DOCKER_BIN = Path("/usr/bin/docker")
VERIFY_COMMAND = ["sudo", "-n", "docker", "version", "--format", "{{.Server.Version}}"]

_SAFE_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*[$]?$")
_SAFE_RULE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _command_preview(command: list[str]) -> str:
    return " ".join(command)


def _validate_user(user: str) -> str:
    value = (user or "").strip()
    if not value or not _SAFE_USER_RE.fullmatch(value):
        raise SystemExit("unsafe sudo user")
    return value


def _validate_rule_name(rule_name: str) -> str:
    value = (rule_name or "").strip()
    if not value or not _SAFE_RULE_NAME_RE.fullmatch(value) or "/" in value or "\\" in value:
        raise SystemExit("unsafe sudoers rule name")
    return value


def _validate_docker_bin(docker_bin: Path) -> str:
    text = Path(docker_bin).as_posix()
    if not text.startswith("/"):
        raise SystemExit("docker binary must be an absolute path")
    if any(char in text for char in [";", "&", "|", "`", "$", "\n", "\r", "\t"]):
        raise SystemExit("unsafe docker binary path")
    parts = PurePosixPath(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise SystemExit("unsafe docker binary path")
    return text


def _sudoers_rule(user: str, docker_bin: str) -> str:
    return f"{user} ALL=(root) NOPASSWD: {docker_bin}\n"


def build_policy_plan(
    *,
    user: str,
    docker_bin: Path,
    sudoers_dir: Path,
    rule_name: str,
    apply_changes: bool,
) -> dict:
    safe_user = _validate_user(user)
    safe_rule_name = _validate_rule_name(rule_name)
    safe_docker_bin = _validate_docker_bin(docker_bin)
    sudoers_file = Path(sudoers_dir) / safe_rule_name
    validate_command = ["visudo", "-cf", str(sudoers_file)]
    steps = [
        {
            "id": "write_sudoers_rule",
            "command": ["write_file", str(sudoers_file), "sudoers_rule_redacted"],
            "command_preview": f"write_file {sudoers_file} sudoers_rule_redacted",
            "mutates_state": True,
        },
        {
            "id": "validate_sudoers_rule",
            "command": validate_command,
            "command_preview": _command_preview(validate_command),
            "mutates_state": False,
        },
        {
            "id": "verify_operator_docker_command",
            "command": VERIFY_COMMAND,
            "command_preview": _command_preview(VERIFY_COMMAND),
            "mutates_state": False,
        },
    ]
    return {
        "plan_id": PLAN_ID,
        "schema_version": 1,
        "mode": "apply" if apply_changes else "dry_run",
        "user": safe_user,
        "docker_bin": str(safe_docker_bin),
        "sudoers_file": str(sudoers_file),
        "sudoers_rule": _sudoers_rule(safe_user, safe_docker_bin),
        "verification_command": VERIFY_COMMAND,
        "steps": steps,
        "security_boundary": [
            "narrow NOPASSWD sudo is limited to the Docker binary path",
            "no password, proxy URL, API key, or Docker socket override is written",
            "rawchat model traffic remains direct and is not affected by this Docker policy",
        ],
    }


def _run(command: list[str]) -> None:
    proc = subprocess.run(command, text=True, capture_output=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"command failed: {_command_preview(command)}{': ' + detail if detail else ''}")


def _requires_root(sudoers_dir: Path) -> bool:
    try:
        return sudoers_dir.resolve() == DEFAULT_SUDOERS_DIR
    except OSError:
        return str(sudoers_dir) == str(DEFAULT_SUDOERS_DIR)


def _ensure_root_for_system_sudoers(sudoers_dir: Path) -> None:
    if not _requires_root(sudoers_dir):
        return
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() != 0:
        raise SystemExit("applying to /etc/sudoers.d requires root")


def configure_docker_access(
    *,
    user: str,
    docker_bin: Path,
    sudoers_dir: Path,
    rule_name: str,
    apply_changes: bool,
) -> dict:
    plan = build_policy_plan(
        user=user,
        docker_bin=docker_bin,
        sudoers_dir=sudoers_dir,
        rule_name=rule_name,
        apply_changes=apply_changes,
    )
    if not apply_changes:
        return plan

    sudoers_file = Path(plan["sudoers_file"])
    _ensure_root_for_system_sudoers(sudoers_file.parent)
    sudoers_file.parent.mkdir(parents=True, exist_ok=True)
    sudoers_file.write_text(plan["sudoers_rule"], encoding="utf-8")
    sudoers_file.chmod(stat.S_IRUSR | stat.S_IRGRP)
    _run(["visudo", "-cf", str(sudoers_file)])
    _run(list(plan["verification_command"]))
    return plan


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure Image Agent Docker sudo access policy")
    parser.add_argument("--user", required=True, help="Unix user that runs Image Agent or the operator command")
    parser.add_argument("--docker-bin", default=str(DEFAULT_DOCKER_BIN), help="Absolute Docker binary path")
    parser.add_argument("--sudoers-dir", default=str(DEFAULT_SUDOERS_DIR), help="sudoers.d directory")
    parser.add_argument("--rule-name", default=DEFAULT_RULE_NAME, help="sudoers.d file name")
    parser.add_argument("--apply", action="store_true", help="Write and validate the sudoers rule")
    parser.add_argument("--output-json", default="", help="Optional path for the JSON plan/report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    plan = configure_docker_access(
        user=args.user,
        docker_bin=Path(args.docker_bin),
        sudoers_dir=Path(args.sudoers_dir),
        rule_name=args.rule_name,
        apply_changes=args.apply,
    )
    text = json.dumps(plan, indent=2, sort_keys=True)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
