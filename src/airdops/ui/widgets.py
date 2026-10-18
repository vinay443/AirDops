"""Apple-style controls: switch, segmented control, battery ring, grouped list."""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import art, theme

_active: theme.Palette = theme.LIGHT


def P() -> theme.Palette:
    return _active


def set_palette(p: theme.Palette) -> None:
    global _active
    _active = p


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


def _soft_shadow(p: QPainter, rect: QRectF, radius: float, alpha: int = 40, spread: int = 3) -> None:
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(spread, 0, -1):
        c = QColor(0, 0, 0, int(alpha / (i * 1.6)))
        p.setBrush(c)
        r = rect.adjusted(-i * 0.5, -i * 0.2 + 1, i * 0.5, i * 0.7 + 1)
        p.drawRoundedRect(r, radius + i * 0.5, radius + i * 0.5)
    p.restore()


class Label(QLabel):
    """Text label that picks its colour from the active palette at paint time."""

    def __init__(self, text: str = "", size: float = 13, weight=QFont.Weight.Normal, role: str = "label") -> None:
        super().__init__(text)
        self.role = role
        self.setFont(theme.font(size, weight))
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:  # noqa: N802
        color = getattr(P(), self.role) if self.isEnabled() else P().tertiary
        if self.palette().color(self.foregroundRole()) != color:
            pal = self.palette()
            pal.setColor(self.foregroundRole(), color)
            self.setPalette(pal)
        super().paintEvent(event)


