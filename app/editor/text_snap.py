"""Magnetic snap guides for dragging text overlays."""

from __future__ import annotations

import copy

SNAP_THRESHOLD = 6.0  # PDF points
DEFAULT_GRID_SIZE = 5.0  # PDF points (~1.8 mm)


def overlay_pdf_bbox(edit: dict):
    """Approximate PDF bbox for a pending text overlay."""
    import fitz

    etype = edit.get("type")
    if etype == "text_edit":
        bb = edit.get("bbox")
        return fitz.Rect(bb) if bb else None
    if etype == "area_move":
        dst = edit.get("dst_rect") or edit.get("src_rect")
        return fitz.Rect(dst) if dst else None
    if etype == "text":
        pt = edit["point"]
        size = float(edit.get("size", 12))
        text = edit.get("text", "") or ""
        x0 = float(pt.x) if hasattr(pt, "x") else float(pt[0])
        y0 = float(pt.y) if hasattr(pt, "y") else float(pt[1])
        w = max(size * 0.6, len(text) * size * 0.52)
        return fitz.Rect(x0, y0 - size * 0.85, x0 + w, y0 + size * 0.2)
    return None


def overlay_anchor(edit: dict) -> tuple[float, float]:
    """Reference point used when dragging (baseline left)."""
    import fitz

    if edit.get("type") == "text_edit":
        orig = edit.get("origin")
        if orig and len(orig) >= 2:
            return float(orig[0]), float(orig[1])
        bb = edit.get("bbox") or (0, 0, 0, 0)
        return float(bb[0]), float(bb[3])
    if edit.get("type") == "area_move":
        dst = edit.get("dst_rect") or edit.get("src_rect") or (0, 0, 0, 0)
        return float(dst[0]), float(dst[1])
    pt = edit["point"]
    return (
        float(pt.x) if hasattr(pt, "x") else float(pt[0]),
        float(pt.y) if hasattr(pt, "y") else float(pt[1]),
    )


def collect_snap_targets(page, overlays: list, skip_idx: int = -1) -> dict:
    """Collect X/Y snap lines from PDF text and other pending overlays."""
    import fitz

    xs: list[float] = []
    ys: list[float] = []

    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            lb = fitz.Rect(line["bbox"])
            xs.extend([lb.x0, lb.x1, (lb.x0 + lb.x1) / 2])
            ys.extend([lb.y0, lb.y1, (lb.y0 + lb.y1) / 2])
            for span in line.get("spans", []):
                if not (span.get("text") or "").strip():
                    continue
                bb = fitz.Rect(span["bbox"])
                xs.extend([bb.x0, bb.x1])
                origin = span.get("origin")
                if origin and len(origin) >= 2:
                    ys.append(float(origin[1]))
                else:
                    ys.append(bb.y1)

    for i, e in enumerate(overlays):
        if i == skip_idx:
            continue
        if e.get("type") not in ("text", "text_edit", "area_move"):
            continue
        if e.get("page") != page.number:
            continue
        bb = overlay_pdf_bbox(e)
        if bb is None:
            continue
        xs.extend([bb.x0, bb.x1, (bb.x0 + bb.x1) / 2])
        ys.extend([bb.y0, bb.y1, (bb.y0 + bb.y1) / 2])
        ax, ay = overlay_anchor(e)
        xs.append(ax)
        ys.append(ay)

    return {"x": xs, "y": ys}


def snap_point(x: float, y: float, targets: dict,
               threshold: float = SNAP_THRESHOLD,
               grid_size: float = 0.0) -> tuple[float, float, float | None, float | None]:
    """Snap (x, y) to nearest guides. Returns (x, y, guide_x, guide_y) in PDF coords."""
    guide_x = guide_y = None
    snapped_x, snapped_y = x, y

    best_dx = threshold + 1
    for tx in targets.get("x", []):
        d = abs(x - tx)
        if d <= threshold and d < best_dx:
            best_dx = d
            snapped_x = tx
            guide_x = tx

    best_dy = threshold + 1
    for ty in targets.get("y", []):
        d = abs(y - ty)
        if d <= threshold and d < best_dy:
            best_dy = d
            snapped_y = ty
            guide_y = ty

    if grid_size > 0:
        if guide_x is None:
            gx = round(x / grid_size) * grid_size
            if abs(x - gx) <= threshold:
                snapped_x = gx
                guide_x = gx
        if guide_y is None:
            gy = round(y / grid_size) * grid_size
            if abs(y - gy) <= threshold:
                snapped_y = gy
                guide_y = gy

    return snapped_x, snapped_y, guide_x, guide_y


def clone_overlay_edit(edit: dict) -> dict:
    """Deep-copy a pending text overlay (fitz.Point-safe)."""
    import fitz

    e = copy.deepcopy(edit)
    if e.get("type") == "text" and "point" in edit:
        pt = edit["point"]
        e["point"] = fitz.Point(
            float(pt.x) if hasattr(pt, "x") else float(pt[0]),
            float(pt.y) if hasattr(pt, "y") else float(pt[1]),
        )
    return e


def overlay_positions_differ(before: dict, after: dict, eps: float = 0.05) -> bool:
    ax1, ay1 = overlay_anchor(before)
    ax2, ay2 = overlay_anchor(after)
    return abs(ax1 - ax2) > eps or abs(ay1 - ay2) > eps


def move_overlay(edit: dict, new_x: float, new_y: float) -> dict:
    """Return a copy of *edit* moved so its anchor sits at (new_x, new_y)."""
    import fitz

    e = dict(edit)
    ax, ay = overlay_anchor(edit)
    dx, dy = new_x - ax, new_y - ay
    if e.get("type") == "text_edit":
        orig = list(e.get("origin") or [ax, ay])
        e["origin"] = [orig[0] + dx, orig[1] + dy]
        bb = e.get("bbox")
        if bb:
            e["bbox"] = [bb[0] + dx, bb[1] + dy, bb[2] + dx, bb[3] + dy]
    elif e.get("type") == "text":
        pt = e["point"]
        px = float(pt.x) if hasattr(pt, "x") else float(pt[0])
        py = float(pt.y) if hasattr(pt, "y") else float(pt[1])
        e["point"] = fitz.Point(px + dx, py + dy)
    elif e.get("type") == "area_move":
        dst = list(e.get("dst_rect") or e.get("src_rect"))
        w, h = dst[2] - dst[0], dst[3] - dst[1]
        e["dst_rect"] = [dst[0] + dx, dst[1] + dy, dst[0] + dx + w, dst[1] + dy + h]
    return e
