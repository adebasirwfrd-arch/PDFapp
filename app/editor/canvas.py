"""PDFApps – PdfEditCanvas: continuous-scroll visual PDF edit canvas."""

import contextlib
import os
from functools import lru_cache

from PySide6.QtCore import Qt, Signal, QRect, QPoint, QObject, QRunnable, QThreadPool, QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QSizePolicy, QPlainTextEdit, QFrame

from app.constants import ACCENT, BG_INNER, TEXT_SEC, _LN, _LI
from app.editor.area_move import area_move_delta, shifted_span
from app.editor.text_snap import (
    clone_overlay_edit, collect_snap_targets, move_overlay, overlay_anchor,
    overlay_pdf_bbox, snap_point,
)
from app.editor.text_style import (
    edit_style_from_span, line_bbox_for_span, qfont_from_span,
    redact_fill_for_edit, sample_background_fitz,
    span_color_int, span_font_size,
)
from app.i18n import t

_NOTE_ICON_SIZE = 22
_PAGE_GAP = 4
_BUFFER_PGS = 2
_MAX_THREADS = 2

_ICON_CURSORS: dict = {}


@lru_cache(maxsize=64)
def _load_overlay_pixmap(path: str, _mtime: float) -> QPixmap:
    """LRU-cached QPixmap loader for overlay image/signature stamps.

    The previous implementation built a fresh ``QPixmap(path)`` on every
    ``paintEvent`` — once per overlay — which became the dominant cost
    of scrolling a document containing dozens of inserted images. The
    ``_mtime`` parameter (which the caller passes verbatim) participates
    in the cache key so the cache auto-invalidates when the underlying
    file is rewritten (e.g. signature regenerated on disk).
    """
    return QPixmap(path)


def _get_icon_cursor(icon_name: str, hx: int, hy: int,
                     size: int = 28, rotate: float = 0.0):
    """Cached QCursor built from a qtawesome icon with a white halo so the
    cursor stays visible on both light and dark PDF backgrounds."""
    key = (icon_name, hx, hy, size, rotate)
    cur = _ICON_CURSORS.get(key)
    if cur is not None:
        return cur
    from PySide6.QtGui import QCursor, QPixmap, QPainter
    import qtawesome as qta
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    pad = (size - 24) // 2
    extra = {"rotated": rotate} if rotate else {}
    halo = qta.icon(icon_name, color="white", **extra).pixmap(24, 24)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        p.drawPixmap(pad + dx, pad + dy, halo)
    body = qta.icon(icon_name, color="black", **extra).pixmap(24, 24)
    p.drawPixmap(pad, pad, body)
    p.end()
    cur = QCursor(pix, hx, hy)
    _ICON_CURSORS[key] = cur
    return cur


class _EditRenderSignals(QObject):
    page_ready = Signal(int, int, object)  # gen, idx, QPixmap


class _EditPageJob(QRunnable):
    """Renders a single page in a background thread."""

    def __init__(self, path: str, idx: int, zoom: float, dpr: float,
                 gen: int, signals: _EditRenderSignals, password: str = ""):
        super().__init__()
        self._path = path
        self._idx = idx
        self._zoom = zoom
        self._dpr = dpr
        self._gen = gen
        self._password = password
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        doc = None
        try:
            import fitz
            from PySide6.QtGui import QPixmap as QP, QImage
            doc = fitz.open(self._path)
            if doc.needs_pass and self._password:
                doc.authenticate(self._password)
            page = doc[self._idx]
            rz = self._zoom * self._dpr
            pix = page.get_pixmap(matrix=fitz.Matrix(rz, rz), annots=False)
            img = pix.tobytes("png")
            qp = QP()
            if not qp.loadFromData(img):
                # samples_mv is a memoryview backed by the fitz Pixmap,
                # which is backed by the open Document. Force an eager
                # copy via QImage.copy() before letting the doc fall
                # out of scope in the finally clause — otherwise the
                # underlying buffer can be freed mid-QImage-blit.
                qi = QImage(pix.samples_mv, pix.width, pix.height,
                            pix.stride, QImage.Format.Format_RGB888)
                qp = QP.fromImage(qi.copy())
            qp.setDevicePixelRatio(self._dpr)
            self.signals.page_ready.emit(self._gen, self._idx, qp)
        except Exception:
            import traceback, logging
            logging.error("Edit page render failed (idx=%d):\n%s",
                          self._idx, traceback.format_exc())
        finally:
            if doc is not None:
                try: doc.close()
                except Exception: pass


