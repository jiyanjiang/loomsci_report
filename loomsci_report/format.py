"""Human-facing report formatting: stable citations, readable gate, Unicode math."""

from __future__ import annotations

import re

SUB = str.maketrans("0123456789+-=()xyz", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₓᵧᵤ")
SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")


def normalize_math(text: str) -> str:
    """Render common simple LaTeX sub/superscripts without a JS math runtime."""
    text = re.sub(r"\$_\{?([0-9A-Za-z+\-=()]+)\}?\$", lambda m: m.group(1).translate(SUB), text)
    text = re.sub(r"\$\^\{?([0-9+\-=()n]+)\}?\$", lambda m: m.group(1).translate(SUP), text)
    text = text.replace("$", "")
    return text


def _gate_table(check: dict) -> str:
    ok = check.get("ok")
    status = "通过" if ok else "未通过"
    reasons = "；".join(check.get("reasons") or []) or "无"
    return f"""## 证据与核验

| 项目 | 结果 |
|---|---|
| 来源数 | {check.get('source_count', 0)} |
| 独立域名 | {check.get('domain_count', 0)} |
| 学术/一手来源 | {check.get('strong_count', 0)} |
| 正文引用来源 | {check.get('cited_count', 0)} |
| 结构门禁 | **{status}** |

**核验边界**：结构门禁通过，表示来源数量、域名、强来源和引用满足最低证据契约，不等于每条 claim 已经过全文核查。本文 claim 主要来自论文摘要；未做逐条全文复核。

**门禁结论**：{"通过，无阻断项。" if ok else "未通过：" + reasons}
"""


def _rebuild_table(body: str, facts: list[dict] | None) -> str:
    if not facts:
        return body
    cited = {x.upper() for x in re.findall(r"\[(S\d{3})\]", body)}
    by_source = {}
    for fact in facts:
        sid = str(fact.get("source") or "").upper()
        if sid and sid not in by_source and fact.get("kind", "claim") == "claim":
            by_source[sid] = fact
    rows = []
    for sid in sorted(cited):
        fact = by_source.get(sid)
        if not fact:
            continue
        claim = str(fact.get("claim") or "").replace("|", "/")[:220]
        qualifier = str(fact.get("qualifier") or fact.get("metadata", {}).get("qualifier") or "").replace("|", "/")[:120]
        rows.append(f"| [{sid}] | {claim} | {qualifier} |")
    if not rows:
        return body
    start = body.find("## 证据表")
    if start < 0:
        return body
    end = body.find("\n## ", start + 1)
    table = "## 证据表\n\n| 来源 | 判断 | 限定 |\n|---|---|---|\n" + "\n".join(rows) + "\n"
    return body[:start] + table + (body[end:] if end >= 0 else "")


def _rebuild_references(body: str, sources: list[dict]) -> str:
    cited = {x.upper() for x in re.findall(r"\[(S\d{3})\]", body)}
    by_id = {str(s.get("id") or "").upper(): s for s in sources if s.get("id")}
    refs = []
    for sid in sorted(cited):
        src = by_id.get(sid)
        if not src:
            continue
        title = normalize_math(str(src.get("title") or "")).replace("|", "/")
        refs.append(f"- [{sid}] {title} — {src.get('url') or ''}")
    if not refs:
        return body
    if "## 参考来源" in body:
        head, tail = body.split("## 参考来源", 1)
        nxt = tail.find("\n## ")
        body = head + "## 参考来源\n\n" + "\n".join(refs) + ("\n" + tail[nxt:] if nxt >= 0 else "\n")
    else:
        body = body.rstrip() + "\n\n## 参考来源\n\n" + "\n".join(refs) + "\n"
    return body


def finalize(md: str, sources: list[dict], check: dict, facts: list[dict] | None = None) -> str:
    """Remove machine JSON, rebuild citation table/references, add evidence note."""
    body = md.split("## 证据门禁", 1)[0].rstrip()
    body = body.split("## 证据与核验", 1)[0].rstrip()
    body = normalize_math(body).replace("`[Sxxx]`", "`S001`")
    body = _rebuild_table(body, facts)
    body = _rebuild_references(body, sources)
    # add citation semantics once
    if "## 引用说明" not in body:
        body = body.replace("## 证据表", """## 引用说明

正文中的稳定证据编号（如 `S001`）指向下方证据表与参考来源。导出时不重编号，便于逐条复核；编号本身不代表引用次数或重要性。

## 证据表""", 1)
    # rebuild reference URLs from the source registry, only cited sources
    by_id = {s.get("id"): s for s in sources if s.get("id")}
    cited = {x.upper() for x in re.findall(r"\[(S\d+)\]", body)}
    if "## 参考来源" in body:
        head, _ = body.split("## 参考来源", 1)
        refs = []
        for sid in sorted(c for c in by_id if c.upper() in cited):
            src = by_id[sid]
            title = normalize_math(str(src.get("title") or "")).replace("|", "/")
            url = str(src.get("url") or "")
            refs.append(f"- [{sid}] {title} — {url}")
        if refs:
            body = head + "## 参考来源\n\n" + "\n".join(refs) + "\n"
    return body + "\n" + _gate_table(check)
