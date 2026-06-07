"""Helpers to inherit font size, family, and colour from PDF text spans."""

from __future__ import annotations


def _span_is_bold(span: dict) -> bool:
    flags = int(span.get("flags") or 0)
    fname = (span.get("font", "") or "").lower()
    return bool(flags & 16) or any(x in fname for x in ("bold", "black", "heavy", "semibold"))


def _span_is_italic(span: dict) -> bool:
    flags = int(span.get("flags") or 0)
    fname = (span.get("font", "") or "").lower()
    return bool(flags & 2) or any(x in fname for x in ("italic", "oblique"))


def _span_is_serif(span: dict) -> bool:
    flags = int(span.get("flags") or 0)
    fname = (span.get("font", "") or "").lower()
    return bool(flags & 4) or any(x in fname for x in ("times", "serif", "roman"))


def _span_is_mono(span: dict) -> bool:
    flags = int(span.get("flags") or 0)
    fname = (span.get("font", "") or "").lower()
    return bool(flags & 8) or any(x in fname for x in ("mono", "courier", "consol", "code"))


def span_font_size(span: dict, line: dict | None = None) -> float:
    """Return the span's font size in PDF points."""
    size = float(span.get("size") or 0)
    if size >= 4.0:
        return size
    if line is not None:
        import fitz
        lh = fitz.Rect(line["bbox"]).height
        if lh > 0:
            return max(4.0, min(lh * 0.78, 48.0))
    bb = span.get("bbox") or (0, 0, 0, 0)
    bbox_h = float(bb[3]) - float(bb[1])
    if bbox_h > 0:
        return max(4.0, min(bbox_h * 0.72, 48.0))
    return 12.0


def _same_line(lb, click_y: float) -> bool:
    import fitz
    line = fitz.Rect(lb)
    return line.y0 - 3 <= click_y <= line.y1 + 3


def left_neighbour_span(page, pdf_pt, max_gap: float = 400.0):
    """Span immediately to the left on the same line (best style reference)."""
    import fitz

    click = fitz.Point(pdf_pt.x, pdf_pt.y)
    best, best_line, best_gap = None, None, float("inf")
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            if not _same_line(line["bbox"], click.y):
                continue
            for span in line.get("spans", []):
                if not (span.get("text") or "").strip():
                    continue
                bbox = fitz.Rect(span["bbox"])
                if bbox.x1 <= click.x + 2:
                    gap = click.x - bbox.x1
                    if 0 <= gap < best_gap:
                        best_gap = gap
                        best = span
                        best_line = line
    if best is not None and best_gap <= max_gap:
        return best, best_line
    return None, None


def nearest_span_for_insert(page, pdf_pt, max_dist: float = 2500.0):
    """Find the best neighbour span when inserting text in empty space."""
    import fitz

    click = fitz.Point(pdf_pt.x, pdf_pt.y)
    best_span, best_line, best_score = None, None, float("inf")
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            lb = fitz.Rect(line["bbox"])
            same_line = _same_line(line["bbox"], click.y)
            for span in line.get("spans", []):
                if not (span.get("text") or "").strip():
                    continue
                bbox = fitz.Rect(span["bbox"])
                if bbox.contains(click):
                    return span, line
                cx = max(bbox.x0, min(click.x, bbox.x1))
                cy = max(bbox.y0, min(click.y, bbox.y1))
                dist = ((click.x - cx) ** 2 + (click.y - cy) ** 2) ** 0.5
                if dist > max_dist:
                    continue
                score = dist if same_line else dist + 1500.0
                if score < best_score:
                    best_score = score
                    best_span, best_line = span, line
    return best_span, best_line


def neighbour_span_for_insert(page, pdf_pt):
    """Prefer the span directly beside the click, else nearest on the line."""
    left, line = left_neighbour_span(page, pdf_pt)
    if left is not None:
        return left, line
    return nearest_span_for_insert(page, pdf_pt)


