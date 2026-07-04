from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_TESTS = [
    "src/lib/api.test.ts",
    "src/lib/workflows.test.ts",
    "src/routes/AgentPage.test.tsx",
    "src/routes/WorkflowsPage.test.tsx",
    "src/routes/ResultDetailPage.test.tsx",
]
DEFAULT_NPM_REGISTRY = "https://registry.npmjs.org/"
PROXY_ENV_KEYS = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "npm_config_proxy",
    "npm_config_https_proxy",
}


def _npm_executable() -> str:
    if sys.platform.startswith("win"):
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def _require_safe_registry(registry: str | None) -> str | None:
    if not registry:
        return None
    parsed = urlparse(registry)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("npm registry must be an HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("npm registry URL must not contain credentials, query, or fragment")
    return registry


def _redact_command(command: list[str]) -> str:
    redacted = []
    for part in command:
        parsed = urlparse(part)
        if parsed.scheme in {"http", "https"} and (
            parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            redacted.append("<redacted-url>")
        else:
            redacted.append(part)
    return " ".join(redacted)


def _command_env(*, trust_env_proxy: bool) -> dict[str, str]:
    env = dict(os.environ)
    if not trust_env_proxy:
        for key in PROXY_ENV_KEYS:
            env.pop(key, None)
    return env


def _run_command(command: list[str], *, cwd: Path, timeout_seconds: int, trust_env_proxy: bool = False) -> None:
    try:
        subprocess.run(
            command,
            cwd=cwd,
            check=True,
            timeout=timeout_seconds,
            env=_command_env(trust_env_proxy=trust_env_proxy),
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"command timed out after {timeout_seconds}s: {_redact_command(command)}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"command failed with exit code {exc.returncode}: {_redact_command(command)}"
        ) from exc


def run_frontend_contract_tests(
    *,
    console_dir: Path,
    tests: list[str],
    install: bool,
    timeout_seconds: int,
    registry: str | None,
    fetch_timeout_ms: int,
    fetch_retries: int,
    trust_env_proxy: bool,
    cache_dir: Path | None,
    offline: bool,
) -> None:
    console_root = console_dir.resolve()
    if not (console_root / "package.json").is_file():
        raise SystemExit(f"console_dir missing package.json: {console_root}")
    if install and not (console_root / "package-lock.json").is_file():
        raise SystemExit(f"console_dir missing package-lock.json: {console_root}")

    npm = _npm_executable()
    safe_registry = _require_safe_registry(registry)
    if install:
        install_command = [npm, "ci", "--include=dev", "--ignore-scripts", "--no-audit", "--no-fund"]
        if safe_registry:
            install_command.extend(["--registry", safe_registry])
        install_command.extend([f"--fetch-timeout={fetch_timeout_ms}", f"--fetch-retries={fetch_retries}"])
        if cache_dir is not None:
            install_command.extend(["--cache", str(cache_dir.resolve())])
        if offline:
            install_command.append("--offline")
        _run_command(
            install_command,
            cwd=console_root,
            timeout_seconds=timeout_seconds,
            trust_env_proxy=trust_env_proxy,
        )
    _run_command(
        [npm, "test", "--", "--run", *tests],
        cwd=console_root,
        timeout_seconds=timeout_seconds,
        trust_env_proxy=trust_env_proxy,
    )
    print("frontend_api_contract_tests=passed")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run console API/workflow contract tests portably.")
    parser.add_argument("--console-dir", default="apps/console", help="Path to the console package.")
    parser.add_argument("--install", action="store_true", help="Run npm ci from the Git-managed lockfile first.")
    parser.add_argument("--timeout-seconds", type=int, default=600, help="Timeout for each npm command.")
    parser.add_argument(
        "--registry",
        default=os.environ.get("IMAGE_AGENT_NPM_REGISTRY", DEFAULT_NPM_REGISTRY),
        help="HTTPS npm registry URL without credentials, query, or fragment.",
    )
    parser.add_argument("--fetch-timeout-ms", type=int, default=20_000, help="npm fetch timeout in milliseconds.")
    parser.add_argument("--fetch-retries", type=int, default=0, help="npm fetch retry count.")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Optional npm cache directory.")
    parser.add_argument("--offline", action="store_true", help="Run npm install in offline cache-only mode.")
    parser.add_argument(
        "--trust-env-proxy",
        action="store_true",
        help="Allow npm to inherit proxy environment variables for this run.",
    )
    parser.add_argument("tests", nargs="*", default=DEFAULT_TESTS, help="Vitest files to run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    run_frontend_contract_tests(
        console_dir=Path(args.console_dir),
        tests=list(args.tests or DEFAULT_TESTS),
        install=bool(args.install),
        timeout_seconds=args.timeout_seconds,
        registry=args.registry,
        fetch_timeout_ms=args.fetch_timeout_ms,
        fetch_retries=args.fetch_retries,
        trust_env_proxy=bool(args.trust_env_proxy),
        cache_dir=args.cache_dir,
        offline=bool(args.offline),
    )


if __name__ == "__main__":
    main()
