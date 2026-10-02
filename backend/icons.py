"""Anti-aliased icon rendering with Pillow.

Tkinter's Canvas has no anti-aliasing, so circles and glyphs drawn directly on
it show jagged "teeth". Here we render each icon at a high supersample factor
and downscale with LANCZOS, producing smooth, modern edges.

The bubble is rendered as RGBA with a fully transparent background so it can be
shown through a Windows layered window (per-pixel alpha) — no color-key matte,
so there is no dark halo around the circle. These helpers are deliberately
Tk-free (they return PIL Images) so they can be unit-tested.
"""

import math
from typing import Tuple

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when Pillow is absent
    PIL_AVAILABLE = False

SUPERSAMPLE = 4

WHITE = (255, 255, 255, 255)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _round_line(draw, p0, p1, width: float, color) -> None:
    draw.line([p0, p1], fill=color, width=max(1, int(round(width))))
    radius = width / 2.0
    for x, y in (p0, p1):
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)


def _load_font(size_px: int):
    for name in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size_px)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _draw_bubble_glyph(draw, glyph: str, x0: float, y0: float, box: float, text: str) -> None:
    """Draw the white state glyph inside the square box (x0, y0, box)."""
    cx = x0 + box / 2.0
    cy = y0 + box / 2.0
    stroke = box * 0.055

    def px(fx):
        return x0 + fx * box

    def py(fy):
        return y0 + fy * box

    if glyph == "play":
        draw.polygon([(px(0.40), py(0.30)), (px(0.40), py(0.70)), (px(0.73), py(0.50))], fill=WHITE)
    elif glyph == "stop":
        draw.rounded_rectangle([px(0.37), py(0.37), px(0.63), py(0.63)], radius=box * 0.07, fill=WHITE)
    elif glyph == "ellipsis":
        dot = box * 0.05
        for fx in (0.34, 0.50, 0.66):
            draw.ellipse([px(fx) - dot, cy - dot, px(fx) + dot, cy + dot], fill=WHITE)
    elif glyph == "paste":
        _round_line(draw, (cx, py(0.27)), (cx, py(0.58)), stroke, WHITE)
        _round_line(draw, (px(0.37), py(0.45)), (cx, py(0.58)), stroke, WHITE)
        _round_line(draw, (px(0.63), py(0.45)), (cx, py(0.58)), stroke, WHITE)
        _round_line(draw, (px(0.33), py(0.72)), (px(0.67), py(0.72)), stroke, WHITE)
    elif glyph == "check":
        _round_line(draw, (px(0.29), py(0.52)), (px(0.43), py(0.66)), stroke * 1.05, WHITE)
        _round_line(draw, (px(0.43), py(0.66)), (px(0.73), py(0.33)), stroke * 1.05, WHITE)
    elif glyph == "error":
        _round_line(draw, (cx, py(0.28)), (cx, py(0.56)), stroke, WHITE)
        dot = box * 0.045
        draw.ellipse([cx - dot, py(0.66), cx + dot, py(0.66) + 2 * dot], fill=WHITE)
    else:
        font = _load_font(int(box * 0.5))
        if font is not None:
            draw.text((cx, cy), text or "", font=font, fill=WHITE, anchor="mm")


def render_bubble_rgba(
    glyph: str,
    bg_hex: str,
    ring_hex: str,
    window_size: int,
    circle_size: int,
    text: str = "",
) -> "Image.Image":
    """Render a circular bubble as RGBA with a transparent background.

    The circle is centered in a window_size canvas; everything outside the
    circle is fully transparent, so a layered window composites it smoothly
    over any desktop with no dark fringe.
    """
    scale = SUPERSAMPLE
    canvas = window_size * scale
    diameter = circle_size * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    offset = (canvas - diameter) / 2.0
    box = [offset, offset, offset + diameter, offset + diameter]
    draw.ellipse(box, fill=hex_to_rgb(bg_hex) + (255,))
    draw.ellipse(box, outline=hex_to_rgb(ring_hex) + (255,), width=max(1, scale))

    _draw_bubble_glyph(draw, glyph, offset, offset, diameter, text)

    return img.resize((window_size, window_size), Image.LANCZOS)


