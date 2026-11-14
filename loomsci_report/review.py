"""Independent LLM review for a report draft.

Three reviewers read the same draft with different mandates. The synthesis is
advisory: it can identify weaknesses, but it cannot override the evidence gate.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import llm

REVIEWERS = [
    ("领域审稿人", "检查物理/领域事实、过度概括、竞争解释是否被公平对待；重点找会被专家一眼看出的错误。"),
    ("证据审稿人", "检查每个关键判断是否有来源支撑、引用是否对应、是否存在 claim 与来源不匹配、证据不足却下强结论。"),
    ("中文编辑", "检查中文可读性、论证结构、空话、重复、标题与结论一致性；不评价领域事实。"),
]

SCHEMA = """只输出 JSON：
{"verdict":"accept|major_revision|reject","score":0-100,
 "summary":"一句话结论",
 "strengths":["值得保留的优点"],
 "issues":[{"severity":"P0|P1|P2","quote":"原文短句","problem":"问题",
            "fix":"可直接执行的修法","extra_query":"可选：需要补充调研的英文检索式"}]}
最多 10 条 issue；P0=事实/引用错误或严重过度概括，P1=论证缺口，P2=文字/结构。
每个 issue 必须给出 fix；不要只挑错。若证据单薄，在 extra_query 给出补充检索式。"""


def _one(role: str, mandate: str, draft: str, claims: str, key: str) -> dict:
    data = llm.json_chat(
        f"你是独立{role}。{mandate} 你不负责改写，只做审稿。{SCHEMA}",
        f"【报告】\n{draft[:30000]}\n\n【证据 claim】\n{claims[:20000]}",
        key, temperature=0.1, max_tokens=2600, timeout=240,
    )
    if not isinstance(data, dict):
        data = {}
    return {"role": role, "verdict": data.get("verdict") or "major_revision",
            "score": int(data.get("score") or 0), "summary": data.get("summary") or "",
            "strengths": data.get("strengths") or [], "issues": data.get("issues") or []}


def independent_review(draft: str, claims: list[dict], key: str) -> list[dict]:
    compact = "\n".join(
        f"[{c.get('source_id')}] {c.get('claim')} | 限定:{c.get('qualifier')}"
        for c in claims[:100]
    )
    reviews = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(_one, role, mandate, draft, compact, key) for role, mandate in REVIEWERS]
        for job in as_completed(jobs):
            try:
                reviews.append(job.result())
            except Exception as exc:
                reviews.append({"role": "reviewer", "verdict": "major_revision", "score": 0,
                                "summary": f"review failed: {type(exc).__name__}", "issues": []})
    return reviews


def assess_sufficiency(question: str, claims: list[dict], key: str) -> dict:
    """Ask an LLM whether the evidence set is thin before writing."""
    compact = "\n".join(f"[{c.get('source_id')}] {c.get('claim')}" for c in claims[:80])
    data = llm.json_chat(
        "你是研究证据评估员。判断给定 claim 是否足以支撑一篇有论点的中文报告。"
        '只输出 JSON：{"sufficient":true|false,"reasons":["..."],"extra_queries":["英文检索式"]}。'
        "若不足，extra_queries 1-3 条，针对缺失的机制/平台/反例。",
        f"问题：{question}\n\n现有 claim：\n{compact}",
        key, temperature=0.1, max_tokens=700,
    )
    return data if isinstance(data, dict) else {"sufficient": True, "reasons": [], "extra_queries": []}


def to_markdown(reviews: list[dict]) -> str:
    lines = ["# 独立审稿", ""]
    for r in reviews:
        lines += [f"## {r['role']} · {r['verdict']} · {r['score']}/100", "",
                  r.get("summary") or "", ""]
        for s in r.get("strengths") or []:
            lines.append(f"- 优点：{s}")
        for issue in r.get("issues") or []:
            lines += [f"- **{issue.get('severity','P1')}** {issue.get('problem','')}",
                      f"  - 原文：{issue.get('quote','')}",
                      f"  - 修法：{issue.get('fix','')}",
                      (f"  - 补充检索：{issue.get('extra_query')}" if issue.get('extra_query') else "")]
        lines.append("")
    scores = [int(r.get("score") or 0) for r in reviews]
    lines += ["## 综合", "",
              f"- 平均分：{sum(scores)/len(scores):.1f}/100" if scores else "- 无评分",
              f"- P0 数：{sum(1 for r in reviews for i in r.get('issues') or [] if i.get('severity')=='P0')}",
              f"- P1 数：{sum(1 for r in reviews for i in r.get('issues') or [] if i.get('severity')=='P1')}",
              ""]
    return "\n".join(lines)