def style_from_span(span: dict, line: dict | None, click_x: float | None = None) -> dict:
    """Copy full text styling from an existing PDF span."""
    import fitz

    ox, oy = span_baseline(span)
    x = float(click_x) if click_x is not None else ox
    return {
        "size": span_font_size(span, line),
        "color": span.get("color", 0),
        "color_pdf": span_color_pdf(span),
        "font": span.get("font", ""),
        "flags": int(span.get("flags") or 0),
        "point": fitz.Point(x, oy),
    }


def insert_style_from_neighbour(page, pdf_pt, fallback_size: float = 12.0) -> dict:
    """Build size/colour/font/baseline for a new text insertion."""
    import fitz

    near, line = neighbour_span_for_insert(page, pdf_pt)
    if near:
        return style_from_span(near, line, click_x=pdf_pt.x)
    return {
        "size": fallback_size,
        "color": 0,
        "color_pdf": (0.0, 0.0, 0.0),
        "font": "",
        "flags": 0,
        "point": fitz.Point(pdf_pt.x, pdf_pt.y),
    }


def span_color_int(span: dict) -> tuple[int, int, int]:
    c = span.get("color", 0)
    if isinstance(c, int):
        return (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return int(float(c[0]) * 255), int(float(c[1]) * 255), int(float(c[2]) * 255)
    return 0, 0, 0


def span_color_pdf(span_or_edit: dict) -> tuple[float, float, float]:
    if "color_pdf" in span_or_edit:
        cp = span_or_edit["color_pdf"]
        return float(cp[0]), float(cp[1]), float(cp[2])
    c = span_or_edit.get("color", 0)
    if isinstance(c, int):
        return ((c >> 16) & 0xFF) / 255, ((c >> 8) & 0xFF) / 255, (c & 0xFF) / 255
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        return tuple(float(v) for v in c[:3])
    return 0.0, 0.0, 0.0


def span_font_family(span: dict) -> str:
    if _span_is_serif(span):
        return "Times New Roman"
    if _span_is_mono(span):
        return "Consolas"
    return "Helvetica"


def span_fontname_pdf(span_or_edit: dict) -> str:
    bold = _span_is_bold(span_or_edit)
    italic = _span_is_italic(span_or_edit)
    if _span_is_serif(span_or_edit):
        if bold and italic:
            return "tibi"
        if bold:
            return "tibo"
        if italic:
            return "tiit"
        return "tiro"
    if _span_is_mono(span_or_edit):
        if bold and italic:
            return "cobi"
        if bold:
            return "cobo"
        if italic:
            return "coit"
        return "cour"
    if bold and italic:
        return "hebi"
    if bold:
        return "hebo"
    if italic:
        return "heit"
    return "helv"


def span_baseline(span: dict) -> tuple[float, float]:
    bb = span.get("bbox") or (0, 0, 0, 0)
    origin = span.get("origin")
    if origin and len(origin) >= 2:
        return float(origin[0]), float(origin[1])
    return float(bb[0]), float(bb[3])


def qfont_from_span(span: dict, zoom: float = 1.0, line: dict | None = None):
    from PySide6.QtGui import QFont

    fnt = QFont(span_font_family(span))
    fnt.setPointSizeF(max(4.0, span_font_size(span, line) * zoom))
    if _span_is_bold(span):
        fnt.setBold(True)
    if _span_is_italic(span):
        fnt.setItalic(True)
    return fnt


def edit_style_from_span(span: dict) -> dict:
    """Build a pending text_edit dict with inherited span styling."""
    bb = span["bbox"]
    ox, oy = span_baseline(span)
    return {
        "type": "text_edit",
        "bbox": list(bb),
        "old_text": span.get("text", ""),
        "size": span_font_size(span),
        "color": span.get("color", 0),
        "font": span.get("font", ""),
        "flags": int(span.get("flags") or 0),
        "origin": [ox, oy],
    }


def line_bbox_for_span(page, span) -> list[float]:
    """Return the full PDF line bbox that contains ``span``."""
    import fitz

    sb = fitz.Rect(span["bbox"])
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for s in line.get("spans", []):
                if fitz.Rect(s["bbox"]).intersects(sb):
                    lb = fitz.Rect(line["bbox"])
                    return [lb.x0, lb.y0, lb.x1, lb.y1]
    return [sb.x0, sb.y0, sb.x1, sb.y1]


def sample_background_fitz(page, bbox, expand: float = 4.0) -> tuple[float, float, float]:
    """Sample PDF background colour around a text bbox (RGB 0–1)."""
    import fitz

    r = fitz.Rect(bbox)
    if r.is_empty:
        return (1.0, 1.0, 1.0)
    page_rect = page.rect
    mid_y = (r.y0 + r.y1) / 2.0
    probes = [
        fitz.Point(max(page_rect.x0 + 1, r.x0 - expand), mid_y),
        fitz.Point(min(page_rect.x1 - 1, r.x1 + expand), mid_y),
        fitz.Point(r.x0 + r.width * 0.15, max(page_rect.y0 + 1, r.y0 - expand)),
        fitz.Point(r.x0 + r.width * 0.15, min(page_rect.y1 - 1, r.y1 + expand)),
    ]
    mat = fitz.Matrix(3, 3)
    colors: list[tuple[float, float, float]] = []
    for pt in probes:
        clip = fitz.Rect(pt.x - 1.5, pt.y - 1.5, pt.x + 1.5, pt.y + 1.5) & page_rect
        if clip.is_empty:
            continue
        try:
            pix = page.get_pixmap(matrix=mat, clip=clip, annots=False)
        except Exception:
            continue
        if pix.samples:
            s = pix.samples
            colors.append((s[0] / 255.0, s[1] / 255.0, s[2] / 255.0))
    if colors:
        n = len(colors)
        return (
            sum(c[0] for c in colors) / n,
            sum(c[1] for c in colors) / n,
            sum(c[2] for c in colors) / n,
        )
    strip = fitz.Rect(r.x0, max(page_rect.y0, r.y0 - expand), r.x1, r.y0) & page_rect
    if not strip.is_empty:
        try:
            pix = page.get_pixmap(matrix=mat, clip=strip, annots=False)
            n = pix.width * pix.height
            if n:
                step = pix.n
                rs = gs = bs = 0
                for i in range(0, len(pix.samples), step):
                    rs += pix.samples[i]
                    gs += pix.samples[i + 1]
                    bs += pix.samples[i + 2]
                return (rs / n / 255, gs / n / 255, bs / n / 255)
        except Exception:
            pass
    return (1.0, 1.0, 1.0)


def redact_fill_for_edit(edit: dict) -> tuple[float, float, float]:
    """Return the redaction fill colour for a text_edit (stored or white)."""
    bg = edit.get("bg_fill")
    if bg and len(bg) >= 3:
        return float(bg[0]), float(bg[1]), float(bg[2])
    return (1.0, 1.0, 1.0)


def insert_multiline_text(page, point, text: str, *, fontsize: float,
                          fontname: str, color) -> None:
    """Insert *text* at *point*, honouring newline characters."""
    import fitz

    if not text:
        return
    px = float(point.x) if hasattr(point, "x") else float(point[0])
    py = float(point.y) if hasattr(point, "y") else float(point[1])
    lines = text.split("\n")
    if len(lines) == 1:
        page.insert_text(
            fitz.Point(px, py), text,
            fontsize=float(fontsize), fontname=fontname, color=color,
        )
        return
    lh = max(float(fontsize) * 1.15, float(fontsize) + 2.0)
    for i, line in enumerate(lines):
        page.insert_text(
            fitz.Point(px, py + i * lh), line,
            fontsize=float(fontsize), fontname=fontname, color=color,
        )
