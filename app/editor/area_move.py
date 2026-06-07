"""Capture and reposition a rectangular region of a PDF page."""

from __future__ import annotations

import contextlib
import os
import tempfile

from app.editor.text_style import (
    insert_multiline_text,
    sample_background_fitz,
    span_baseline,
    span_color_pdf,
    span_font_size,
    span_fontname_pdf,
)


def area_move_delta(edit: dict) -> tuple[float, float]:
    src = edit.get("src_rect") or (0, 0, 0, 0)
    dst = edit.get("dst_rect") or src
    return float(dst[0]) - float(src[0]), float(dst[1]) - float(src[1])


def extract_text_spans_in_rect(page, rect) -> list[dict]:
    """Collect PDF text spans intersecting *rect* (page coords)."""
    import fitz

    clip = fitz.Rect(rect)
    spans: list[dict] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text") or ""
                if not text.strip():
                    continue
                sb = fitz.Rect(span["bbox"])
                if sb.intersects(clip):
                    ox, oy = span_baseline(span)
                    spans.append({
                        "text": text,
                        "bbox": [sb.x0, sb.y0, sb.x1, sb.y1],
                        "origin": [ox, oy],
                        "size": span_font_size(span, line),
                        "color": span.get("color", 0),
                        "font": span.get("font", ""),
                        "flags": int(span.get("flags") or 0),
                    })
    return spans


def shifted_span(edit: dict, sp: dict, span_idx: int,
                 overlay_idx: int | None = None) -> dict:
    """Return *sp* moved to the area's destination rect (for hit-testing)."""
    dx, dy = area_move_delta(edit)
    bb = sp["bbox"]
    ox, oy = sp.get("origin") or [bb[0], bb[3]]
    out = {
        "text": sp.get("text", ""),
        "bbox": [bb[0] + dx, bb[1] + dy, bb[2] + dx, bb[3] + dy],
        "origin": [ox + dx, oy + dy],
        "size": sp.get("size", 12),
        "color": sp.get("color", 0),
        "font": sp.get("font", ""),
        "flags": int(sp.get("flags") or 0),
        "_area_move_span_idx": span_idx,
    }
    if overlay_idx is not None:
        out["_area_move_overlay_idx"] = overlay_idx
    return out


def create_area_move_edit(page, page_idx: int, rect) -> dict:
    """Build a pending *area_move* edit; text stays editable when possible."""
    import fitz

    fill = sample_background_fitz(page, rect)
    text_spans = extract_text_spans_in_rect(page, rect)
    r = [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]
    edit: dict = {
        "type": "area_move",
        "page": page_idx,
        "src_rect": list(r),
        "dst_rect": list(r),
        "bg_fill": fill,
        "text_spans": text_spans,
    }
    if not text_spans:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
        fd, path = tempfile.mkstemp(suffix=".png", prefix="pdfapps_area_")
        os.close(fd)
        pix.save(path)
        edit["_pixmap_path"] = path
    return edit


def apply_area_move(page, edit: dict) -> None:
    """Redact the source region and stamp text (or a pixmap fallback) at *dst*."""
    import fitz

    src = fitz.Rect(edit["src_rect"])
    dst = fitz.Rect(edit.get("dst_rect") or edit["src_rect"])
    dx, dy = area_move_delta(edit)
    fill = edit.get("bg_fill", (1.0, 1.0, 1.0))
    text_spans = edit.get("text_spans") or []

    page.add_redact_annot(src, fill=fill)
    page.apply_redactions()

    if text_spans:
        for sp in text_spans:
            txt = (sp.get("text") or "").strip()
            if not txt:
                continue
            orig = sp.get("origin") or sp["bbox"][:2]
            pt = fitz.Point(float(orig[0]) + dx, float(orig[1]) + dy)
            stub = {
                "size": sp.get("size", 12),
                "font": sp.get("font", ""),
                "color": sp.get("color", 0),
                "flags": sp.get("flags", 0),
            }
            insert_multiline_text(
                page, pt, sp.get("text", ""),
                fontsize=float(span_font_size(stub)),
                fontname=span_fontname_pdf(stub),
                color=span_color_pdf(stub),
            )
        return

    path = edit.get("_pixmap_path", "")
    if path and os.path.isfile(path):
        page.insert_image(dst, filename=path)


def cleanup_area_move(edit: dict) -> None:
    path = edit.get("_pixmap_path")
    if path and os.path.isfile(path):
        with contextlib.suppress(OSError):
            os.unlink(path)
