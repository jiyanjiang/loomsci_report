"""OpenAlex adapter, used as an arXiv-independent retrieval fallback."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = "https://api.openalex.org/works"


@dataclass
class Work:
    id: str
    doi: str
    title: str
    abstract: str
    authors: list[str]
    year: int | None
    url: str


def _abstract(value: dict | None) -> str:
    """Rebuild OpenAlex's abstract_inverted_index into readable text."""
    if not isinstance(value, dict):
        return ""
    slots: dict[int, str] = {}
    for word, positions in value.items():
        for pos in positions or []:
            try:
                slots[int(pos)] = str(word)
            except (TypeError, ValueError):
                continue
    return " ".join(slots[i] for i in sorted(slots))[:4000]


def search(query: str, max_results: int = 100) -> list[Work]:
    params = urllib.parse.urlencode({"search": query, "per-page": min(100, max_results)})
    request = urllib.request.Request(API + "?" + params, headers={"User-Agent": "loomsci-report/0.1"})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = json.load(response)
    out = []
    for item in data.get("results") or []:
        primary = item.get("primary_location") or {}
        best = item.get("best_oa_location") or {}
        landing = str(best.get("landing_page_url") or primary.get("landing_page_url") or "")
        doi = str(item.get("doi") or "").replace("https://doi.org/", "")
        if not landing:
            landing = ("https://doi.org/" + doi) if doi else str(item.get("id") or "")
        out.append(Work(
            id=str(item.get("id") or ""),
            doi=doi,
            title=str(item.get("title") or ""),
            abstract=_abstract(item.get("abstract_inverted_index")),
            authors=[str(a.get("author", {}).get("display_name") or "") for a in item.get("authorships") or []],
            year=item.get("publication_year"),
            url=landing,
        ))
    return out[:max_results]
