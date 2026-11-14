"""Nature-style editorial passes for Report.

These passes do not add facts. They rewrite prose against the Loom_Science
L1/L2 rules and then verify that the citation set did not change.
"""

from __future__ import annotations

import re

from . import llm, style

STRUCTURE = """你是 Nature Physics Perspective 的主编。只改结构与表达，不新增/删除事实。
硬约束：
1. 开篇第一段：领域问题 + 旧解释为什么不够 + 本文检验什么；
2. 第二段：2-4 句阅读路线图，明确认知顺序；
3. 每个小节标题是问题或判断；每节 3-4 段；
4. 一段只做一个认知任务，2-4 句；禁止 bullet（证据/参考表除外）；
5. 术语首次出现给中文+英文+一句人话；
6. 删除重复的“证据不足”套话，改为具体缺口；
7. 保留所有 [Sxxx] 引用，不得新增引用，不得把理论/模拟写成实验；
8. 结论回答开篇，给出具体可检验下一步。
只输出完整 Markdown，不要解释。"""

PROSE = """你是中文科学编辑。只改语言与节奏，不改结构、论点、引用和事实。
规则：
- 每段 2-4 句；长句拆开；
- 术语首次出现软着陆；避免连续隐喻；
- 不要每句都“闪光”；保留普通承重句；
- 删除空泛判断、重复句、模板化过渡；
- 保留全部 [Sxxx]；不得新增事实/数字/URL。
只输出完整 Markdown。"""


def _cites(text: str) -> set[str]:
    return set(re.findall(r"\[(S\d{3})\]", text))


def edit(draft: str, key: str, *, passes: int = 1) -> tuple[str, list[dict]]:
    current = draft
    trace = []
    for index in range(max(1, passes)):
        system = style.report_system() + "\n\n" + (STRUCTURE if index == 0 else PROSE)
        before = _cites(current)
        try:
            candidate = llm.chat(system, current, key, max_tokens=7000, temperature=0.25, timeout=300)
        except Exception as exc:
            trace.append({"pass": index + 1, "status": "failed", "error": type(exc).__name__})
            break
        after = _cites(candidate)
        if before - after:
            trace.append({"pass": index + 1, "status": "dropped_citations",
                          "dropped": sorted(before - after)[:10]})
            break
        if after - before:
            trace.append({"pass": index + 1, "status": "new_citations",
                          "new": sorted(after - before)[:10]})
            break
        current = candidate.strip() + "\n"
        trace.append({"pass": index + 1, "status": "ok",
                      "chars": len(current), "citations": len(after)})
    return current, trace


def audit(text: str, facts: list[dict]) -> dict:
    body = text.split("## 证据表", 1)[0].split("## 参考来源", 1)[0]
    paras = [p.strip() for p in body.split("\n\n") if p.strip() and not p.lstrip().startswith(("#", "|", "-", "```"))]
    def sentences(p: str) -> int:
        return len([x for x in re.split(r"(?<=[。！？!?])", p) if x.strip()])
    long_paras = [{"chars": len(p), "sentences": sentences(p), "head": p[:60]}
                  for p in paras if sentences(p) > 5]
    cites = _cites(text)
    ids = {str(f.get("source")) for f in facts}
    return {
        "paragraphs": len(paras),
        "long_paragraphs": long_paras[:8],
        "citations": len(cites),
        "missing_sources": sorted(cites - ids),
        "bullets_in_body": sum(1 for line in body.splitlines() if line.startswith(("- ", "* "))),
        "has_roadmap": "阅读路线图" in text,
        "has_opening_problem": len(paras[0]) > 80 if paras else False,
    }


def edit_chunked(draft: str, key: str) -> tuple[str, list[dict]]:
    """Edit each section independently so a citation drop cannot poison the whole draft."""
    parts = re.split(r"(?=^## )", draft, flags=re.M)
    out = []
    trace = []
    for part in parts:
        if not part.strip() or part.lstrip().startswith(("## 证据表", "## 参考来源", "## 证据与核验", "## 引用说明")):
            out.append(part)
            continue
        before = _cites(part)
        if not before:
            out.append(part)
            continue
        try:
            candidate = llm.chat(
                style.report_system() + "\n\n" + PROSE,
                part, key, max_tokens=3000, temperature=0.2, timeout=240,
            )
        except Exception as exc:
            trace.append({"section": part.splitlines()[0][:60], "status": type(exc).__name__})
            out.append(part)
            continue
        after = _cites(candidate)
        if (before - after) or (after - before):
            trace.append({"section": part.splitlines()[0][:60], "status": "citation_mismatch",
                          "dropped": sorted(before - after)[:5], "new": sorted(after - before)[:5]})
            out.append(part)
            continue
        out.append(candidate.rstrip() + "\n\n")
        trace.append({"section": part.splitlines()[0][:60], "status": "ok",
                      "chars": len(candidate)})
    return "".join(out).rstrip() + "\n", trace


def split_long_paragraphs(text: str, max_sentences: int = 4) -> tuple[str, int]:
    """Deterministic, citation-preserving split of overlong body paragraphs."""
    body_end = text.find("## 证据表")
    head = text if body_end < 0 else text[:body_end]
    tail = "" if body_end < 0 else text[body_end:]
    blocks = head.split("\n\n")
    out = []
    changed = 0
    for block in blocks:
        stripped = block.strip()
        if not stripped or stripped.startswith(("#", "|", "-", "```")):
            out.append(block)
            continue
        sentences = [x.strip() for x in re.split(r"(?<=[。！？!?])", stripped) if x.strip()]
        if len(sentences) <= max_sentences:
            out.append(block)
            continue
        for i in range(0, len(sentences), max_sentences):
            out.append(" ".join(sentences[i:i + max_sentences]))
            changed += 1
    return "\n\n".join(out) + tail, changed
