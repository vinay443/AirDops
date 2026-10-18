"""Tray icon drawn at runtime with Pillow (no image files to ship)."""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

GREY = (140, 140, 140, 255)
GREEN = (46, 204, 113, 255)
BLUE = (52, 152, 219, 255)
AMBER = (243, 156, 18, 255)
RED = (231, 76, 60, 255)
WHITE = (255, 255, 255, 255)


def _bud(draw: ImageDraw.ImageDraw, x: int, color, mirror: bool, size: int) -> None:
    s = size / 64.0
    head = [x - 11 * s, 6 * s, x + 11 * s, 28 * s]
    draw.ellipse(head, fill=color)
    stem_x0 = x + (2 * s if mirror else -8 * s)
    draw.rounded_rectangle([stem_x0, 18 * s, stem_x0 + 6 * s, 46 * s], radius=3 * s, fill=color)


def render(state: str = "off", battery: Optional[int] = None, size: int = 64) -> Image.Image:
    """state: 'off' (not connected), 'game', 'call'."""
    color = {"game": GREEN, "call": BLUE}.get(state, GREY)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64.0
    _bud(d, int(20 * s), color, mirror=False, size=size)
    _bud(d, int(44 * s), color, mirror=True, size=size)
    if battery is not None and state != "off":
        level = max(0, min(100, battery))
        bar_color = RED if level <= 20 else AMBER if level <= 40 else WHITE
        d.rounded_rectangle([4 * s, 52 * s, 60 * s, 62 * s], radius=3 * s, outline=WHITE, width=max(1, int(2 * s)))
        width = (60 - 4 - 4) * s * level / 100.0
        if width > 0:
            d.rectangle([6 * s, 54 * s, 6 * s + width, 60 * s], fill=bar_color)
    return img


def save_ico(path: str) -> None:
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    render("game", size=256).save(path, format="ICO", sizes=sizes)
