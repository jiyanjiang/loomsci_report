"""Small official arXiv API adapter."""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass
class Paper:
    id: str
    title: str
    abstract: str
    authors: list[str]
    published: str
    category: str
    url: str


def search(query: str, max_results: int = 12) -> list[Paper]:
    term = urllib.parse.quote(f'all:"{query}"')
    url = f"{API}?search_query={term}&start=0&max_results={max_results}&sortBy=relevance"
    request = urllib.request.Request(url, headers={"User-Agent": "loomsci-report/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    papers = []
    for entry in root.findall("a:entry", NS):
        raw_id = entry.findtext("a:id", default="", namespaces=NS)
        arxiv_id = raw_id.rsplit("/", 1)[-1]
        papers.append(Paper(
            id=arxiv_id,
            title=" ".join(entry.findtext("a:title", default="", namespaces=NS).split()),
            abstract=" ".join(entry.findtext("a:summary", default="", namespaces=NS).split()),
            authors=[a.findtext("a:name", default="", namespaces=NS) for a in entry.findall("a:author", NS)],
            published=entry.findtext("a:published", default="", namespaces=NS)[:10],
            category=entry.findtext("arxiv:primary_category", default="", namespaces=NS) or "",
            url=raw_id,
        ))
    return papers
