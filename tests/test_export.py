import tempfile
import unittest
import zipfile
from pathlib import Path

from loomsci_report import export


class ExportTests(unittest.TestCase):
    def test_epub_is_readable_zip_with_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.epub"
            export._epub("# 标题\n\n中文正文 [S001]\n", "中文报告", path)
            with zipfile.ZipFile(path) as z:
                self.assertEqual(z.read("mimetype"), b"application/epub+zip")
                self.assertIn("中文正文", z.read("OEBPS/content.xhtml").decode("utf-8"))
                self.assertIn("OEBPS/content.opf", z.namelist())

    def test_html_contains_tables(self):
        text = export._html("| A | B |\n|---|---|\n| 1 | 2 |", "T")
        self.assertIn("<table>", text)
        self.assertIn("lang=\"zh-CN\"", text)
