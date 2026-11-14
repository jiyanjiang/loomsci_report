"""Claim-graph-first report writing.

The old path wrote sections first and let a critic patch them. This path selects
a small argument spine before any prose exists, so the report can omit claims
instead of cataloguing every retrieved record.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import llm, style

GRAPH_SCHEMA = """只输出 JSON：
{"title":"8-18 个汉字",
 "thesis":"一句可证伪的中心判断",
 "reader_model":"读者已有知识/误区",
 "roadmap":["第一步","第二步","第三步"],
 "arguments":[
   {"title":"问题或判断式标题","question":"本节要回答什么",
    "claim_ids":["S001","S002"],"boundary_claim_ids":["S003"]}
 ]}
3-4 个 arguments；总共只选 12-18 条 claim；每个 argument 3-5 条；
必须有一条竞争解释/边界 claim；不得引入不存在的编号。"""


def build(question: str, claims: list[dict], refs: list[dict], key: str) -> dict:
    by_id = {c["source_id"]: c for c in claims}
    compact = "\n".join(
        f"[{c['source_id']}] {c.get('claim','')} | 限定:{c.get('qualifier','')}"
        for c in claims
    )
    data = llm.json_chat(
        "你是研究主编。先建论点树，不写正文。不要按来源顺序组织；按论证需要选证据。"
        + GRAPH_SCHEMA,
        f"问题：{question}\n\n候选 claim：\n{compact}",
        key, temperature=0.15, max_tokens=2500,
    )
    if not isinstance(data, dict):
        raise ValueError("graph must be an object")
    seen = set()
    args = []
    for arg in data.get("arguments") or []:
        ids = []
        for sid in arg.get("claim_ids") or []:
            sid = str(sid).upper()
            if sid in by_id and sid not in seen:
                ids.append(sid)
                seen.add(sid)
        boundary = [str(x).upper() for x in arg.get("boundary_claim_ids") or [] if str(x).upper() in by_id]
        if ids:
            args.append({"title": str(arg.get("title") or "未命名论证")[:90],
                         "question": str(arg.get("question") or "")[:300],
                         "claim_ids": ids[:6], "boundary_claim_ids": boundary[:2]})
    if len(args) < 2:
        raise ValueError("graph needs at least two arguments")
    selected = [c for c in claims if c["source_id"] in seen]
    return {
        "title": str(data.get("title") or question)[:100],
        "thesis": str(data.get("thesis") or "")[:800],
        "reader_model": str(data.get("reader_model") or "")[:400],
        "roadmap": [str(x)[:300] for x in (data.get("roadmap") or []) if str(x).strip()][:4],
        "arguments": args[:4],
        "selected": selected,
    }


def write_section(question: str, thesis: str, argument: dict, claims: list[dict], key: str) -> str:
    by_id = {c["source_id"]: c for c in claims}
    selected = [by_id[i] for i in argument["claim_ids"] if i in by_id]
    boundary = [by_id[i] for i in argument["boundary_claim_ids"] if i in by_id]
    evidence = "\n".join(
        f"[{c['source_id']}] {c.get('claim')}\n限定: {c.get('qualifier','')}"
        for c in selected + boundary
    )
    return llm.chat(
        style.report_system() + "\n\n" + (
            "你是报告分节作者。只写这一节，不能写其他节，不得新增事实、数字、URL、引用。"
            "本节必须包含 3-4 个自然段；每段只做一个认知任务；每段 2-4 句；禁止 bullet。"
            "先给读者降低门槛：本节要解决什么问题、为什么不是上一个问题的重复；"
            "再给证据与竞争解释；最后给出本节判断，并明确边界。"
            "所有事实句末尾保留对应 [Sxxx]。"
        ),
        f"总问题：{question}\n中心判断：{thesis}\n本节标题：{argument['title']}\n"
        f"本节问题：{argument['question']}\n可用证据：\n{evidence}\n\n写 600-900 字。",
        key, temperature=0.25, max_tokens=2200, timeout=240,
    )


def write_report(question: str, graph: dict, key: str) -> str:
    # Sequential: concurrent flash/chat calls hit provider rate limits and
    # leave placeholder sections, which is worse than waiting.
    sections = []
    for arg in graph["arguments"]:
        text = ""
        for _ in range(2):
            try:
                text = write_section(question, graph["thesis"], arg, graph["selected"], key)
                if text.strip():
                    break
            except Exception:
                text = ""
        if not text.strip():
            raise RuntimeError(f"section failed: {arg['title']}")
        sections.append(text.strip())
    selected = graph["selected"]
    table = "\n".join(
        f"| [{c['source_id']}] | {c.get('claim','')[:180].replace('|','/')} | {c.get('qualifier','')[:100].replace('|','/')} |"
        for c in selected
    )
    return f"""# {graph['title']}

## 摘要

{graph['thesis']}

## 核心判断

**判断：** {graph['thesis']}

## 阅读路线图

""" + "\n".join(f"{i+1}. {x}" for i, x in enumerate(graph["roadmap"])) + f"""

{"\n\n".join(sections)}

## 证据表

| 来源 | 判断 | 限定 |
|---|---|---|
{table}

## 开放问题

- 哪些独立观测能排除本文列出的竞争解释？
- 哪条材料路线能给出可复现的编织判据？
- 哪些结论依赖样品、应变或解理条件？
"""
