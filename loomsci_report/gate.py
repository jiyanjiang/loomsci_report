"""Deterministic evidence gate, adapted from research.ask."""

from __future__ import annotations

import re
import urllib.parse

STRONG = {"official", "primary"}
OFFICIAL = (".gov", ".gov.cn", "europa.eu", "loc.gov")
PRIMARY = ("arxiv.org", "doi.org", "nature.com", "science.org", "aps.org", "springer.com", "ac.cn")
SECONDARY = ("openalex.org", "crossref.org", "europepmc.org", "wikipedia.org")
WEAK = ("sohu.com", "163.com", "sina.com.cn", "qq.com", "toutiao.com", "baijiahao.baidu.com")


def host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def grade_for(url: str) -> str:
    h = host(url)
    if any(x in h for x in OFFICIAL):
        return "official"
    if any(x in h for x in PRIMARY):
        return "primary"
    if any(x in h for x in SECONDARY):
        return "secondary"
    return "weak"


def evaluate(answer: str, sources: list[dict], *, query_terms: list[str] | None = None) -> dict:
    srcs = [s for s in sources if isinstance(s, dict) and s.get("url")]
    domains = {host(s["url"]) for s in srcs if host(s["url"])}
    strong = {s.get("id") or s.get("url") for s in srcs if str(s.get("grade") or "") in STRONG}
    ids = {str(s.get("id") or "").upper() for s in srcs if s.get("id")}
    urls = {str(s.get("url") or "") for s in srcs if s.get("url")}
    cited_ids = {x.upper() for x in re.findall(r"\[(S\d+)\]", answer or "", re.I)}
    cited_urls = {u.rstrip(".,);]") for u in re.findall(r"https?://[^\s)>\]]+", answer or "")}
    cited = (cited_ids & ids) | (cited_urls & urls)
    abstain = bool(re.search(r"来源不足|无法核验|未能核验|缺证据|无来源|未核验", answer or ""))
    reasons = []
    if len(domains) < 2:
        reasons.append(f"独立来源域名不足({len(domains)})")
    if not strong:
        reasons.append("缺少官方/一手/学术来源")
    if len(cited) < 2:
        reasons.append(f"答案引用来源不足({len(cited)})")
    if abstain:
        reasons.append("答案显式声明来源不足/未核验")
    topical = None
    terms = [str(t).lower() for t in (query_terms or []) if t and len(str(t)) >= 2]
    if terms:
        used = [s for s in srcs if str(s.get("id") or "").upper() in cited_ids
                or str(s.get("url") or "") in cited_urls]
        topical = 0
        for source in used:
            blob = f"{source.get('title') or ''} {source.get('abstract') or ''} {source.get('text') or ''}".lower()
            if any(term in blob for term in terms):
                topical += 1
        if used and topical == 0:
            reasons.append(f"被引用来源({len(used)})与检索词无任何交集（疑似跑题）")
    return {
        "ok": not reasons,
        "status": "verified" if not reasons else "unverified",
        "reasons": reasons,
        "source_count": len(srcs),
        "domain_count": len(domains),
        "strong_count": len(strong),
        "cited_count": len(cited),
        "cited": sorted(str(x) for x in cited)[:8],
        "topical_count": topical,
        "abstained": abstain,
    }
