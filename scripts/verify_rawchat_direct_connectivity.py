from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


DEFAULT_URL = "https://rawchat.cn/codex"
PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _require_rawchat_url(url: str) -> str:
    text = (url or "").strip()
    parsed = urlsplit(text)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "rawchat.cn" or host.endswith(".rawchat.cn")):
        raise SystemExit("rawchat direct probe URL must target rawchat.cn over HTTPS")
    return text


def _proxy_env_present() -> bool:
    return any(os.environ.get(name) for name in PROXY_ENV_NAMES)


def _safe_failure(error: BaseException) -> dict[str, str]:
    return {
        "error_type": type(error).__name__,
        "error_summary": str(error.__class__.__name__),
    }


def _default_opener():
    return build_opener(ProxyHandler({}))


def probe_rawchat_direct_connectivity(
    *,
    url: str = DEFAULT_URL,
    timeout_seconds: float = 20.0,
    opener_factory: Callable[[], Any] = _default_opener,
) -> dict:
    target = _require_rawchat_url(url)
    parsed = urlsplit(target)
    checked: dict[str, object] = {
        "host": parsed.hostname,
        "scheme": parsed.scheme,
        "direct_transport": True,
        "proxy_env_present": _proxy_env_present(),
        "proxy_env_trusted": False,
        "proxy_handler": "disabled",
    }
    request = Request(target, headers={"User-Agent": "image-agent-rawchat-direct-probe/1"})
    opener = opener_factory()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            checked["http_status"] = int(getattr(response, "status", 0) or 0)
    except HTTPError as exc:
        checked["http_status"] = int(exc.code)
    except URLError as exc:
        checked.update(_safe_failure(exc))
        return {
            "status": "failed",
            "checked": checked,
            "summary": "rawchat_direct_connectivity_status=failed",
        }
    except OSError as exc:
        checked.update(_safe_failure(exc))
        return {
            "status": "failed",
            "checked": checked,
            "summary": "rawchat_direct_connectivity_status=failed",
        }
    status_code = checked.get("http_status")
    passed = isinstance(status_code, int) and 100 <= status_code < 500
    return {
        "status": "passed" if passed else "failed",
        "checked": checked,
        "summary": f"rawchat_direct_connectivity_status={'passed' if passed else 'failed'}",
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify rawchat endpoint connectivity without trusting proxy environment variables.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args(argv)

    report = probe_rawchat_direct_connectivity(url=args.url, timeout_seconds=args.timeout_seconds)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(report["summary"])
    print(f"rawchat_direct_proxy_env_trusted={str(report['checked'].get('proxy_env_trusted')).lower()}")
    print("rawchat_direct_transport=direct" if report["checked"].get("direct_transport") else "rawchat_direct_transport=not_direct")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
