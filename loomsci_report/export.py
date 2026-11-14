"""Deliver a report as Markdown, PDF and EPUB."""

from __future__ import annotations

import html
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

try:
    import markdown
except Exception:  # pragma: no cover
    markdown = None

CSS = """
@page { size: A4; margin: 18mm 17mm; }
body { font-family: "PingFang SC", "Noto Sans CJK SC", "Songti SC", serif;
       color: #1d232b; font-size: 11pt; line-height: 1.75; }
h1 { font-size: 22pt; line-height: 1.35; margin: 0 0 10mm; }
h2 { font-size: 15pt; margin-top: 8mm; border-bottom: 1px solid #d8dee7; padding-bottom: 2mm; }
h3 { font-size: 12.5pt; margin-top: 6mm; }
p { margin: 0 0 3.2mm; text-align: justify; }
blockquote { border-left: 3px solid #8aa0b8; margin-left: 0; padding-left: 4mm; color: #445; }
table { border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 4mm 0; }
th, td { border: 1px solid #cfd7e2; padding: 1.5mm 2mm; vertical-align: top; }
th { background: #eef2f7; }
code, pre { font-family: "SFMono-Regular", Menlo, monospace; font-size: 8.5pt; }
pre { background: #f6f8fa; padding: 3mm; white-space: pre-wrap; }
a { color: #1558a6; text-decoration: none; }
"""


def _html(md_text: str, title: str) -> str:
    if markdown is not None:
        body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    else:
        body = "<pre>" + html.escape(md_text) + "</pre>"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body>{body}</body></html>
"""


def _pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = os.environ.get("CHROME_BIN") or shutil.which("google-chrome") or shutil.which("chromium")
    candidates = [chrome, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    executable = next((p for p in candidates if p and Path(p).is_file()), None)
    if not executable:
        raise RuntimeError("Chrome/Chromium not found for PDF export")
    profile = tempfile.mkdtemp(prefix="loomsci-pdf-")
    try:
        subprocess.run([
            executable, "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--user-data-dir={profile}", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri(),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not pdf_path.is_file() or pdf_path.stat().st_size < 1000:
        raise RuntimeError("PDF export produced no usable file")


def _epub(md_text: str, title: str, epub_path: Path) -> None:
    ident = "urn:uuid:" + str(uuid.uuid4())
    body = _html(md_text, title)
    inner = body.split("<body>", 1)[1].rsplit("</body>", 1)[0] if "<body>" in body else body
    xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN" lang="zh-CN">
<head><meta charset="utf-8"/><title>{escape(title)}</title><style>{CSS}</style></head>
<body>{inner}</body></html>"""
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{escape(title)}</dc:title><dc:language>zh-CN</dc:language>
<dc:identifier id="bookid">{ident}</dc:identifier>
</metadata>
<manifest><item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="css" href="style.css" media-type="text/css"/></manifest>
<spine toc="ncx"><itemref idref="content"/></spine></package>"""
    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{ident}"/></head><docTitle><text>{escape(title)}</text></docTitle>
<navMap><navPoint id="n1" playOrder="1"><navLabel><text>{escape(title)}</text></navLabel>
<content src="content.xhtml"/></navPoint></navMap></ncx>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
    with zipfile.ZipFile(epub_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)


def export_all(md_text: str, out_dir: Path, title: str, slug: str = "report") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{slug}.md"
    html_path = out_dir / f"{slug}.html"
    pdf_path = out_dir / f"{slug}.pdf"
    epub_path = out_dir / f"{slug}.epub"
    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(_html(md_text, title), encoding="utf-8")
    _pdf(html_path, pdf_path)
    _epub(md_text, title, epub_path)
    return {
        "md": {"path": str(md_path), "bytes": md_path.stat().st_size},
        "pdf": {"path": str(pdf_path), "bytes": pdf_path.stat().st_size},
        "epub": {"path": str(epub_path), "bytes": epub_path.stat().st_size},
        "html": str(html_path),
    }
