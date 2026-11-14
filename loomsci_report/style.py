"""Adapter to Loom_Science's L1/L2 writing system.

The Report app owns evidence and section planning; Loom_Science owns the
editorial constitution and narrative grammar. If LOOMSCI_STYLE_DIR is absent,
fall back to the report-specific standard only.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

FALLBACK = (
    "你是 LoomSci 的严谨研究编辑。只使用给定的来源与 claim；"
    "不得凭记忆补充事实、数字、引文或 URL。每个事实性结论后必须保留 [Sxxx]。"
    "区分事实、推断与判断；默认简体中文。"
)

FILES = ("macro_prompt_en.md", "L2_narrative_syntax_en.md")


@lru_cache(maxsize=1)
def report_system() -> str:
    base = Path(__file__).resolve().parent.parent
    report_standard = base / "prompts" / "report_perspective_zh.md"
    parts = [FALLBACK]
    if report_standard.is_file():
        parts.append(report_standard.read_text(encoding="utf-8"))
    style_dir = Path(os.environ.get("LOOMSCI_STYLE_DIR", "")).expanduser()
    if style_dir.is_dir():
        for name in FILES:
            path = style_dir / name
            if path.is_file():
                parts.append(f"### Loom_Science source: {name}\n" + path.read_text(encoding="utf-8")[:14000])
    return "\n\n".join(parts)