def render_glyph(name: str, color_hex: str, size: int) -> "Image.Image":
    """Render a thin-line UI glyph on a transparent background (RGBA)."""
    scale = SUPERSAMPLE
    canvas = size * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = hex_to_rgb(color_hex) + (255,)
    s = canvas
    cx = s / 2.0
    cy = s / 2.0
    stroke = s * 0.06

    if name == "history":
        pad = s * 0.18
        draw.ellipse([pad, pad, s - pad, s - pad], outline=color, width=max(1, int(stroke * 0.8)))
        _round_line(draw, (cx, cy), (cx, cy - s * 0.18), stroke * 0.8, color)
        _round_line(draw, (cx, cy), (cx + s * 0.16, cy + s * 0.08), stroke * 0.8, color)
    elif name == "settings":
        ring_r = s * 0.30
        draw.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r], outline=color, width=max(1, int(stroke * 0.8)))
        hub = s * 0.10
        draw.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], outline=color, width=max(1, int(stroke * 0.7)))
        for i in range(6):
            a = i * math.pi / 3.0
            _round_line(
                draw,
                (cx + ring_r * math.cos(a), cy + ring_r * math.sin(a)),
                (cx + (ring_r + s * 0.10) * math.cos(a), cy + (ring_r + s * 0.10) * math.sin(a)),
                stroke * 0.7,
                color,
            )
    elif name == "close":
        d = s * 0.26
        _round_line(draw, (cx - d, cy - d), (cx + d, cy + d), stroke, color)
        _round_line(draw, (cx + d, cy - d), (cx - d, cy + d), stroke, color)
    elif name == "export":
        _round_line(draw, (cx, s * 0.22), (cx, s * 0.60), stroke, color)
        _round_line(draw, (cx - s * 0.12, s * 0.46), (cx, s * 0.60), stroke, color)
        _round_line(draw, (cx + s * 0.12, s * 0.46), (cx, s * 0.60), stroke, color)
        _round_line(draw, (s * 0.26, s * 0.74), (s * 0.74, s * 0.74), stroke, color)
    elif name == "save":
        draw.rounded_rectangle([s * 0.24, s * 0.24, s * 0.76, s * 0.76], radius=s * 0.06, outline=color, width=max(1, int(stroke * 0.8)))
        _round_line(draw, (cx, s * 0.30), (cx, s * 0.54), stroke * 0.8, color)
        _round_line(draw, (cx - s * 0.10, s * 0.44), (cx, s * 0.54), stroke * 0.8, color)
        _round_line(draw, (cx + s * 0.10, s * 0.44), (cx, s * 0.54), stroke * 0.8, color)
    elif name == "copy":
        draw.rounded_rectangle(
            [s * 0.34, s * 0.24, s * 0.74, s * 0.64],
            radius=s * 0.055,
            outline=color,
            width=max(1, int(stroke * 0.75)),
        )
        draw.rounded_rectangle(
            [s * 0.24, s * 0.36, s * 0.64, s * 0.76],
            radius=s * 0.055,
            outline=color,
            width=max(1, int(stroke * 0.75)),
        )
    elif name == "tray":
        draw.rounded_rectangle(
            [s * 0.22, s * 0.56, s * 0.78, s * 0.76],
            radius=s * 0.05,
            outline=color,
            width=max(1, int(stroke * 0.75)),
        )
        _round_line(draw, (cx, s * 0.22), (cx, s * 0.50), stroke * 0.8, color)
        _round_line(draw, (cx - s * 0.12, s * 0.39), (cx, s * 0.50), stroke * 0.8, color)
        _round_line(draw, (cx + s * 0.12, s * 0.39), (cx, s * 0.50), stroke * 0.8, color)
    elif name == "wave":
        for offset in (-0.18, 0.0, 0.18):
            x = cx + s * offset
            _round_line(draw, (x, cy - s * 0.22), (x, cy + s * 0.22), stroke * 0.55, color)
        _round_line(draw, (cx - s * 0.32, cy - s * 0.10), (cx - s * 0.32, cy + s * 0.10), stroke * 0.55, color)
        _round_line(draw, (cx + s * 0.32, cy - s * 0.10), (cx + s * 0.32, cy + s * 0.10), stroke * 0.55, color)
    elif name == "monitor":
        draw.rounded_rectangle(
            [s * 0.18, s * 0.24, s * 0.82, s * 0.62],
            radius=s * 0.045,
            outline=color,
            width=max(1, int(stroke * 0.7)),
        )
        _round_line(draw, (cx, s * 0.62), (cx, s * 0.74), stroke * 0.65, color)
        _round_line(draw, (cx - s * 0.16, s * 0.76), (cx + s * 0.16, s * 0.76), stroke * 0.65, color)
    elif name == "keyboard":
        draw.rounded_rectangle(
            [s * 0.16, s * 0.28, s * 0.84, s * 0.72],
            radius=s * 0.055,
            outline=color,
            width=max(1, int(stroke * 0.7)),
        )
        key_r = s * 0.018
        for row_y in (0.41, 0.52):
            for col_x in (0.30, 0.40, 0.50, 0.60, 0.70):
                draw.ellipse(
                    [s * col_x - key_r, s * row_y - key_r, s * col_x + key_r, s * row_y + key_r],
                    fill=color,
                )
        _round_line(draw, (s * 0.36, s * 0.63), (s * 0.64, s * 0.63), stroke * 0.55, color)

    return img.resize((size, size), Image.LANCZOS)
