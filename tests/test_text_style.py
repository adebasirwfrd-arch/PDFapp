"""Tests for PDF text span style inheritance."""

from app.editor.text_style import span_font_size, span_fontname_pdf


def test_span_font_size_uses_declared_size_not_bbox():
    span = {"size": 10.0, "bbox": (0, 0, 100, 40)}
    assert span_font_size(span) == 10.0


def test_span_font_size_fallback_when_missing():
    span = {"bbox": (0, 0, 100, 20)}
    assert span_font_size(span) == 14.4  # 20 * 0.72


def test_span_fontname_pdf_serif():
    assert span_fontname_pdf({"font": "TimesNewRoman-Bold"}) == "tiro"