# --------------------------------------------------------------- switch
class Switch(QAbstractButton):
    """iOS / macOS style on-off switch with a sliding, shadowed knob."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 26)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(44, 26)

    def _get(self) -> float:
        return self._pos

    def _set(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:  # noqa: N802 - snap without animation when set by code
        if on == self.isChecked():
            return
        self.blockSignals(True)
        super().setChecked(on)
        self.blockSignals(False)
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if not self.isEnabled():
            p.setOpacity(0.45)
        track = mix(pal.fill_strong, pal.green, self._pos)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.left() + 2 + (r.width() - d - 4) * self._pos
        knob = QRectF(x, r.top() + 2, d, d)
        _soft_shadow(p, knob, d / 2, alpha=60, spread=3)
        p.setBrush(pal.knob)
        p.drawEllipse(knob)


# ----------------------------------------------------- segmented control
class Segmented(QWidget):
    changed = Signal(int)

    def __init__(self, options: Sequence[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.options = list(options)
        self.index = 0
        self._x = 0.0
        self._hover = -1
        self.setFixedHeight(32)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QPropertyAnimation(self, b"pill", self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._font = theme.font(13, QFont.Weight.Medium)
        self._font_sel = theme.font(13, QFont.Weight.DemiBold)

    def _get(self) -> float:
        return self._x

    def _set(self, v: float) -> None:
        self._x = v
        self.update()

    pill = Property(float, _get, _set)

    def set_index(self, i: int, animate: bool = False) -> None:
        if i == self.index and not animate:
            self._x = float(i)
            self.update()
            return
        self.index = i
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._x)
            self._anim.setEndValue(float(i))
            self._anim.start()
        else:
            self._x = float(i)
            self.update()

    def _seg_at(self, x: float) -> int:
        n = len(self.options)
        return max(0, min(n - 1, int(x / (self.width() / n))))

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        self._hover = self._seg_at(e.position().x())
        self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        i = self._seg_at(e.position().x())
        if i != self.index:
            self.set_index(i, animate=True)
            self.changed.emit(i)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.fill)
        p.drawRoundedRect(r, 9, 9)
        n = len(self.options)
        seg_w = r.width() / n
        pill = QRectF(2 + self._x * seg_w, 2, seg_w - 4, r.height() - 4)
        if 0 <= self._hover < n and self._hover != self.index:
            hv = QRectF(2 + self._hover * seg_w, 2, seg_w - 4, r.height() - 4)
            p.setBrush(pal.hover)
            p.drawRoundedRect(hv, 7, 7)
        _soft_shadow(p, pill, 7, alpha=45 if not pal.dark else 80, spread=3)
        p.setBrush(pal.segment_pill)
        p.drawRoundedRect(pill, 7, 7)
        for i, text in enumerate(self.options):
            seg = QRectF(i * seg_w, 0, seg_w, r.height())
            p.setFont(self._font_sel if i == self.index else self._font)
            p.setPen(pal.label)
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, text)


# ------------------------------------------------------------ battery tile
class BatteryTile(QWidget):
    """Ring gauge with a glyph inside, percentage and caption underneath."""

    def __init__(self, kind: str, caption: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.kind = kind  # "left", "right", "case", "single"
        self.caption = caption
        self.level: Optional[int] = None
        self.charging = False
        self.setFixedSize(92, 108)
        self._f_pct = theme.font(15, QFont.Weight.DemiBold)
        self._f_cap = theme.font(11.5, QFont.Weight.Medium)

    def set_value(self, level: Optional[int], charging: bool) -> None:
        if (level, charging) != (self.level, self.charging):
            self.level, self.charging = level, charging
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = 62.0
        ring = QRectF((self.width() - size) / 2, 4, size, size)
        stroke = 5.5
        inner = ring.adjusted(stroke / 2, stroke / 2, -stroke / 2, -stroke / 2)
        p.setPen(QPen(pal.fill_strong, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(inner)
        color = theme.battery_color(pal, self.level, self.charging)
        if self.level is not None:
            span = -int(360 * 16 * max(0.02, self.level / 100.0))
            p.setPen(QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(inner, 90 * 16, span)

        glyph_color = QColor(pal.label)
        if self.level is None:
            glyph_color = QColor(pal.tertiary)
        c = ring.center()
        if self.kind in ("left", "right", "single"):
            box = QRectF(c.x() - 9, c.y() - 15, 18, 30)
            art.glyph_bud(p, box, glyph_color, left=self.kind != "right")
        else:
            box = QRectF(c.x() - 15, c.y() - 10, 30, 20)
            art.glyph_case(p, box, glyph_color)

        # percentage (+ bolt)
        text = f"{self.level}%" if self.level is not None else "–"
        p.setFont(self._f_pct)
        p.setPen(pal.label if self.level is not None else pal.tertiary)
        fm = QFontMetricsF(self._f_pct)
        tw = fm.horizontalAdvance(text)
        bolt_w = 9 if self.charging else 0
        x0 = (self.width() - tw - bolt_w) / 2
        y_text = ring.bottom() + 8
        p.drawText(QRectF(x0, y_text, tw + 2, fm.height()), Qt.AlignmentFlag.AlignLeft, text)
        if self.charging:
            draw_bolt(p, QRectF(x0 + tw + 2, y_text + 3, 8, fm.height() - 6), pal.green)
        p.setFont(self._f_cap)
        p.setPen(pal.secondary)
        p.drawText(QRectF(0, y_text + fm.height(), self.width(), 16), Qt.AlignmentFlag.AlignHCenter, self.caption)


def draw_bolt(p: QPainter, box: QRectF, color: QColor) -> None:
    path = QPainterPath()
    w, h = box.width(), box.height()
    x, y = box.left(), box.top()
    path.moveTo(x + w * 0.62, y)
    path.lineTo(x, y + h * 0.58)
    path.lineTo(x + w * 0.45, y + h * 0.58)
    path.lineTo(x + w * 0.35, y + h)
    path.lineTo(x + w, y + h * 0.40)
    path.lineTo(x + w * 0.55, y + h * 0.40)
    path.closeSubpath()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPath(path)
    p.restore()


# ------------------------------------------------------------ grouped list
class Group(QWidget):
    """Inset grouped list (iOS Settings style): rounded card, hairline separators."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.rows: list[QWidget] = []

    def add(self, row: QWidget) -> QWidget:
        self.rows.append(row)
        self._layout.addWidget(row)
        return row

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.group)
        p.drawRoundedRect(r, 11, 11)
        visible = [w for w in self.rows if not w.isHidden()]
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        sep = QColor(pal.separator)
        sep.setAlphaF(min(1.0, sep.alphaF() * 1.3))
        p.setPen(QPen(sep, 1))
        for w in visible[:-1]:
            y = w.geometry().bottom() + 1
            p.drawLine(16, y, int(r.right()), y)


