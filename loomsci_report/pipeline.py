"""LLM-driven, Chinese-default research report pipeline.

The pipeline keeps evidence fixed before prose: sources -> claims -> themes ->
sections -> critic.  It is intentionally slower than retrieval-only output.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loomsci_core.sdk import CoreClient

from . import arxiv, export, llm, openalex, review, workspace
from . import format as report_format

SYSTEM = (
    "你是 LoomSci 的严谨研究编辑。只使用给定的来源与 claim；"
    "不得凭记忆补充事实、数字、引文或 URL。"
    "每个事实性结论后必须保留来源编号，如 [S001]。"
    "区分事实、推断与判断；证据不足时明确写“证据不足”。"
    "默认使用简体中文写作，术语首次出现可保留英文。\n"
    "写作遵循《LoomSci Report · Perspective 写作标准》："
    "开篇给问题与阅读路线图；一段一个认知任务；每个概念按直觉层/技术层/意义层展开；"
    "类比只用于降低门槛；每节标题是问题或判断；结论回答开篇。"
)


def _clean(value: str, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _source_ref(source: dict) -> dict:
    return {
        "id": source["id"],
        "title": _clean(source.get("title"), 180),
        "abstract": _clean(source.get("text") or source.get("abstract"), 900),
        "grade": source.get("grade"),
        "url": source.get("url"),
    }


def _plan(question: str, query: str, key: str) -> list[str]:
    data = llm.json_chat(
        "你是检索规划器。把中文研究问题转成 3-5 个英文检索式；只输出 JSON "
        '{"queries":["..."]}。检索式应覆盖机制、材料/平台、实验/证据、争议。',
        f"问题：{question}\n附加检索词：{query or '无'}",
        key, temperature=0.1, max_tokens=500,
    )
    queries = [str(x).strip() for x in (data.get("queries") or []) if str(x).strip()]
    if not queries:
        queries = [query or question]
    return queries[:5]


def _extract_batch(question: str, refs: list[dict], key: str) -> list[dict]:
    payload = "\n\n".join(
        f"[{s['id']}] {s['title']}\n摘要: {s['abstract']}"
        for s in refs
    )
    data = llm.json_chat(
        "你是证据抽取器。对每条来源只抽取 1 条可由摘要直接支持的事实性 claim。"
        "输出 JSON 数组，每项：source_id, claim, evidence, qualifier, relevance(1-5)。"
        "claim 必须是具体断言，不是“本文研究……”这类空话；"
        "qualifier 写适用范围/条件；不得引入摘要外知识。",
        f"研究问题：{question}\n\n来源：\n{payload}",
        key, temperature=0.1, max_tokens=2500,
    )
    if isinstance(data, dict):
        data = data.get("claims") or data.get("items") or []
    valid = {s["id"] for s in refs}
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("source_id") or "").strip().upper()
        claim = _clean(item.get("claim"), 400)
        if sid in valid and claim:
            out.append({
                "source_id": sid,
                "claim": claim,
                "evidence": _clean(item.get("evidence"), 500),
                "qualifier": _clean(item.get("qualifier"), 200),
                "relevance": max(1, min(5, int(item.get("relevance") or 3))),
            })
    return out


def _extract_all(question: str, refs: list[dict], key: str) -> list[dict]:
    batches = [refs[i:i + 10] for i in range(0, len(refs), 10)]
    claims: list[dict] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        jobs = [pool.submit(_extract_batch, question, batch, key) for batch in batches]
        for job in as_completed(jobs):
            try:
                claims.extend(job.result())
            except Exception:
                continue
    by_source = {c["source_id"]: c for c in claims}
    # Every source gets one traceable fact; LLM claims are preferred.
    for ref in refs:
        if ref["id"] not in by_source:
            by_source[ref["id"]] = {
                "source_id": ref["id"], "claim": ref["title"],
                "evidence": ref["abstract"][:400], "qualifier": "仅标题/摘要",
                "relevance": 2,
            }
    return list(by_source.values())


def _synthesize(question: str, claims: list[dict], refs: list[dict], key: str) -> dict:
    compact = "\n".join(
        f"[{c['source_id']}] {c['claim']} | 限定:{c['qualifier']} | 相关度:{c['relevance']}"
        for c in claims
    )
    data = llm.json_chat(
        "你是研究主编。基于 claim 设计一篇中文 Perspective。输出 JSON："
        '{"title":"...","thesis":"...","reader_model":"...","roadmap":["..."],'
        '"sections":[{"title":"...","question":"...","angle":"...","claim_ids":["S001"]}]}。'
        "4-5 节；标题必须是问题或判断，不是名词短语；roadmap 2-4 句；"
        "每节 6-12 条 claim；论点必须有张力且可证伪；不得引入新事实。",
        f"问题：{question}\n\n可用 claim：\n{compact}",
        key, temperature=0.2, max_tokens=2200,
    )
    if not isinstance(data, dict):
        data = {}
    ids = {c["source_id"] for c in claims}
    sections = []
    for sec in data.get("sections") or []:
        sec_ids = [str(x).upper() for x in sec.get("claim_ids") or [] if str(x).upper() in ids]
        if sec_ids:
            sections.append({"title": _clean(sec.get("title"), 80), "angle": _clean(sec.get("angle"), 300), "claim_ids": sec_ids})
    if not sections:
        ordered = [c["source_id"] for c in sorted(claims, key=lambda x: -int(x.get("relevance") or 0))]
        sections = [{"title": f"证据视角 {i + 1}", "angle": "按证据归纳", "claim_ids": ordered[i::4][:12]} for i in range(4)]
    return {"title": _clean(data.get("title") or question, 120),
            "thesis": _clean(data.get("thesis"), 700),
            "reader_model": _clean(data.get("reader_model"), 400),
            "roadmap": [_clean(x, 300) for x in (data.get("roadmap") or []) if str(x).strip()][:4],
            "sections": sections[:5]}


def _write_section(question: str, thesis: str, section: dict, claims: list[dict], key: str) -> str:
    selected = [c for c in claims if c["source_id"] in set(section["claim_ids"])]
    refs = "\n".join(
        f"[{c['source_id']}] claim: {c['claim']}\n证据: {c['evidence']}\n限定: {c['qualifier']}"
        for c in selected
    )
    return llm.chat(
        SYSTEM + " 只写这一节；不要重复其他节；保留来源编号。",
        f"总问题：{question}\n中心论点：{thesis}\n本节标题：{section['title']}\n"
        f"本节问题：{section.get('question') or section.get('angle') or ''}\n本节角度：{section['angle']}\n"
        f"可用证据：\n{refs}\n\n"
        "写 700-1000 字中文分析。第一段先降低门槛：本节要解决什么问题、读者需要先知道什么；"
        "之后按‘证据→竞争解释/边界→判断’推进。每段只做一个认知任务，2-5 句；不要用 bullet。",
        key, temperature=0.35, max_tokens=1800,
    )


def _critic(draft: str, allowed: list[str], key: str) -> str:
    return llm.chat(
        SYSTEM + " 你是严格的中文主编。只修文字、结构与论证，不得增加新事实或新引用。",
        f"允许的来源编号：{', '.join(allowed[:60])}\n\n待修稿：\n{draft}\n\n"
        "输出修订后的完整 Markdown。保留所有 [Sxxx] 引用；删除空话；把描述性段落改成有论点的论证；"
        "确保标题、摘要、分节和结论互相一致。",
        key, temperature=0.25, max_tokens=6000, timeout=240,
    )


def generate(job_id: str, question: str, query: str, data_dir: Path, update) -> dict:
    key = llm.deepseek_key()
    if not key:
        raise llm.LlmError("DeepSeek key missing; set DEEPSEEK_API_KEY or ~/.loomsci/config.yaml")
    update(stage="planning", progress=0.05)
    queries = _plan(question, query, key)

    update(stage="searching", progress=0.15)
    papers = []
    seen = set()
    for q in queries:
        try:
            found = arxiv.search(q, max_results=40)
        except Exception:
            found = []
        for paper in found:
            if paper.id not in seen:
                seen.add(paper.id)
                papers.append(paper)
        if len(papers) >= 100:
            break
    papers = papers[:100]
    if not papers:
        try:
            papers = arxiv.search(query or question, max_results=100)
        except Exception:
            papers = []
    if not papers:
        raise RuntimeError("arXiv returned no records after fallback")

    ws = workspace.new(question, data_dir / "research", title=question[:80])
    refs = []
    for paper in papers:
        source = workspace.add_source(data_dir / "research", ws["code"], ws["version"], {
            "url": paper.url, "domain": "arxiv.org", "title": paper.title,
            "authors": paper.authors, "year": paper.published[:4],
            "arxiv": paper.id, "license": "arXiv", "abstract": paper.abstract,
        })
        refs.append(_source_ref({**source, "abstract": paper.abstract}))
    extra_sources = []
    try:
        for work in openalex.search(query or question, max_results=10):
            url = ("https://doi.org/" + work.doi) if work.doi else work.url
            if url:
                source = workspace.add_source(data_dir / "research", ws["code"], ws["version"], {
                    "url": url, "title": work.title, "authors": work.authors,
                    "year": work.year, "openalex": work.id, "license": "unknown",
                })
                extra_sources.append(source)
    except Exception:
        pass

    update(stage="extracting", progress=0.30, found=len(papers), workspace=ws)
    claims = _extract_all(question, refs, key)
    try:
        assessment = review.assess_sufficiency(question, claims, key)
    except Exception:
        assessment = {"sufficient": True, "reasons": [], "extra_queries": []}
    extra_queries = [str(q) for q in (assessment.get("extra_queries") or []) if str(q).strip()][:2]
    for extra_query in extra_queries:
        try:
            found = arxiv.search(extra_query, max_results=20)
        except Exception:
            found = []
        new_refs = []
        for paper in found:
            source = workspace.add_source(data_dir / "research", ws["code"], ws["version"], {
                "url": paper.url, "domain": "arxiv.org", "title": paper.title,
                "authors": paper.authors, "year": paper.published[:4],
                "arxiv": paper.id, "license": "arXiv", "abstract": paper.abstract,
            })
            if source["id"] not in {r["id"] for r in refs}:
                refs.append(_source_ref({**source, "abstract": paper.abstract}))
                papers.append(paper)
                new_refs.append(refs[-1])
        if new_refs:
            new_claims = _extract_all(question, new_refs, key)
            have = {c["source_id"] for c in claims}
            claims.extend(c for c in new_claims if c["source_id"] not in have)
    # Numeric floor: every source should carry one traceable record.
    for source in extra_sources:
        if len(claims) >= 100:
            break
        if any(c["source_id"] == source["id"] for c in claims):
            continue
        claims.append({
            "source_id": source["id"], "claim": _clean(source.get("title"), 400),
            "evidence": "OpenAlex metadata only", "qualifier": "仅题录，未读全文",
            "relevance": 2,
        })
    for claim in claims:
        ref = next((r for r in refs if r["id"] == claim["source_id"]), None)
        if ref is None:
            ref = next((_source_ref(x) for x in extra_sources if x["id"] == claim["source_id"]), None)
        if ref:
            workspace.add_fact(data_dir / "research", ws["code"], ws["version"],
                               claim=claim["claim"], url=ref["url"],
                               quote=(claim.get("evidence") or "")[:800])

    ranked = sorted(claims, key=lambda c: (-int(c.get("relevance") or 0), c["source_id"]))
    selected = ranked[:40]
    update(stage="synthesizing", progress=0.48, facts=len(claims), selected=len(selected))
    plan = _synthesize(question, selected, refs, key)

    update(stage="writing", progress=0.58)
    sections = []
    with ThreadPoolExecutor(max_workers=min(4, len(plan["sections"]))) as pool:
        jobs = {pool.submit(_write_section, question, plan["thesis"], sec, selected, key): sec
                for sec in plan["sections"]}
        by_title = {}
        for job in as_completed(jobs):
            sec = jobs[job]
            try:
                by_title[sec["title"]] = job.result()
            except Exception:
                by_title[sec["title"]] = f"## {sec['title']}\n\n证据不足，未能生成该节。\n"
        sections = [by_title.get(sec["title"], "") for sec in plan["sections"]]

    allowed = [c["source_id"] for c in selected]
    draft = f"""# {plan['title']}