class PdfEditCanvas(QWidget):
    rect_selected   = Signal(int, object)        # (page_idx, fitz.Rect)
    point_clicked   = Signal(int, object)        # (page_idx, fitz.Point)
    stroke_finished = Signal(int, object)        # (page_idx, list[fitz.Point])
    note_deleted    = Signal(dict)
    zoom_changed    = Signal(int)
    text_edit_committed = Signal(int, dict)      # (page_idx, edit_dict)
    text_inserted       = Signal(int, dict)      # (page_idx, edit_dict)
    overlay_moved       = Signal(int, dict, dict)  # (idx, after, before)

    def __init__(self):
        super().__init__()
        self._doc         = None
        self._path        = ""
        self._password    = ""
        self._page_idx    = 0   # kept for compatibility (current page indicator)
        self._zoom        = 1.0
        self._zoom_factor = 1.0
        self._base_avail  = 300
        self._page_pixmaps: list = []   # list of QPixmap|None, one per page
        self._page_offsets = []   # list of (y_offset, width, height) per page
        self._gen         = 0
        self._pending: set[int] = set()
        self._render_signals = _EditRenderSignals()
        self._render_signals.page_ready.connect(self._on_page_ready)
        self._drag_start  = None
        self._drag_rect   = None
        self._overlays    = []    # ALL overlays (all pages)
        self._select_mode = False
        self._area_move_mode = False
        self._draw_mode   = False
        self._text_mode   = False
        self._move_text_enabled = False
        self._draw_color  = (1.0, 0.0, 0.0)
        self._draw_width  = 2
        self._current_stroke = None   # list of (sx, sy) screen coords while drawing
        self._stroke_page = -1
        self._open_note   = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(300, 400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._bg_color = BG_INNER
        # Inline text editor (overlayed on span for real-time edit)
        self._inline_edit = QPlainTextEdit(self)
        self._inline_edit.setFrameShape(QFrame.Shape.NoFrame)
        self._inline_edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inline_edit.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inline_edit.setTabChangesFocus(False)
        self._inline_edit.hide()
        self._inline_edit.installEventFilter(self)
        self._inline_span = None
        self._inline_page_idx = -1
        self._inline_original = ""
        self._inline_mode = None  # "edit" | "insert"
        self._inline_insert_point = None  # (pdf_x, pdf_y) for insert mode
        self._inline_insert_size = 12
        self._inline_insert_color = (0, 0, 0)
        self._inline_insert_font = ""
        self._inline_insert_flags = 0
        self._inline_bg_fill = (1.0, 1.0, 1.0)
        self._inline_cover_bbox = None  # PDF coords: full line to hide while editing
        self._overlay_drag_idx = -1
        self._overlay_drag_page = -1
        self._overlay_drag_offset = (0.0, 0.0)  # mouse − anchor at press (PDF pts)
        self._overlay_drag_before: dict | None = None
        self._snap_guide_x: float | None = None
        self._snap_guide_y: float | None = None
        self._grid_snap_enabled = False
        self._grid_size = 5.0
        self._text_hit_margin = 8
        self._area_hit_margin = 14
        self._scroll_area = None
        self._inline_edit.textChanged.connect(self._on_inline_text_changed)

    def set_dark_mode(self, dark: bool):
        self._bg_color = BG_INNER if dark else _LN
        self.update()

    def set_select_mode(self, active: bool):
        self._select_mode = active

    def set_area_move_mode(self, active: bool):
        self._area_move_mode = active
        if active:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def set_text_mode(self, active: bool):
        """Text mode uses IBeamCursor consistently (edit existing or add new)."""
        self._text_mode = active
        if active:
            self.setCursor(Qt.CursorShape.IBeamCursor)

    def set_move_text_enabled(self, active: bool):
        self._move_text_enabled = active

    def set_grid_snap(self, enabled: bool, grid_size: float = 5.0):
        self._grid_snap_enabled = enabled
        self._grid_size = max(1.0, float(grid_size))

    def set_draw_mode(self, active: bool, color=None, width=None):
        self._draw_mode = active
        if color is not None:
            self._draw_color = color
        if width is not None:
            self._draw_width = max(1, int(width))
        if active:
            self.setCursor(_get_icon_cursor("fa5s.pencil-alt", 14, 2, rotate=135))
        else:
            self._current_stroke = None
            self._stroke_page = -1
            self.update()

    def set_scroll_area(self, scroll_area):
        """Keep a ref so we can pause scrolling while dragging overlays."""
        self._scroll_area = scroll_area

    def cancel_overlay_drag(self):
        """Drop an in-progress overlay drag without recording undo."""
        self._finish_overlay_drag(emit_move=False)

    def _finish_overlay_drag(self, emit_move: bool = True):
        if self._overlay_drag_idx < 0:
            self._set_scroll_locked(False)
            return
        idx = self._overlay_drag_idx
        before = self._overlay_drag_before
        moved = (
            clone_overlay_edit(self._overlays[idx])
            if idx < len(self._overlays) else None
        )
        self._overlay_drag_idx = -1
        self._overlay_drag_page = -1
        self._overlay_drag_before = None
        self._snap_guide_x = self._snap_guide_y = None
        self._set_scroll_locked(False)
        if self._move_text_enabled and self._text_mode:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif self._move_text_enabled or self._area_move_mode:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        if emit_move and moved is not None and before is not None:
            self.overlay_moved.emit(idx, moved, before)
        self.update()

    def set_overlays(self, overlays: list):
        self._overlays = overlays
        self._open_note = None
        self.update()

    def load(self, path: str, password: str = ""):
        import fitz
        if self._doc: self._doc.close()
        self._doc = fitz.open(path)
        if self._doc.needs_pass and password:
            self._doc.authenticate(password)
        self._path = path
        self._password = password
        self._page_idx = 0
        self._zoom_factor = 1.0
        self._gen += 1
        self._pending.clear()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._layout_and_schedule)

    def zoom_in(self):
        self._zoom_factor = min(4.0, round(self._zoom_factor * 1.25, 4))
        self._invalidate_and_relayout()

    def zoom_out(self):
        self._zoom_factor = max(0.2, round(self._zoom_factor / 1.25, 4))
        self._invalidate_and_relayout()

    def zoom_reset(self):
        self._zoom_factor = 1.0
        self._invalidate_and_relayout()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if e.angleDelta().y() > 0: self.zoom_in()
            else: self.zoom_out()
            e.accept()
        else:
            super().wheelEvent(e)

    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    def set_page(self, idx: int):
        """Scroll to page (called by tab navigation arrows)."""
        if self._doc and 0 <= idx < self._doc.page_count:
            self._page_idx = idx

    def scroll_to_page(self, idx: int) -> int:
        """Return Y offset for a given page index."""
        if 0 <= idx < len(self._page_offsets):
            return self._page_offsets[idx][0]
        return 0

    def page_at_y(self, y: int) -> int:
        """Return which page index is at scroll position y."""
        for i, (yo, w, h) in enumerate(self._page_offsets):
            if y < yo + h + _PAGE_GAP:
                return i
        return max(0, len(self._page_offsets) - 1)

    def get_span_at(self, page_idx, pdf_pt, max_dist: float = 30.0):
        """Returns the closest fitz span to pdf_pt on the given page.

        `max_dist` is in PDF points. A hit inside a bbox returns immediately;
        otherwise the closest span within `max_dist` (if any) is returned.
        Pending area-move overlays are checked first at their destination.
        """
        if not self._doc:
            return None
        import fitz
        click = fitz.Point(pdf_pt.x, pdf_pt.y)
        for ov_idx, e in enumerate(self._overlays):
            if e.get("type") != "area_move" or e.get("page") != page_idx:
                continue
            hit = self._span_in_area_move(e, click, max_dist, ov_idx)
            if hit is not None:
                return hit
        page = self._doc[page_idx]
        found, best_dist = None, float(max_dist)
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if self._span_hidden_by_area_move(page_idx, span):
                        continue
                    bbox = fitz.Rect(span["bbox"])
                    if bbox.contains(click):
                        return span
                    cx = max(bbox.x0, min(click.x, bbox.x1))
                    cy = max(bbox.y0, min(click.y, bbox.y1))
                    dist = ((click.x - cx) ** 2 + (click.y - cy) ** 2) ** 0.5
                    if dist < best_dist:
                        best_dist = dist
                        found = span
        return found

    def _span_hidden_by_area_move(self, page_idx: int, span: dict) -> bool:
        import fitz
        sb = fitz.Rect(span["bbox"])
        for e in self._overlays:
            if e.get("type") != "area_move" or e.get("page") != page_idx:
                continue
            src = fitz.Rect(e.get("src_rect") or (0, 0, 0, 0))
            if sb.intersects(src):
                return True
        return False

    def _span_in_area_move(self, edit: dict, click, max_dist: float, ov_idx: int):
        import fitz
        found, best_dist = None, float(max_dist)
        for j, sp in enumerate(edit.get("text_spans") or []):
            synth = shifted_span(edit, sp, j, overlay_idx=ov_idx)
            bbox = fitz.Rect(synth["bbox"])
            if bbox.contains(click):
                return synth
            cx = max(bbox.x0, min(click.x, bbox.x1))
            cy = max(bbox.y0, min(click.y, bbox.y1))
            dist = ((click.x - cx) ** 2 + (click.y - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                found = synth
        return found

    # ── inline text edit ────────────────────────────────────────────────

    def begin_inline_text_edit(self, span: dict, page_idx: int):
        """Show a QLineEdit positioned over the span, pre-filled and focused."""
        if self._inline_edit.isVisible():
            self._commit_inline()
        self._inline_mode = "edit"
        self._inline_span = dict(span)
        self._inline_page_idx = page_idx
        self._inline_original = span.get("text", "")
        if self._doc and 0 <= page_idx < self._doc.page_count:
            page = self._doc[page_idx]
            if span.get("_area_move_overlay_idx") is not None:
                self._inline_cover_bbox = list(span["bbox"])
                self._inline_bg_fill = sample_background_fitz(page, span["bbox"])
            else:
                self._inline_cover_bbox = line_bbox_for_span(page, span)
                self._inline_bg_fill = sample_background_fitz(page, self._inline_cover_bbox)
        else:
            self._inline_cover_bbox = list(span["bbox"])
            self._inline_bg_fill = (1.0, 1.0, 1.0)
        self._inline_edit.setPlainText(self._inline_original)
        self._style_inline_edit(span)
        self._reposition_inline()
        self._inline_edit.show()
        self._inline_edit.raise_()
        self._inline_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._inline_edit.selectAll()
        self.update()

    def begin_inline_text_insert(self, page_idx: int, pdf_point, size: float,
                                 color: tuple, font: str = "", flags: int = 0):
        """Show an empty QLineEdit at the click point for real-time text insertion."""
        if self._inline_edit.isVisible():
            self._commit_inline()
        self._inline_mode = "insert"
        self._inline_span = None
        self._inline_page_idx = page_idx
        self._inline_original = ""
        self._inline_insert_point = (float(pdf_point.x), float(pdf_point.y))
        self._inline_insert_size = float(size)
        self._inline_insert_color = tuple(color)
        self._inline_insert_font = font or ""
        self._inline_insert_flags = int(flags or 0)
        self._inline_edit.setPlainText("")
        self._style_inline_insert()
        self._reposition_inline()
        self._inline_edit.show()
        self._inline_edit.raise_()
        self._inline_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _style_inline_insert(self):
        span_stub = {
            "size": self._inline_insert_size,
            "font": self._inline_insert_font,
            "color": self._inline_insert_color,
            "flags": self._inline_insert_flags,
        }
        fnt = qfont_from_span(span_stub, self._zoom)
        self._inline_edit.setFont(fnt)
        r, g, b = span_color_int(span_stub)
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self._inline_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; color: {hex_color};"
            f" border: none; padding: 0 2px; margin: 0; }}")

    def _style_inline_edit(self, span: dict):
        fnt = qfont_from_span(span, self._zoom)
        self._inline_edit.setFont(fnt)
        r, g, b = span_color_int(span)
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        bg = self._inline_bg_fill
        bg_hex = f"#{int(bg[0]*255):02x}{int(bg[1]*255):02x}{int(bg[2]*255):02x}"
        self._inline_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: {bg_hex}; color: {hex_color};"
            f" border: none; padding: 0 2px; margin: 0; }}")

    def _inline_plain_text(self) -> str:
        return self._inline_edit.toPlainText()

    def _inline_doc_size(self) -> tuple[int, int]:
        layout = self._inline_edit.document().documentLayout()
        size = layout.documentSize()
        return max(1, int(size.width()) + 12), max(1, int(size.height()) + 8)

    def _inline_editor_pdf_rect(self) -> list[float]:
        if self._inline_page_idx < 0 or self._inline_page_idx >= len(self._page_offsets):
            return [0, 0, 0, 0]
        z = self._zoom or 1.0
        yo = self._page_offsets[self._inline_page_idx][0]
        qr = self._inline_edit.geometry()
        ly = (qr.top() - yo) / z
        return [qr.left() / z, ly, qr.right() / z, ly + qr.height() / z]

    @staticmethod
    def _draw_multiline_baseline(p, x: int, y: int, text: str):
        fm = p.fontMetrics()
        lh = fm.lineSpacing()
        for i, line in enumerate(text.split("\n")):
            p.drawText(x, y + i * lh, line)

    def _on_inline_text_changed(self, _text: str = ""):
        if self._inline_edit.isVisible():
            self._reposition_inline()
            self.update()

    def _reposition_inline(self):
        if self._inline_mode is None:
            return
        if self._inline_page_idx < 0 or self._inline_page_idx >= len(self._page_offsets):
            return
        z = self._zoom
        yo = self._page_offsets[self._inline_page_idx][0]
        if self._inline_mode == "edit" and self._inline_span is not None:
            cover = self._inline_cover_bbox or self._inline_span["bbox"]
            bb = cover
            x = int(bb[0] * z) - 1
            y = yo + int(bb[1] * z) - 1
            line_w = max(40, int((bb[2] - bb[0]) * z) + 4)
            doc_w, doc_h = self._inline_doc_size()
            w = max(line_w, doc_w, 120)
            h = max(20, doc_h, int((bb[3] - bb[1]) * z) + 2)
            self._inline_edit.setGeometry(x, y, w, h)
            self._style_inline_edit(self._inline_span)
        elif self._inline_mode == "insert" and self._inline_insert_point is not None:
            px, py = self._inline_insert_point
            size = self._inline_insert_size
            x = int(px * z) - 2
            y = yo + int((py - size * 0.85) * z) - 2
            doc_w, doc_h = self._inline_doc_size()
            w = max(120, doc_w, int(size * z * 8))
            h = max(20, doc_h, int(size * z * 1.4) + 4)
            self._inline_edit.setGeometry(x, y, w, h)
            self._style_inline_insert()

    def _commit_inline(self):
        if self._inline_mode is None or not self._inline_edit.isVisible():
            return
        editor_rect = self._inline_editor_pdf_rect()
        new_text = self._inline_plain_text()
        mode = self._inline_mode
        page_idx = self._inline_page_idx
        span = self._inline_span
        ipoint = self._inline_insert_point
        isize = self._inline_insert_size
        icolor = self._inline_insert_color
        ifont = self._inline_insert_font
        iflags = self._inline_insert_flags
        original = self._inline_original
        self._inline_edit.hide()
        self._inline_mode = None
        self._inline_span = None
        self._inline_page_idx = -1
        self._inline_insert_point = None
        self._inline_cover_bbox = None
        # LOW: reset insert-mode style state on commit so the next
        # insert (which begins fresh) doesn't inherit the previous
        # font/size/colour if begin_inline_text_insert is somehow
        # called without re-setting them.
        self._inline_insert_font = ""
        self._inline_insert_size = 12
        self._inline_insert_color = (0, 0, 0)
        self._inline_insert_flags = 0
        self._inline_original = ""
        if mode == "edit" and span is not None:
            if new_text == original:
                self.update()
                return
            ov_idx = span.get("_area_move_overlay_idx")
            if ov_idx is not None and 0 <= ov_idx < len(self._overlays):
                sp_idx = int(span.get("_area_move_span_idx", 0))
                e = self._overlays[ov_idx]
                spans = e.get("text_spans") or []
                if 0 <= sp_idx < len(spans):
                    spans[sp_idx]["text"] = new_text
                    self.update()
                    return
            edit = edit_style_from_span(span)
            edit["page"] = page_idx
            edit["new_text"] = new_text
            ob = edit.get("bbox") or list(span["bbox"])
            edit["bbox"] = [
                min(ob[0], editor_rect[0]), min(ob[1], editor_rect[1]),
                max(ob[2], editor_rect[2]), max(ob[3], editor_rect[3]),
            ]
            if self._inline_bg_fill:
                edit["bg_fill"] = list(self._inline_bg_fill)
            elif self._doc and 0 <= page_idx < self._doc.page_count:
                edit["bg_fill"] = list(
                    sample_background_fitz(self._doc[page_idx], span["bbox"]))
            self.text_edit_committed.emit(page_idx, edit)
        elif mode == "insert" and ipoint is not None:
            if not new_text.strip():
                return
            import fitz
            edit = {
                "type": "text", "page": page_idx,
                "point": fitz.Point(ipoint[0], ipoint[1]),
                "text": new_text, "size": isize,
                "color": icolor, "color_pdf": icolor,
                "font": ifont, "flags": iflags,
            }
            self.text_inserted.emit(page_idx, edit)
        self.update()

    def _cancel_inline(self):
        self._inline_edit.hide()
        self._inline_mode = None
        self._inline_span = None
        self._inline_page_idx = -1
        self._inline_insert_point = None
        self._inline_cover_bbox = None
        self._inline_insert_font = ""
        self._inline_insert_size = 12
        self._inline_insert_color = (0, 0, 0)
        self._inline_insert_flags = 0
        self._inline_original = ""
        self.update()

    def eventFilter(self, obj, event):
        if obj is self._inline_edit:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_inline()
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                        self._commit_inline()
                        return True
                    return False
            elif event.type() == QEvent.Type.FocusOut:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._commit_inline)
                return False
        return super().eventFilter(obj, event)

    def release_doc(self):
        if self._doc: self._doc.close(); self._doc = None

    def close_doc(self):
        self._cancel_inline()
        self.cancel_overlay_drag()
        self._gen += 1
        self._pending.clear()
        self.release_doc()
        self._page_pixmaps.clear()
        self._page_offsets.clear()
        self._overlays = []; self._open_note = None
        self.setMinimumSize(300, 400)
        self.setMaximumSize(16777215, 16777215)
        self.update()

    # ── DPR change handling (R8/D1) ──────────────────────────────────────
    def showEvent(self, event):
        """Re-render pages when the top-level window crosses a screen
        with a different devicePixelRatio. ``_schedule_visible`` only
        sampled the DPR at scroll/zoom time, so dragging the window from
        a 100 % monitor to a 200 % monitor left previously rendered
        pages blurry until the user changed zoom (R8/D1)."""
        super().showEvent(event)
        win = self.window().windowHandle() if self.window() else None
        if win:
            # Disconnect before reconnecting — re-show events can stack
            # the same handler multiple times.
            with contextlib.suppress(TypeError, RuntimeError):
                win.screenChanged.disconnect(self._on_screen_changed)
            win.screenChanged.connect(self._on_screen_changed)

    def _on_screen_changed(self, _screen):
        """Drop cached pixmaps and re-queue visible pages at the new DPR."""
        self._gen += 1
        self._pending.clear()
        self._page_pixmaps = [None] * len(self._page_pixmaps)
        self._schedule_visible()
        self.update()

    def on_scroll(self):
        """Called when scroll position changes — renders newly visible pages."""
        self._schedule_visible()

    def _invalidate_and_relayout(self):
        self._gen += 1
        self._pending.clear()
        self._page_pixmaps = [None] * len(self._page_pixmaps)
        self._layout_and_schedule()

    def _layout_and_schedule(self):
        """Fast layout pass — compute page dimensions only, then schedule
        background rendering for visible pages."""
        if not self._doc:
            return

        if self._zoom_factor == 1.0:
            from PySide6.QtWidgets import QScrollArea as _SA
            vp = self.parent()
            sa = vp.parent() if vp else None
            avail = sa.viewport().width() - 4 if isinstance(sa, _SA) else self.width()
            self._base_avail = max(avail, 300)

        ref_w = self._doc[0].rect.width
        self._zoom = (self._base_avail / ref_w) * self._zoom_factor

        self._page_pixmaps.clear()
        self._page_offsets.clear()
        y_off = 0
        max_w = 0
        for i in range(self._doc.page_count):
            r = self._doc[i].rect
            pw = round(r.width * self._zoom)
            ph = round(r.height * self._zoom)
            self._page_pixmaps.append(None)
            self._page_offsets.append((y_off, pw, ph))
            max_w = max(max_w, pw)
            y_off += ph + _PAGE_GAP

        total_h = y_off - _PAGE_GAP if y_off > 0 else 400
        self.setFixedSize(max(max_w, 300), max(total_h, 400))
        self.zoom_changed.emit(round(self._zoom_factor * 100))
        self.update()
        self._schedule_visible()
        if self._inline_edit.isVisible():
            self._reposition_inline()

    def _visible_range(self) -> tuple[int, int]:
        from PySide6.QtWidgets import QScrollArea as _SA
        vp = self.parent()
        sa = vp.parent() if vp else None
        n = len(self._page_offsets)
        if not isinstance(sa, _SA) or not n:
            return (0, min(n - 1, _BUFFER_PGS * 2))
        y0 = sa.verticalScrollBar().value()
        y1 = y0 + sa.viewport().height()
        first = last = 0
        found = False
        for i, (yo, pw, ph) in enumerate(self._page_offsets):
            if not found and yo + ph >= y0:
                first = i; found = True
            if yo <= y1:
                last = i
        return (max(0, first - _BUFFER_PGS), min(n - 1, last + _BUFFER_PGS))

    def _schedule_visible(self):
        if not self._page_offsets or not self._path:
            return
        first, last = self._visible_range()
        dpr = self.devicePixelRatioF() or 1.0
        gen = self._gen
        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(_MAX_THREADS)
        for i in range(first, last + 1):
            if self._page_pixmaps[i] is None and i not in self._pending:
                self._pending.add(i)
                pool.start(_EditPageJob(self._path, i, self._zoom, dpr,
                                        gen, self._render_signals,
                                        password=getattr(self, "_password", "")))

    def _on_page_ready(self, gen: int, idx: int, pixmap):
        if gen != self._gen:
            return
        self._pending.discard(idx)
        if 0 <= idx < len(self._page_pixmaps):
            self._page_pixmaps[idx] = pixmap
            self.update()

    def _page_and_local(self, sx, sy):
        """Convert screen coords to (page_index, local_x, local_y)."""
        for i, (yo, w, h) in enumerate(self._page_offsets):
            if sy < yo + h + _PAGE_GAP // 2 or i == len(self._page_offsets) - 1:
                return i, sx, sy - yo
        return 0, sx, sy

    def _to_pdf(self, page_idx, sx, sy):
        import fitz
        return fitz.Point(sx / self._zoom, sy / self._zoom)

    def _rect_to_pdf(self, page_idx, local_rect):
        import fitz
        z = self._zoom
        r = fitz.Rect(local_rect.left()/z, local_rect.top()/z,
                      local_rect.right()/z, local_rect.bottom()/z)
        # Clamp to the page bbox: cross-page drags previously mapped the
        # rect to the start page only and PyMuPDF then silently truncated
        # the off-page portion. Returning ``None`` for a degenerate
        # (zero-area / fully off-page) rect lets the caller skip it.
        if self._doc and 0 <= page_idx < self._doc.page_count:
            page_rect = self._doc[page_idx].rect
            r = r & page_rect  # intersection
            if r.is_empty or r.width < 1 or r.height < 1:
                return None
        return r

    def paintEvent(self, _):
        from PySide6.QtGui import QPainter, QColor, QPen, QFont
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._bg_color))

        if not self._page_pixmaps:
            p.setPen(QColor(TEXT_SEC))
            f = QFont(); f.setPointSize(11); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, t("edit.open_prompt"))
            p.end()
            return

        # Draw pages (or placeholder if not yet rendered)
        for i, qpix in enumerate(self._page_pixmaps):
            yo, pw, ph = self._page_offsets[i]
            if qpix is not None:
                p.drawPixmap(0, yo, qpix)
            else:
                p.fillRect(QRect(0, yo, pw, ph), QColor("#FFFFFF"))
                p.setPen(QColor(TEXT_SEC))
                f = QFont(); f.setPointSize(9); p.setFont(f)
                p.drawText(QRect(0, yo, pw, ph), Qt.AlignmentFlag.AlignCenter, f"⏳ {i+1}")
                p.setPen(QColor("#E0E0E0"))
                p.drawRect(QRect(0, yo, pw - 1, ph - 1))

        # Draw overlays
        z = self._zoom
        for ov_idx, e in enumerate(self._overlays):
            pg = e.get("page", 0)
            if pg >= len(self._page_offsets):
                continue
            yo = self._page_offsets[pg][0]
            etype = e["type"]

            if etype == "redact":
                r = e["rect"]; fill = e["fill"]
                qr = QRect(int(r.x0*z), yo+int(r.y0*z), max(1,int(r.width*z)), max(1,int(r.height*z)))
                p.fillRect(qr, QColor(int(fill[0]*255), int(fill[1]*255), int(fill[2]*255), 210))
                p.setPen(QPen(QColor("#EF4444"), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(qr)
            elif etype == "highlight":
                r = e["rect"]; c = e["color"]
                qr = QRect(int(r.x0*z), yo+int(r.y0*z), max(1,int(r.width*z)), max(1,int(r.height*z)))
                p.fillRect(qr, QColor(int(c[0]*255), int(c[1]*255), int(c[2]*255), 120))
            elif etype == "area_move":
                src = e.get("src_rect") or (0, 0, 0, 0)
                dst = e.get("dst_rect") or src
                dx, dy = area_move_delta(e)
                fill = e.get("bg_fill", (1, 1, 1))
                sr = QRect(int(src[0] * z), yo + int(src[1] * z),
                           max(1, int((src[2] - src[0]) * z)),
                           max(1, int((src[3] - src[1]) * z)))
                p.fillRect(sr, QColor(int(fill[0] * 255), int(fill[1] * 255),
                                      int(fill[2] * 255)))
                text_spans = e.get("text_spans") or []
                if text_spans:
                    for sp in text_spans:
                        span_stub = {
                            "size": sp.get("size", 12),
                            "font": sp.get("font", ""),
                            "color": sp.get("color", 0),
                            "color_pdf": sp.get("color", 0),
                            "flags": sp.get("flags", 0),
                        }
                        r_c, g_c, b_c = span_color_int(span_stub)
                        p.setPen(QColor(r_c, g_c, b_c))
                        p.setFont(qfont_from_span(span_stub, z))
                        orig = sp.get("origin") or sp["bbox"][:2]
                        p.drawText(int((orig[0] + dx) * z),
                                   yo + int((orig[1] + dy) * z),
                                   sp.get("text", ""))
                else:
                    path = e.get("_pixmap_path", "")
                    if path:
                        try:
                            mtime = os.path.getmtime(path)
                        except OSError:
                            mtime = 0.0
                        img_px = _load_overlay_pixmap(path, mtime)
                        qr = QRect(int(dst[0] * z), yo + int(dst[1] * z),
                                   max(1, int((dst[2] - dst[0]) * z)),
                                   max(1, int((dst[3] - dst[1]) * z)))
                        if not img_px.isNull():
                            p.drawPixmap(qr, img_px)
                dr = QRect(int(dst[0] * z), yo + int(dst[1] * z),
                           max(1, int((dst[2] - dst[0]) * z)),
                           max(1, int((dst[3] - dst[1]) * z)))
                p.setPen(QPen(QColor("#EF4444"), 2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(dr)
            elif etype == "text":
                pt = e["point"]
                span_stub = {
                    "size": e.get("size", 12),
                    "font": e.get("font", ""),
                    "color": e.get("color", (0, 0, 0)),
                    "color_pdf": e.get("color_pdf", e.get("color", (0, 0, 0))),
                    "flags": e.get("flags", 0),
                }
                r_c, g_c, b_c = span_color_int(span_stub)
                p.setPen(QColor(r_c, g_c, b_c))
                p.setFont(qfont_from_span(span_stub, z))
                txt = e.get("text", "")
                if "\n" in txt:
                    self._draw_multiline_baseline(
                        p, int(pt.x * z), yo + int(pt.y * z), txt)
                else:
                    p.drawText(int(pt.x * z), yo + int(pt.y * z), txt)
                if self._move_text_enabled:
                    bb = overlay_pdf_bbox(e)
                    if bb is not None:
                        qr = QRect(int(bb.x0*z), yo+int(bb.y0*z),
                                   max(1, int(bb.width*z)), max(1, int(bb.height*z)))
                        p.setPen(QPen(QColor(ACCENT), 1, Qt.PenStyle.DotLine))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRect(qr)
            elif etype in ("image", "signature"):
                r = e["rect"]
                qr = QRect(int(r.x0*z), yo+int(r.y0*z), max(1,int(r.width*z)), max(1,int(r.height*z)))
                path = e["path"]
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    mtime = 0.0
                img_px = _load_overlay_pixmap(path, mtime)
                if not img_px.isNull():
                    p.drawPixmap(qr, img_px)
                border = "#22C55E" if etype == "signature" else ACCENT
                p.setPen(QPen(QColor(border), 2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(qr)
            elif etype == "note":
                pt = e["point"]
                px, py = int(pt.x*z), yo+int(pt.y*z)
                # LOW polish: prefer the enumerate index over an O(n)
                # list.index lookup (which scaled as O(n²) when there
                # are many overlays).
                note_idx = ov_idx
                icon_r = QRect(px, py - _NOTE_ICON_SIZE, _NOTE_ICON_SIZE, _NOTE_ICON_SIZE)
                p.setBrush(QColor("#FBBF24")); p.setPen(QPen(QColor("#D97706"), 1))
                p.drawRoundedRect(icon_r, 4, 4)
                fi = QFont(); fi.setPointSize(10); fi.setBold(True); p.setFont(fi)
                p.setPen(QColor("#1C1917")); p.drawText(icon_r, Qt.AlignmentFlag.AlignCenter, "\u270e")
                if self._open_note == note_idx:
                    bx = px + _NOTE_ICON_SIZE + 6
                    by = py - _NOTE_ICON_SIZE - 4
                    ft = QFont(); ft.setPointSize(9); p.setFont(ft)
                    fm = p.fontMetrics()
                    lines = e["text"].split("\n")
                    tw = max(fm.horizontalAdvance(ln) for ln in lines) + 20
                    th = fm.height() * len(lines) + 16
                    bw, bh = max(120, min(tw, 260)), max(32, th)
                    br = QRect(bx, by, bw, bh)
                    p.setBrush(QColor(0,0,0,30)); p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(QRect(bx+2, by+2, bw, bh), 6, 6)
                    p.setBrush(QColor("#FFFDF5")); p.setPen(QPen(QColor("#D97706"), 1))
                    p.drawRoundedRect(br, 6, 6)
                    p.setPen(QColor("#000000"))
                    p.drawText(QRect(bx+10, by+8, bw-20, bh-16),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                               e["text"])
            elif etype == "draw":
                pts = e.get("points", [])
                if len(pts) >= 2:
                    col = e.get("color", (1, 0, 0))
                    w = max(1, int(e.get("width", 2)))
                    pen = QPen(QColor(int(col[0]*255), int(col[1]*255), int(col[2]*255)),
                               max(1, int(w * z)))
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
                    prev = pts[0]
                    for cur in pts[1:]:
                        p.drawLine(int(prev[0]*z), yo+int(prev[1]*z),
                                   int(cur[0]*z),  yo+int(cur[1]*z))
                        prev = cur
            elif etype == "text_edit":
                r = e["bbox"]
                qr = QRect(int(r[0]*z), yo+int(r[1]*z),
                           max(1, int((r[2]-r[0])*z)), max(1, int((r[3]-r[1])*z)))
                fill = redact_fill_for_edit(e)
                p.fillRect(qr, QColor(int(fill[0]*255), int(fill[1]*255), int(fill[2]*255)))
                new_txt = e.get("new_text", "")
                if new_txt:
                    span_stub = {
                        "size": e.get("size", 12),
                        "font": e.get("font", ""),
                        "color": e.get("color", 0),
                    }
                    p.setFont(qfont_from_span(span_stub, z))
                    r_c, g_c, b_c = span_color_int(span_stub)
                    p.setPen(QColor(r_c, g_c, b_c))
                    orig = e.get("origin") or (r[0], r[3])
                    ox, oy = int(orig[0] * z), yo + int(orig[1] * z)
                    if "\n" in new_txt:
                        self._draw_multiline_baseline(p, ox, oy, new_txt)
                    else:
                        p.drawText(ox, oy, new_txt)
                if self._move_text_enabled:
                    qr = QRect(int(r[0]*z), yo+int(r[1]*z),
                               max(1, int((r[2]-r[0])*z)), max(1, int((r[3]-r[1])*z)))
                    p.setPen(QPen(QColor(ACCENT), 1, Qt.PenStyle.DotLine))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(qr)

        # While typing: hide original glyphs under the active inline editor.
        if self._inline_edit.isVisible() and self._inline_mode == "edit":
            qr = self._inline_edit.geometry()
            fill = self._inline_bg_fill
            p.fillRect(qr, QColor(int(fill[0]*255), int(fill[1]*255), int(fill[2]*255)))

        # Magnetic snap guides while dragging text
        if self._snap_guide_x is not None or self._snap_guide_y is not None:
            pen = QPen(QColor("#06B6D4"), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            if self._overlay_drag_idx >= 0:
                pg = self._overlay_drag_page
                if 0 <= pg < len(self._page_offsets):
                    yo, pw, ph = self._page_offsets[pg]
                    if self._snap_guide_x is not None:
                        sx = int(self._snap_guide_x * z)
                        p.drawLine(sx, yo, sx, yo + ph)
                    if self._snap_guide_y is not None:
                        sy = yo + int(self._snap_guide_y * z)
                        p.drawLine(0, sy, pw, sy)

        # In-progress freehand stroke preview
        if self._draw_mode and self._current_stroke and len(self._current_stroke) >= 2:
            col = self._draw_color
            pen = QPen(QColor(int(col[0]*255), int(col[1]*255), int(col[2]*255)),
                       max(1, int(self._draw_width * self._zoom)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            prev = self._current_stroke[0]
            for cur in self._current_stroke[1:]:
                p.drawLine(int(prev[0]), int(prev[1]), int(cur[0]), int(cur[1]))
                prev = cur

        # Drag rect
        if self._drag_rect:
            if self._select_mode:
                p.setPen(QPen(QColor("#3B82F6"), 2, Qt.PenStyle.SolidLine))
                p.setBrush(QColor(59, 130, 246, 50))
            else:
                p.setPen(QPen(QColor("#EF4444"), 2, Qt.PenStyle.DashLine))
                p.setBrush(QColor(239, 68, 68, 50))
            p.drawRect(self._drag_rect)
        p.end()

    def focusOutEvent(self, event):
        self._finish_overlay_drag()
        super().focusOutEvent(event)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        if self._draw_mode and self._page_offsets:
            page_idx, _lx, _ly = self._page_and_local(pos.x(), pos.y())
            self._stroke_page = page_idx
            self._current_stroke = [(pos.x(), pos.y())]
            self.update()
            return
        if not self._inline_edit.isVisible():
            hit = self._draggable_overlay_at(pos)
            if hit >= 0:
                self._overlay_drag_idx = hit
                ov = self._overlays[hit]
                self._overlay_drag_page = ov.get("page", 0)
                _, lx, ly = self._page_and_local(pos.x(), pos.y())
                pdf_pt = self._to_pdf(self._overlay_drag_page, lx, ly)
                ax, ay = overlay_anchor(ov)
                self._overlay_drag_offset = (
                    float(pdf_pt.x) - ax, float(pdf_pt.y) - ay)
                self._overlay_drag_before = clone_overlay_edit(ov)
                self._drag_start = None
                self._drag_rect = None
                self._set_scroll_locked(True)
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.update()
                return
        self._drag_start = pos
        self._drag_rect = None

    def mouseMoveEvent(self, e):
        if self._overlay_drag_idx >= 0:
            if not (e.buttons() & Qt.MouseButton.LeftButton):
                self._finish_overlay_drag()
                return
            self._apply_overlay_drag(e.position().toPoint())
            return
        if not self._inline_edit.isVisible():
            pos = e.position().toPoint()
            if self._draggable_overlay_at(pos) >= 0:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            elif self._text_mode:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            elif self._select_mode or self._area_move_mode:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        if self._draw_mode and self._current_stroke is not None and (e.buttons() & Qt.MouseButton.LeftButton):
            pos = e.position().toPoint()
            if self._stroke_page < 0 or self._stroke_page >= len(self._page_offsets):
                return
            yo, pw, ph = self._page_offsets[self._stroke_page]
            sx = max(0, min(pos.x(), pw))
            sy = max(yo, min(pos.y(), yo + ph))
            last = self._current_stroke[-1]
            if (sx - last[0]) ** 2 + (sy - last[1]) ** 2 >= 4:
                self._current_stroke.append((sx, sy))
                self.update()
            return
        if self._drag_start and (e.buttons() & Qt.MouseButton.LeftButton):
            self._drag_rect = QRect(self._drag_start, e.position().toPoint()).normalized()
            self.update()
            return
        # Text mode keeps a constant IBeam cursor (set once in set_text_mode).

    def _note_icon_at(self, pos: QPoint) -> int:
        z = self._zoom
        margin = 10
        for i, e in enumerate(self._overlays):
            if e.get("type") != "note": continue
            pg = e.get("page", 0)
            if pg >= len(self._page_offsets): continue
            yo = self._page_offsets[pg][0]
            pt = e["point"]
            px, py = int(pt.x * z), yo + int(pt.y * z)
            hit_r = QRect(px - margin, py - _NOTE_ICON_SIZE - margin,
                          _NOTE_ICON_SIZE + margin * 2, _NOTE_ICON_SIZE + margin * 2)
            if hit_r.contains(pos):
                return i
        return -1

    def _annot_note_at(self, pos: QPoint):
        if not self._doc:
            return -1, None
        import fitz
        page_idx, lx, ly = self._page_and_local(pos.x(), pos.y())
        pdf_pt = self._to_pdf(page_idx, lx, ly)
        page = self._doc[page_idx]
        for annot in page.annots() or []:
            if annot.type[0] == fitz.PDF_ANNOT_TEXT:
                expanded = annot.rect + fitz.Rect(-10, -10, 10, 10)
                if expanded.contains(pdf_pt):
                    txt = annot.info.get("content", "") or annot.get_text() or ""
                    for i, e in enumerate(self._overlays):
                        if e.get("type") == "note" and e.get("text", "").strip() == txt.strip():
                            return i, txt.strip()
                    if txt.strip():
                        pt = fitz.Point(annot.rect.x0, annot.rect.y0 + annot.rect.height)
                        self._overlays.append({
                            "type": "note", "page": page_idx,
                            "point": pt, "text": txt.strip(),
                            "_existing": True,
                            "_annot_type": annot.type[0],
                            "_annot_bbox": [annot.rect.x0, annot.rect.y0,
                                            annot.rect.x1, annot.rect.y1],
                        })
                        return len(self._overlays) - 1, txt.strip()
        return -1, None

    def _draggable_overlay_types(self) -> tuple[str, ...]:
        types: list[str] = ["area_move"]
        if self._move_text_enabled:
            types.extend(["text", "text_edit"])
        return tuple(types)

    def _overlay_hit_margin(self, etype: str) -> int:
        return self._area_hit_margin if etype == "area_move" else self._text_hit_margin

    def _draggable_overlay_at(self, pos: QPoint) -> int:
        if not self._doc or not self._page_offsets:
            return -1
        types = self._draggable_overlay_types()
        if not types:
            return -1
        page_idx, lx, ly = self._page_and_local(pos.x(), pos.y())
        import fitz
        click = self._to_pdf(page_idx, lx, ly)
        z = self._zoom or 1.0
        for i in range(len(self._overlays) - 1, -1, -1):
            e = self._overlays[i]
            etype = e.get("type")
            if etype not in types or e.get("page") != page_idx:
                continue
            bb = overlay_pdf_bbox(e)
            if bb is None:
                continue
            m = self._overlay_hit_margin(etype) / z
            expanded = fitz.Rect(bb) + (-m, -m, m, m)
            if expanded.contains(click):
                return i
        return -1

    def _set_scroll_locked(self, locked: bool):
        sa = self._scroll_area
        if sa is None:
            return
        sa.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if locked
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if locked
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def _text_overlay_at(self, pos: QPoint) -> int:
        z = self._zoom
        m = self._text_hit_margin
        for i in range(len(self._overlays) - 1, -1, -1):
            e = self._overlays[i]
            if e.get("type") not in ("text", "text_edit"):
                continue
            pg = e.get("page", 0)
            if pg >= len(self._page_offsets):
                continue
            yo = self._page_offsets[pg][0]
            bb = overlay_pdf_bbox(e)
            if bb is None:
                continue
            qr = QRect(int(bb.x0 * z), yo + int(bb.y0 * z),
                       max(1, int(bb.width * z)), max(1, int(bb.height * z)))
            if qr.adjusted(-m, -m, m, m).contains(pos):
                return i
        return -1

    def _apply_overlay_drag(self, pos: QPoint):
        if self._overlay_drag_idx < 0 or not self._doc:
            return
        idx = self._overlay_drag_idx
        if idx >= len(self._overlays):
            return
        e = self._overlays[idx]
        page_idx = e.get("page", self._overlay_drag_page)
        if page_idx < 0 or page_idx >= self._doc.page_count:
            return
        _, lx, ly = self._page_and_local(pos.x(), pos.y())
        pdf_pt = self._to_pdf(page_idx, lx, ly)
        ox, oy = self._overlay_drag_offset
        ax = float(pdf_pt.x) - ox
        ay = float(pdf_pt.y) - oy
        targets = collect_snap_targets(self._doc[page_idx], self._overlays, skip_idx=idx)
        grid = self._grid_size if self._grid_snap_enabled else 0.0
        sx, sy, gx, gy = snap_point(ax, ay, targets, grid_size=grid)
        self._snap_guide_x = gx
        self._snap_guide_y = gy
        moved = move_overlay(e, sx, sy)
        self._overlays[idx].clear()
        self._overlays[idx].update(moved)
        self.update()

    def contextMenuEvent(self, e):
        pos = e.pos()
        hit = self._note_icon_at(pos)
        if hit < 0:
            hit, _ = self._annot_note_at(pos)
        if hit >= 0:
            from PySide6.QtWidgets import QMenu
            menu = QMenu(self)
            delete_action = menu.addAction(t("viewer.delete_comment"))
            action = menu.exec(e.globalPos())
            if action == delete_action:
                overlay = self._overlays[hit]
                if self._doc and overlay.get("_existing"):
                    import fitz
                    page = self._doc[overlay.get("page", 0)]
                    for annot in page.annots() or []:
                        if annot.type[0] == fitz.PDF_ANNOT_TEXT:
                            txt = annot.info.get("content", "") or ""
                            if txt.strip() == overlay.get("text", "").strip():
                                page.delete_annot(annot)
                                break
                self._overlays.pop(hit)
                if hasattr(self, "note_deleted"):
                    self.note_deleted.emit(overlay)
                if self._open_note == hit:
                    self._open_note = None
                elif self._open_note is not None and self._open_note > hit:
                    self._open_note -= 1
                self.update()
            return
        super().contextMenuEvent(e)

    def mouseReleaseEvent(self, e):
        if self._overlay_drag_idx >= 0:
            self._finish_overlay_drag()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = e.position().toPoint()
        if self._draw_mode and self._current_stroke is not None:
            if len(self._current_stroke) >= 2 and self._stroke_page >= 0:
                z = self._zoom or 1.0
                yo = self._page_offsets[self._stroke_page][0]
                pdf_points = [(round(x / z, 2), round((y - yo) / z, 2))
                              for x, y in self._current_stroke]
                self._page_idx = self._stroke_page
                self.stroke_finished.emit(self._stroke_page, pdf_points)
            self._current_stroke = None
            self._stroke_page = -1
            self.update()
            return
        if self._drag_rect and self._drag_rect.width() > 3 and self._drag_rect.height() > 3:
            skip_new_area = (
                self._area_move_mode
                and self._draggable_overlay_at(self._drag_rect.center()) >= 0
            )
            if not skip_new_area:
                page_idx, lx, ly = self._page_and_local(
                    self._drag_rect.left(), self._drag_rect.top())
                yo = self._page_offsets[page_idx][0] if page_idx < len(self._page_offsets) else 0
                local_rect = QRect(self._drag_rect.left(), self._drag_rect.top() - yo,
                                   self._drag_rect.width(), self._drag_rect.height())
                self._page_idx = page_idx
                pdf_rect = self._rect_to_pdf(page_idx, local_rect)
                if pdf_rect is not None:
                    self.rect_selected.emit(page_idx, pdf_rect)
        else:
            hit = self._note_icon_at(pos)
            if hit < 0:
                hit, _ = self._annot_note_at(pos)
            if hit >= 0:
                self._open_note = None if self._open_note == hit else hit
                self.update()
                self._drag_start = None; self._drag_rect = None
                return
            if self._open_note is not None:
                self._open_note = None
                self.update()
            page_idx, lx, ly = self._page_and_local(pos.x(), pos.y())
            self._page_idx = page_idx
            self.point_clicked.emit(page_idx, self._to_pdf(page_idx, lx, ly))
        self._drag_start = None; self._drag_rect = None
        self.update()
