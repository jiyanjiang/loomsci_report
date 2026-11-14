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


def finalize(md: str, sources: list[dict], check: dict) -> str:
    """Remove machine JSON and append a human-readable evidence note."""
    body = md.split("## 证据门禁", 1)[0].rstrip()
    body = normalize_math(body)
    # add citation semantics once
    if "## 引用说明" not in body:
        body = body.replace("## 证据表", """## 引用说明

正文中的 `[Sxxx]` 是**稳定证据编号**，指向下方证据表与参考来源。导出时不重编号，便于逐条复核；编号本身不代表引用次数或重要性。

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
