"""LLM adapter with provider fallback.

Order: DeepSeek v4 Flash -> Alibaba DashScope (qwen-plus).

Keys are resolved from environment, LOOMSCI config, or legacy TAA config.
Keys are never logged.
"""

from __future__ import annotations

import json
import os
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

DEEPSEEK_URL = os.environ.get("DEEPSEEK_CHAT_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
ALI_URL = os.environ.get(
    "DASHSCOPE_CHAT_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
ALI_MODEL = os.environ.get("ALI_MODEL", "qwen-plus")
MODEL = DEEPSEEK_MODEL  # backwards-compatible export


class LlmError(RuntimeError):
    pass


def _config_paths(home: Path | None = None) -> tuple[Path, Path]:
    base = home or Path(os.environ.get("LOOMSCI_HOME", str(Path.home() / ".loomsci")))
    return base / "config.yaml", Path.home() / ".taa" / "config.toml"


def deepseek_key(home: Path | None = None) -> str:
    for name in ("DEEPSEEK_API_KEY", "DS_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    config, legacy = _config_paths(home)
    if yaml and config.is_file():
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            llm = data.get("llm") or {}
            value = (llm.get("providers") or {}).get("deepseek", {}).get("api_key") or llm.get("deepseek_api_key")
            if value:
                return str(value).strip()
        except Exception:
            pass
    if legacy.is_file():
        try:
            data = tomllib.loads(legacy.read_text(encoding="utf-8"))
            value = (data.get("llm") or {}).get("deepseek_api_key")
            if value:
                return str(value).strip()
        except Exception:
            pass
    key_file = os.environ.get("DEEPSEEK_KEY_FILE")
    if key_file and Path(key_file).is_file():
        return Path(key_file).read_text(encoding="utf-8").strip()
    return ""


def ali_key(home: Path | None = None) -> str:
    for name in ("DASHSCOPE_API_KEY", "ALIBABA_API_KEY", "QWEN_API_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    config, legacy = _config_paths(home)
    if yaml and config.is_file():
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            llm = data.get("llm") or {}
            value = (llm.get("providers") or {}).get("ali", {}).get("api_key")
            value = value or llm.get("alibaba_api_key") or llm.get("dashscope_api_key")
            if value:
                return str(value).strip()
        except Exception:
            pass
    if legacy.is_file():
        try:
            data = tomllib.loads(legacy.read_text(encoding="utf-8"))
            llm = data.get("llm") or {}
            value = llm.get("alibaba_api_key") or llm.get("dashscope_api_key")
            if value:
                return str(value).strip()
        except Exception:
            pass
    return ""


def _post(url: str, payload: dict[str, Any], key: str, *, provider: str, timeout: int) -> dict:
    if not key:
        raise LlmError(f"{provider} key missing")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {key}")
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise LlmError(f"{provider} HTTP {exc.code}: {detail}") from None
        except (OSError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1.0)
    raise LlmError(f"{provider} request failed: {type(last_error).__name__}") from None


def _call(system: str, user: str, key: str, *, url: str, provider: str, model: str,
          temperature: float, max_tokens: int, timeout: int) -> str:
    data = _post(url, {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }, key, provider=provider, timeout=timeout)
    try:
        text = str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        raise LlmError(f"{provider} returned empty content")
    return text


def chat(system: str, user: str, key: str = "", *, model: str = DEEPSEEK_MODEL,
         temperature: float = 0.3, max_tokens: int = 4000, timeout: int = 180) -> str:
    """DeepSeek first; on failure/empty switch to Alibaba DashScope."""
    errors = []
    if key and os.environ.get("LLM_PROVIDER", "").lower() not in {"ali", "alibaba", "dashscope"}:
        try:
            return _call(system, user, key, url=DEEPSEEK_URL, provider="deepseek",
                         model=model, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
        except LlmError as exc:
            errors.append(str(exc))
    ak = ali_key()
    if ak:
        try:
            return _call(system, user, ak, url=ALI_URL, provider="ali",
                         model=ALI_MODEL, temperature=temperature,
                         max_tokens=max_tokens, timeout=timeout)
        except LlmError as exc:
            errors.append(str(exc))
    if errors:
        raise LlmError("all providers failed: " + " | ".join(errors))
    raise LlmError("DeepSeek/Ali key missing")


def json_chat(system: str, user: str, key: str = "", *, model: str = DEEPSEEK_MODEL,
              temperature: float = 0.1, max_tokens: int = 4000, timeout: int = 180) -> Any:
    text = chat(system, user, key, model=model, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start, end = text.find(open_char), text.rfind(close_char)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    raise LlmError("LLM returned non-JSON content") from None
