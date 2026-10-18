"""Vector artwork drawn with QPainter: AirPods, case, glyphs.

Everything is drawn in code so it stays sharp at any DPI and there are no
image assets (or Apple artwork) in the repository.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

WHITE_HI = QColor("#FFFFFF")
WHITE_MID = QColor("#F2F2F4")
WHITE_LO = QColor("#D9D9DE")
GRILLE = QColor("#2B2B2E")
TIP = QColor("#E4E4E8")


def _shadow(p: QPainter, rect: QRectF, strength: float = 0.22) -> None:
    g = QRadialGradient(rect.center(), rect.width() / 2)
    c = QColor(0, 0, 0, int(255 * strength))
    g.setColorAt(0.0, c)
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.scale(1.0, 1.0)
    p.drawEllipse(rect)
    p.restore()


def _plastic(rect: QRectF) -> QLinearGradient:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, WHITE_HI)
    g.setColorAt(0.55, WHITE_MID)
    g.setColorAt(1.0, WHITE_LO)
    return g


def draw_bud(p: QPainter, box: QRectF, left: bool, dim: bool = False) -> None:
    """An AirPods Pro bud seen from the front, fitted into ``box``."""
    w, h = box.width(), box.height()
    x0, y0 = box.left(), box.top()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if dim:
        p.setOpacity(p.opacity() * 0.45)
    mirror = 1 if left else -1
    cx = x0 + w / 2

    # soft floor shadow
    _shadow(p, QRectF(cx - w * 0.28, y0 + h * 0.88, w * 0.56, h * 0.09), 0.18)

    # ear tip (silicone), towards the inside
    tip = QRectF(cx + mirror * w * 0.10 - w * 0.22, y0 + h * 0.10, w * 0.44, h * 0.26)
    tg = QLinearGradient(tip.topLeft(), tip.bottomLeft())
    tg.setColorAt(0, QColor("#F4F4F6"))
    tg.setColorAt(1, QColor("#CFCFD5"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(tg))
    p.drawEllipse(tip)

    # head
    head = QRectF(cx - mirror * w * 0.06 - w * 0.30, y0 + h * 0.06, w * 0.60, h * 0.34)
    p.setBrush(QBrush(_plastic(head)))
    p.setPen(QPen(QColor(0, 0, 0, 28), max(0.6, w * 0.012)))
    p.drawEllipse(head)

    # stem
    stem_w = w * 0.22
    stem_x = cx - mirror * w * 0.10 - stem_w / 2
    stem = QRectF(stem_x, y0 + h * 0.30, stem_w, h * 0.52)
    path = QPainterPath()
    path.addRoundedRect(stem, stem_w / 2, stem_w / 2)
    sg = QLinearGradient(stem.topLeft(), stem.topRight())
    sg.setColorAt(0.0, WHITE_LO)
    sg.setColorAt(0.35, WHITE_HI)
    sg.setColorAt(1.0, QColor("#E1E1E6"))
    p.setBrush(QBrush(sg))
    p.drawPath(path)

    # grille and stem sensor
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(GRILLE)
    gr = QRectF(head.center().x() - w * 0.07, head.top() + head.height() * 0.22, w * 0.14, h * 0.035)
    p.drawRoundedRect(gr, gr.height() / 2, gr.height() / 2)
    sensor = QRectF(stem.center().x() - stem_w * 0.28, stem.bottom() - stem_w * 0.65, stem_w * 0.56, stem_w * 0.40)
    p.setBrush(QColor("#9A9AA0"))
    p.drawRoundedRect(sensor, sensor.height() / 2, sensor.height() / 2)

    # highlight
    hl = QRectF(head.left() + head.width() * 0.18, head.top() + head.height() * 0.12, head.width() * 0.30, head.height() * 0.22)
    p.setBrush(QColor(255, 255, 255, 170))
    p.drawEllipse(hl)
    p.restore()


def draw_case(p: QPainter, box: QRectF, dim: bool = False, led: QColor | None = None) -> None:
    """AirPods Pro charging case (landscape), fitted into ``box``."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if dim:
        p.setOpacity(p.opacity() * 0.45)
    w, h = box.width(), box.height()
    body = QRectF(box.left() + w * 0.04, box.top() + h * 0.08, w * 0.92, h * 0.80)
    _shadow(p, QRectF(body.left() + w * 0.06, body.bottom() - h * 0.02, body.width() - w * 0.12, h * 0.14), 0.22)
    radius = body.height() * 0.30
    p.setPen(QPen(QColor(0, 0, 0, 30), max(0.6, w * 0.006)))
    p.setBrush(QBrush(_plastic(body)))
    p.drawRoundedRect(body, radius, radius)
    # lid seam
    seam_y = body.top() + body.height() * 0.36
    p.setPen(QPen(QColor(0, 0, 0, 38), max(0.8, w * 0.007)))
    inset = radius * 0.30
    p.drawLine(QPointF(body.left() + inset, seam_y), QPointF(body.right() - inset, seam_y))
    # status light
    if led is not None:
        p.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(QPointF(body.center().x(), seam_y + body.height() * 0.22), w * 0.05)
        c = QColor(led)
        glow.setColorAt(0, c)
        c2 = QColor(led)
        c2.setAlpha(0)
        glow.setColorAt(1, c2)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(body.center().x(), seam_y + body.height() * 0.22), w * 0.05, w * 0.05)
        p.setBrush(c)
        p.drawEllipse(QPointF(body.center().x(), seam_y + body.height() * 0.22), w * 0.012, w * 0.012)
    # top highlight
    hl = QRectF(body.left() + radius, body.top() + body.height() * 0.06, body.width() - 2 * radius, body.height() * 0.10)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawRoundedRect(hl, hl.height() / 2, hl.height() / 2)
    p.restore()