class Row(QWidget):
    """Title + optional subtitle on the left, an accessory on the right."""

    clicked = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        accessory: Optional[QWidget] = None,
        clickable: bool = False,
    ) -> None:
        super().__init__()
        self._clickable = clickable
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 9, 12, 9)
        lay.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = Label(title, 13.5, QFont.Weight.Medium)
        self.subtitle = Label(subtitle, 11.5, role="secondary")
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        lay.addLayout(text, 1)
        self.accessory = accessory
        if accessory is not None:
            lay.addWidget(accessory, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumHeight(44)
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_subtitle(self, text: str) -> None:
        if self.subtitle.text() != text:
            self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def enterEvent(self, e) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._clickable and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        elif isinstance(self.accessory, Switch) and self.accessory.isEnabled():
            # Clicking anywhere on a switch row flips it, like iOS.
            self.accessory.toggle()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._hover and (self._clickable or isinstance(self.accessory, Switch)):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(P().hover)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 2, -4, -2), 8, 8)


class TextButton(QAbstractButton):
    """Borderless accent-coloured text button (like a macOS link button)."""

    def __init__(self, text: str, role: str = "accent", size: float = 13, weight=QFont.Weight.Medium) -> None:
        super().__init__()
        self.setText(text)
        self.role = role
        self._font = theme.font(size, weight)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        fm = QFontMetricsF(self._font)
        self.setFixedHeight(int(fm.height() + 10))
        self.setMinimumWidth(int(fm.horizontalAdvance(text) + 16))

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetricsF(self._font)
        return QSize(int(fm.horizontalAdvance(self.text()) + 16), int(fm.height() + 10))

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.hover)
            p.drawRoundedRect(QRectF(self.rect()), 7, 7)
        color = QColor(getattr(pal, self.role))
        if self.isDown():
            color.setAlphaF(color.alphaF() * 0.6)
        p.setPen(color)
        p.setFont(self._font)
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.text())


class PopupButton(QAbstractButton):
    """macOS pop-up button: current value + up/down chevrons; opens a menu."""

    def __init__(self, on_open: Callable[["PopupButton"], None]) -> None:
        super().__init__()
        self._on_open = on_open
        self._font = theme.font(12.5, QFont.Weight.Medium)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(26)
        self.setMaximumWidth(190)
        self.clicked.connect(lambda: self._on_open(self))

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = QFontMetricsF(self._font)
        return QSize(min(190, int(fm.horizontalAdvance(self.text()) + 36)), 26)

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self.updateGeometry()

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.fill_strong if self.underMouse() else pal.fill)
        p.drawRoundedRect(r, 7, 7)
        p.setFont(self._font)
        p.setPen(pal.label)
        fm = QFontMetricsF(self._font)
        text = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, r.width() - 32)
        p.drawText(r.adjusted(10, 0, -22, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        # chevrons
        cx, cy = r.right() - 13, r.center().y()
        pen = QPen(pal.secondary, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(cx - 3.2, cy - 2), QPointF(cx, cy - 5), QPointF(cx + 3.2, cy - 2)])
        p.drawPolyline([QPointF(cx - 3.2, cy + 2), QPointF(cx, cy + 5), QPointF(cx + 3.2, cy + 2)])


class StatusDot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.role = "tertiary"
        self.setFixedSize(8, 8)

    def set_role(self, role: str) -> None:
        if role != self.role:
            self.role = role
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(getattr(P(), self.role))
        p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
