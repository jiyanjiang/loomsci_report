"""Research workspace: prompt hash, versions, sources and facts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from . import gate

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
    item["domain"] = str(item.get("domain") or gate.host(url))
    item["grade"] = str(item.get("grade") or gate.grade_for(url))
    item["retrieved_at"] = now()
    with (path / "sources.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def add_fact(root: Path, code: str, version: str, *, claim: str, url: str, quote: str = "",
             kind: str = "claim", metadata: dict | None = None) -> dict:
    path = root / "workspaces" / code / version
    sources = [json.loads(line) for line in (path / "sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    source = next((item for item in sources if item.get("url") == url), None)
    if source is None:
        raise ValueError("fact source must exist")
    facts = [json.loads(line) for line in (path / "facts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    fact = {"id": f"F{len(facts) + 1:03d}", "claim": claim[:500], "url": url,
            "quote": quote[:2000], "source": source["id"], "grade": source["grade"],
            "kind": kind, "metadata": metadata or {}}
    with (path / "facts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fact, ensure_ascii=False) + "\n")
    return fact


def write_draft(root: Path, code: str, version: str, text: str) -> None:
    (root / "workspaces" / code / version / "DRAFT.md").write_text(text, encoding="utf-8")


def check(root: Path, code: str, version: str, query_terms: list[str] | None = None) -> dict:
    path = root / "workspaces" / code / version
    draft = (path / "DRAFT.md").read_text(encoding="utf-8")
    sources = [json.loads(line) for line in (path / "sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    result = gate.evaluate(draft, sources, query_terms=query_terms)
    (path / "check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def summary(root: Path, code: str, version: str) -> dict:
    path = root / "workspaces" / code / version
    sources = [json.loads(line) for line in (path / "sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    facts = [json.loads(line) for line in (path / "facts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    domains = sorted({str(s.get("domain") or "") for s in sources if s.get("domain")})
    check_data = _json(path / "check.json", {})
    return {"sources": len(sources), "facts": len(facts), "domains": domains, "check": check_data}