def draw_hero(p: QPainter, box: QRectF, connected: bool, led: QColor | None = None) -> None:
    """Case with both buds floating either side of it - the header illustration."""
    w, h = box.width(), box.height()
    dim = not connected
    case_box = QRectF(box.left() + w * 0.28, box.top() + h * 0.46, w * 0.44, h * 0.50)
    draw_case(p, case_box, dim=dim, led=led if connected else None)
    bw, bh = w * 0.21, h * 0.70
    for left, cx, angle in ((True, box.left() + w * 0.17, -10.0), (False, box.right() - w * 0.17, 10.0)):
        p.save()
        p.translate(cx, box.top() + h * 0.02 + bh / 2)
        p.rotate(angle)
        draw_bud(p, QRectF(-bw / 2, -bh / 2, bw, bh), left=left, dim=dim)
        p.restore()


# ------------------------------------------------------------------ glyphs
def glyph_bud(p: QPainter, box: QRectF, color: QColor, left: bool) -> None:
    """Flat single-colour bud glyph (SF Symbols style) for small sizes."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    w, h = box.width(), box.height()
    m = 1 if left else -1
    cx = box.center().x()
    head = QRectF(cx - m * w * 0.04 - w * 0.40, box.top(), w * 0.80, h * 0.46)
    p.drawEllipse(head)
    stem_w = w * 0.36
    stem = QRectF(cx - m * w * 0.14 - stem_w / 2, box.top() + h * 0.30, stem_w, h * 0.70)
    p.drawRoundedRect(stem, stem_w / 2, stem_w / 2)
    p.restore()


def glyph_case(p: QPainter, box: QRectF, color: QColor) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = box.width(), box.height()
    body = QRectF(box.left(), box.top() + h * 0.12, w, h * 0.76)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    r = body.height() * 0.32
    p.drawRoundedRect(body, r, r)
    # seam knocked out
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    seam = QRectF(body.left() + r * 0.4, body.top() + body.height() * 0.34, body.width() - r * 0.8, max(1.0, h * 0.07))
    p.drawRect(seam)
    p.restore()


def tray_pixmap(size: int, dark_taskbar: bool, connected: bool, battery: int | None = None) -> QPixmap:
    """Monochrome template icon, like a macOS menu-bar extra."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QColor("#FFFFFF") if dark_taskbar else QColor("#000000")
    if not connected:
        base.setAlphaF(0.45)
    s = size
    glyph_bud(p, QRectF(s * 0.06, s * 0.08, s * 0.40, s * 0.80), base, left=True)
    glyph_bud(p, QRectF(s * 0.54, s * 0.08, s * 0.40, s * 0.80), base, left=False)
    if connected and battery is not None and battery <= 20:
        dot = QColor("#FF453A") if battery <= 10 else QColor("#FF9F0A")
        p.setPen(QPen(QColor(0, 0, 0, 0)))
        p.setBrush(dot)
        r = s * 0.17
        p.drawEllipse(QPointF(s - r - 0.5, s - r - 0.5), r, r)
    p.end()
    return QPixmap.fromImage(img)


def app_icon_image(size: int = 256) -> QImage:
    """Rounded-square app icon (used for the .exe and notifications)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    rect = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0, QColor("#3A3A3C"))
    g.setColorAt(1, QColor("#111113"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    radius = size * 0.2237  # iOS squircle-ish ratio
    p.drawRoundedRect(rect, radius, radius)
    draw_hero(p, QRectF(size * 0.14, size * 0.18, size * 0.72, size * 0.66), connected=True)
    p.end()
    return img