## 摘要

{plan['thesis']}

## 中心论点

{plan['thesis']}

## 阅读路线图

{(chr(10).join(f"{i+1}. {x}" for i, x in enumerate(plan.get("roadmap") or [])) or "先看证据能支持什么，再看它不能支持什么。")}

""" + "\n\n".join(sections) + """

## 证据表

| 来源 | 判断 | 限定 |
|---|---|---|
""" + "\n".join(
        f"| [{c['source_id']}] | {c['claim'][:120]} | {c['qualifier'][:80]} |"
        for c in selected
    ) + """

## 开放问题

- 哪些证据能区分竞争性解释？
- 哪些结论依赖特定材料、平台或制备条件？
- 什么结果会证伪本文中心论点？

## 参考来源

""" + "\n".join(f"- [{c['source_id']}] {next((r['title'] for r in refs if r['id'] == c['source_id']), '')}" for c in selected)

    update(stage="critiquing", progress=0.78)
    try:
        draft = _critic(draft, allowed, key)
    except Exception:
        pass
    workspace.write_draft(data_dir / "research", ws["code"], ws["version"], draft)
    check = workspace.check(data_dir / "research", ws["code"], ws["version"], [question])
    all_sources = [json.loads(line) for line in (data_dir / "research" / "workspaces" / ws["code"] / ws["version"] / "sources.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    body = report_format.finalize(draft, all_sources, check)
    workspace.write_draft(data_dir / "research", ws["code"], ws["version"], body)

    tags = ["report", "zh", "llm", "arxiv", "openalex"]
    if check.get("ok"):
        tags.append("verified")
    client = CoreClient(os.environ["LOOMSCI_CORE_URL"], os.environ["LOOMSCI_APP_TOKEN"])
    item = client.create_item(app="report", type="report.report", title="", body=body, tags=tags)
    export_dir = data_dir / "research" / "workspaces" / ws["code"] / ws["version"] / "exports"
    bundle = export.export_all(body, export_dir, plan["title"], slug=f"report-{ws['code']}")
    blobs = []
    for fmt, ctype in (("md", "text/markdown"), ("pdf", "application/pdf"), ("epub", "application/epub+zip")):
        path = Path(bundle[fmt]["path"])
        blob = client.upload_blob(filename=path.name, content_type=ctype, data=path.read_bytes(), item_id=item["id"])
        blobs.append({"filename": path.name, "id": blob["id"], "bytes": path.stat().st_size})
    client.update_item(item["id"], metadata={"exports": blobs})
    summary = workspace.summary(data_dir / "research", ws["code"], ws["version"])
    return {"item_id": item["id"], "papers": len(papers), "workspace": ws,
            "workspace_summary": summary, "check": check, "queries": queries,
            "exports": bundle, "blobs": blobs, "assessment": assessment}
