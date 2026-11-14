"""DeepSeek adapter for the Report app.

Key resolution order: environment, LOOMSCI_HOME/config.yaml, legacy TAA
config.toml, then an explicit local key file. Keys are never logged.
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
except Exception:  # pragma: no cover - optional
    yaml = None

CHAT_URL = os.environ.get("DEEPSEEK_CHAT_URL", "https://api.deepseek.com/chat/completions")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")


class LlmError(RuntimeError):
    pass


def deepseek_key(home: Path | None = None) -> str:
    for name in ("DEEPSEEK_API_KEY", "DS_KEY"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    base = home or Path(os.environ.get("LOOMSCI_HOME", str(Path.home() / ".loomsci")))
    config = base / "config.yaml"
    if yaml and config.is_file():
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            llm = data.get("llm") or {}
            value = (llm.get("providers") or {}).get("deepseek", {}).get("api_key") or llm.get("deepseek_api_key")
            if value:
                return str(value).strip()
        except Exception:
            pass
    legacy = Path.home() / ".taa" / "config.toml"
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


def _post(payload: dict[str, Any], key: str, timeout: int = 180) -> dict:
    if not key:
        raise LlmError("DeepSeek key missing")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(CHAT_URL, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {key}")
    last_error = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise LlmError(f"DeepSeek HTTP {exc.code}: {detail}") from None
        except (OSError, ValueError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(1.0)
    raise LlmError(f"DeepSeek request failed: {type(last_error).__name__}") from None


def chat(system: str, user: str, key: str, *, model: str = MODEL,
         temperature: float = 0.3, max_tokens: int = 4000, timeout: int = 180) -> str:
    data = _post({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }, key, timeout=timeout)
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError):
        raise LlmError("DeepSeek returned no content") from None


def json_chat(system: str, user: str, key: str, *, model: str = MODEL,
              temperature: float = 0.1, max_tokens: int = 4000, timeout: int = 180) -> Any:
    text = chat(system, user, key, model=model, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout)
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
        raise LlmError("DeepSeek returned non-JSON content") from None
