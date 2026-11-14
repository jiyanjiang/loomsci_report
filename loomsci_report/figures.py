"""Collect figure/table captions into the fact library.

Only OA PDFs with an explicit reuse license are touched. We store the caption
and provenance, not the image bytes; the report links back to the source.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

from . import workspace

ALLOWED = {"cc-by", "cc-by-3.0", "cc-by-4.0", "cc-by-sa", "cc0", "public-domain", "publicdomain"}
CAPTION_RE = re.compile(r"^\s*(Fig(?:ure)?\.?|Table)\s*([0-9]+[A-Za-z]?)", re.I)


def allowed_license(value: str) -> bool:
    return str(value or "").strip().lower().replace("_", "-") in ALLOWED


def _download(url: str, limit: int = 30 * 1024 * 1024) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "loomsci-report/0.1"})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("PDF too large")
    return data


def extract_captions(data: bytes, max_items: int = 4) -> list[dict]:
    if fitz is None:
        return []
    doc = fitz.open(stream=data, filetype="pdf")
    out = []
    seen = set()
    for page_no, page in enumerate(doc, 1):
        for block in page.get_text("blocks"):
            text = " ".join(str(block[4]).split())
            match = CAPTION_RE.match(text)
            if not match:
                continue
            kind = "table" if match.group(1).lower().startswith("table") else "figure"
            label = ("Table " if kind == "table" else "Figure ") + match.group(2)
            if label.lower() in seen:
                continue
            seen.add(label.lower())
            caption = text[:1200]
            out.append({"kind": kind, "label": label, "caption": caption, "page": page_no})
            if len(out) >= max_items:
                return out
    return out


def collect(root: Path, code: str, version: str, sources: list[dict], max_sources: int = 8) -> list[dict]:
    facts = []
    for source in sources:
        if len(facts) >= max_sources * 2:
            break
        if not source.get("oa") or not source.get("pdf_url") or not allowed_license(source.get("license")):
            continue
        try:
            data = _download(source["pdf_url"])
            captions = extract_captions(data)
        except Exception:
            continue
        for item in captions:
            fact = workspace.add_fact(
                root, code, version,
                claim=f"{item['label']}: {item['caption']}",
                url=source["url"],
                quote=item["caption"],
                kind=item["kind"],
                metadata={"label": item["label"], "page": item["page"],
                          "license": source.get("license"), "pdf_url": source["pdf_url"]},
            )
            facts.append(fact)
        if len({f["source"] for f in facts}) >= max_sources:
            break
    return facts


def markdown_section(facts: list[dict]) -> str:
    if not facts:
        return ""
    lines = ["## 图表事实", "", "| 来源 | 类型 | 图/表 | 说明 | 许可 |", "|---|---|---|---|---|"]
    for f in facts[:30]:
        meta = f.get("metadata") or {}
        lines.append(f"| [{f['source']}] | {f.get('kind','')} | {meta.get('label','')} | "
                     f"{f['claim'][:180].replace('|','/')} | {meta.get('license','')} |")
    return "\n".join(lines) + "\n"
