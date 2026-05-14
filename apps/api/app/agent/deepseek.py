import json
import os
import urllib.error
import urllib.request
from contextlib import contextmanager

from app.core.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_TIMEOUT_SECONDS


SYSTEM_PROMPT = """You are the built-in agent for Brain Image Agent, a neuroimaging workflow GUI.
You can explain uploaded imaging inventory, task status, and supported remote container workflows.
Current supported processing scope: DeepPrep for T1 anatomical processing, QSIPrep for DWI preprocessing, and QSIRecon for DWI reconstruction.
BOLD/fMRI and other recognized sequences may be inventoried, but processing may be limited by the current MVP unless exposed by the backend.
Be concise, clinically cautious, and never claim diagnostic certainty."""


class DeepSeekUnavailable(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(DEEPSEEK_API_KEY)


def provider_status() -> dict:
    return {
        "provider": "deepseek",
        "configured": is_configured(),
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
        "proxy_mode": "direct",
    }


@contextmanager
def _without_proxy_env():
    proxy_keys = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ]
    saved = {key: os.environ.get(key) for key in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def complete_chat(message: str, context: dict | None = None) -> str:
    if not DEEPSEEK_API_KEY:
        raise DeepSeekUnavailable("DEEPSEEK_API_KEY is not configured")
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": "Current project context JSON:\n" + json.dumps(context or {}, ensure_ascii=False)[:12000]},
            {"role": "user", "content": message},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    url = DEEPSEEK_BASE_URL.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with _without_proxy_env():
            with opener.open(req, timeout=DEEPSEEK_TIMEOUT_SECONDS) as res:
                body = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
        raise DeepSeekUnavailable(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise DeepSeekUnavailable(f"DeepSeek request failed: {exc}") from exc
    try:
        return body["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise DeepSeekUnavailable("DeepSeek response did not include choices[0].message.content") from exc
