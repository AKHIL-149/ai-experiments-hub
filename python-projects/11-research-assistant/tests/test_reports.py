"""
Downloadable reports.

Found by downloading one: every report came from the saved research, whose findings are named
`finding_text`/`num_sources` while the generators read `text`/`sources`, so reports had a summary and
nothing else, and every source was "unknown". Also: a source URL went unescaped into the HTML report
(a quote ended the attribute, "javascript:" ran when clicked), and PDF export raised an OSError where
pango is missing instead of saying it is unavailable.
"""

import json

import pytest

from src.utils.report_generator import ReportGenerator

# a research as loaded from the database
SAVED = {
    "query_id": "q-1", "query": "What is RAG?", "summary": "RAG fetches documents.",
    "confidence": 0.7, "avg_confidence": 0.7, "processing_time": 12.5,
    "findings": [{"finding_text": "RAG retrieves.", "finding_type": "fact", "confidence": 0.9, "source_ids": ["a", "b"], "num_sources": 2}],
    "sources": [{"title": "Paper A", "url": "https://arxiv.org/abs/1", "source_type": "arxiv", "rank": 1}],
    "citations": ["Doe, J. (2025). Paper A."],
}


@pytest.fixture
def gen(tmp_path):
    return ReportGenerator(output_dir=str(tmp_path))


def read(path):
    return path.read_text(encoding="utf-8")


class TestSavedShape:
    def test_markdown_has_the_findings_and_sources(self, gen):
        text = read(gen.generate_report(SAVED, "markdown", "r"))
        assert "RAG retrieves." in text and "**Sources**: 2" in text and "(*arxiv*)" in text
        assert "Doe, J. (2025)" in text and "Sources Used: 1" in text.replace("**", "")

    def test_html_has_the_findings_and_sources(self, gen):
        text = read(gen.generate_report(SAVED, "html", "r"))
        assert "RAG retrieves." in text and "<em>(arxiv)</em>" in text and "Sources: 2" in text

    def test_json_has_normalised_findings_and_stats(self, gen):
        data = json.loads(read(gen.generate_report(SAVED, "json", "r")))
        assert data["findings"][0]["text"] == "RAG retrieves." and data["stats"]["findings"] == 1
        assert data["stats"]["avg_confidence"] == 0.7 and data["stats"]["processing_time"] == 12.5

    def test_docx_has_the_findings(self, gen):
        from docx import Document
        doc = Document(str(gen.generate_report(SAVED, "docx", "r")))
        assert any("RAG retrieves." in p.text for p in doc.paragraphs)

    def test_the_fresh_shape_still_works(self, gen):
        fresh = {"query": "q", "summary": "s", "findings": [{"text": "T", "type": "fact", "confidence": 0.5, "sources": 3}],
                 "sources": [{"title": "x", "url": None, "type": "web", "composite_score": 0.5}], "citations": [],
                 "stats": {"used_sources": 1, "findings": 1, "avg_confidence": 0.5, "processing_time": 1}}
        text = read(gen.generate_report(fresh, "markdown", "r"))
        assert "T" in text and "**Sources**: 3" in text and "Score: 0.50" in text

    def test_missing_pieces_do_not_crash(self, gen):
        for fmt in ("markdown", "html", "json", "docx"):
            gen.generate_report({"query": "q", "findings": [{"confidence": None}], "sources": [{}]}, fmt, f"empty_{fmt}")

    def test_the_input_is_not_modified(self, gen):
        before = json.dumps(SAVED, sort_keys=True)
        gen.generate_report(SAVED, "html", "r")
        assert json.dumps(SAVED, sort_keys=True) == before


class TestHtmlSafety:
    EVIL = {"query": "<script>alert(1)</script>", "query_id": "<b>id</b>", "summary": "<img src=x onerror=alert(1)>",
            "findings": [{"text": "<svg onload=alert(1)>", "type": "<i>", "confidence": 0.5, "sources": 1}],
            "sources": [
                {"title": "<u>t</u>", "url": "https://x.example/'><script>alert(2)</script>", "type": "web"},
                {"title": "js", "url": "javascript:alert(3)", "type": "<b>web</b>"},
            ],
            "citations": ["<script>alert(4)</script>"]}

    def test_nothing_from_the_data_becomes_markup(self, gen):
        text = read(gen.generate_report(self.EVIL, "html", "evil"))
        body = text.split("</style>", 1)[1]
        for tag in ("<script", "<img", "<svg", "<u>", "<i>", "<b>"):
            assert tag not in body, tag

    def test_a_quote_in_a_url_cannot_leave_the_attribute(self, gen):
        text = read(gen.generate_report(self.EVIL, "html", "evil"))
        assert "href=\"https://x.example/&#39;&gt;&lt;script&gt;alert(2)&lt;/script&gt;\"" in text

    def test_javascript_addresses_are_text_not_links(self, gen):
        text = read(gen.generate_report(self.EVIL, "html", "evil"))
        assert "href=\"javascript" not in text and "javascript:alert(3)" in text

    def test_links_open_safely(self, gen):
        assert "rel='noopener noreferrer'" in read(gen.generate_report(SAVED, "html", "r"))

    def test_markdown_only_links_web_addresses(self, gen):
        text = read(gen.generate_report(self.EVIL, "markdown", "evil"))
        assert "](<javascript" not in text and "[javascript" not in text


class TestFormats:
    def test_an_unknown_format_is_a_value_error(self, gen):
        with pytest.raises(ValueError, match="Unsupported format"):
            gen.generate_report(SAVED, "exe", "r")
        with pytest.raises(ValueError):
            gen.generate_report(SAVED, "", "r")

    def test_aliases(self, gen):
        assert gen.generate_report(SAVED, "MD", "a").suffix == ".md"
        assert gen.generate_report(SAVED, "doc", "b").suffix == ".docx"

    def test_a_missing_pango_is_reported_as_unavailable(self, gen, monkeypatch):
        import builtins
        real = builtins.__import__

        def fake(name, *a, **k):
            if name == "weasyprint":
                raise OSError("cannot load library 'pango-1.0-0'")
            return real(name, *a, **k)
        monkeypatch.setattr(builtins, "__import__", fake)
        with pytest.raises(ValueError, match="pango"):
            gen.generate_report(SAVED, "pdf", "r")
        assert "pdf" not in gen.get_info()["supported_formats"]
