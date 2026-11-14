"""Minimal OpenAlex adapter for a second independent source domain."""

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


def search(query: str, max_results: int = 10) -> list[Work]:
    params = urllib.parse.urlencode({
        "search": query,
        "per-page": max_results,
    })
    request = urllib.request.Request(API + "?" + params, headers={"User-Agent": "loomsci-report/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    out = []
    for item in data.get("results") or []:
        doi = str(item.get("doi") or "").replace("https://doi.org/", "")
        url = str(item.get("doi") or item.get("id") or "")
        out.append(Work(
            id=str(item.get("id") or ""),
            doi=doi,
            title=str(item.get("title") or ""),
            abstract="",
            authors=[str(a.get("author", {}).get("display_name") or "") for a in item.get("authorships") or []],
            year=item.get("publication_year"),
            url=url,
        ))
    return out
