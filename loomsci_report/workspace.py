"""Research workspace: prompt hash, versions, sources and facts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CODE_RE = re.compile(r"^r-[0-9a-f]{12}$")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def code_for(question: str) -> str:
    return "r-" + hashlib.sha256(normalize(question).encode("utf-8")).hexdigest()[:12]


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def new(question: str, root: Path, title: str = "") -> dict:
    question = normalize(question)
    if not question:
        raise ValueError("question required")
    code = code_for(question)
    base = root / "workspaces" / code
    base.mkdir(parents=True, exist_ok=True)
    versions = sorted([p.name for p in base.iterdir() if p.is_dir() and p.name.startswith("v")],
                      key=lambda name: int(name[1:] or 0))
    version = f"v{len(versions) + 1}"
    path = base / version
    path.mkdir()
    (path / "meta.json").write_text(json.dumps({
        "code": code, "version": version, "question": question,
        "title": title or question[:80], "created_at": now(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (path / "sources.jsonl").touch()
    (path / "facts.jsonl").touch()
    (path / "DRAFT.md").write_text("# " + (title or question) + "\n\n", encoding="utf-8")
    (path / "OUTLINE.md").write_text("# Outline\n\n", encoding="utf-8")
    return {"code": code, "version": version, "path": str(path)}


def add_source(root: Path, code: str, version: str, source: dict) -> dict:
    path = root / "workspaces" / code / version
    sources = [json.loads(line) for line in (path / "sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    url = str(source.get("url") or "").strip()
    if any(item.get("url") == url for item in sources):
        return next(item for item in sources if item.get("url") == url)
    item = dict(source)
    item["id"] = f"S{len(sources) + 1:03d}"
    item["retrieved_at"] = now()
    with (path / "sources.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def summary(root: Path, code: str, version: str) -> dict:
    path = root / "workspaces" / code / version
    sources = [json.loads(line) for line in (path / "sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    facts = [json.loads(line) for line in (path / "facts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    domains = sorted({str(s.get("domain") or "") for s in sources if s.get("domain")})
    return {"sources": len(sources), "facts": len(facts), "domains": domains}
