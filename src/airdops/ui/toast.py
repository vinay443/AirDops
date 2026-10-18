"""iPhone-style "AirPods Connected" banner that slides in above the tray."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import art, theme
from .model import ViewState
from .widgets import P, draw_bolt

W, H = 340, 80
MARGIN = 18


class Toast(QWidget):
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(W + 2 * MARGIN, H + 2 * MARGIN)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.state: Optional[ViewState] = None
        self.title = "AirPods"
        self.subtitle = "Connected"
        self._f_title = theme.font(15, QFont.Weight.DemiBold)
        self._f_sub = theme.font(12.5)
        self._f_pct = theme.font(12.5, QFont.Weight.DemiBold)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._move = QPropertyAnimation(self, b"pos", self)
        self._move.setDuration(320)
        self._move.setEasingCurve(QEasingCurve.Type.OutBack)

    def set_state(self, st: ViewState, title: Optional[str] = None, subtitle: Optional[str] = None) -> None:
        self.state = st
        self.title = title or st.name
        self.subtitle = subtitle or ("Connected · Game Mode" if st.mode == "game" else "Connected · Call Mode")
        self.update()

    def popup(self, st: ViewState, title: Optional[str] = None, subtitle: Optional[str] = None, ms: int = 4000) -> None:
        self.set_state(st, title, subtitle)
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        full = screen.geometry()
        x = avail.right() - self.width() + MARGIN - 6
        if avail.top() > full.top():  # taskbar at the top
            end = QPoint(x, avail.top() - MARGIN + 10)
            start = QPoint(x, end.y() - 24)
        else:
            end = QPoint(x, avail.bottom() - self.height() + MARGIN - 10)
            start = QPoint(x, end.y() + 24)
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._move.stop()
        self._move.setStartValue(start)
        self._move.setEndValue(end)
        self._move.start()
        self._timer.start(ms)

    def dismiss(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        try:
            self._anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._anim.finished.connect(self._after_fade)
        self._anim.start()

    def _after_fade(self) -> None:
        try:
            self._anim.finished.disconnect(self._after_fade)
        except (RuntimeError, TypeError):
            pass
        if self.windowOpacity() < 0.05:
            self.hide()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self.clicked.emit()
        self.dismiss()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._timer.stop()

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._timer.start(1800)

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(MARGIN, MARGIN, W, H)
        radius = H / 2
        p.setPen(Qt.PenStyle.NoPen)
        steps = 12
        for i in range(steps, 0, -1):
            c = QColor(0, 0, 0)
            c.setAlphaF(pal.shadow.alphaF() * (1 - i / steps) ** 2 * 0.25)
            p.setBrush(c)
            g = i * (MARGIN / steps)
            p.drawRoundedRect(card.adjusted(-g, -g + 4, g, g + 4), radius + g, radius + g)
        p.setBrush(pal.window)
        p.setPen(QPen(pal.border, 1))
        p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        art_box = QRectF(card.left() + 14, card.top() + 10, 82, 60)
        art.draw_hero(p, art_box, True, led=pal.green)

        tx = art_box.right() + 10
        p.setFont(self._f_title)
        p.setPen(pal.label)
        fm = QFontMetricsF(self._f_title)
        right_reserved = 74 if (self.state and self.state.battery_known) else 18
        title = fm.elidedText(self.title, Qt.TextElideMode.ElideRight, card.right() - tx - right_reserved)
        p.drawText(QRectF(tx, card.top() + 19, 220, 22), Qt.AlignmentFlag.AlignLeft, title)
        p.setFont(self._f_sub)
        p.setPen(pal.secondary)
        p.drawText(QRectF(tx, card.top() + 42, card.right() - tx - right_reserved, 18), Qt.AlignmentFlag.AlignLeft, self.subtitle)

        st = self.state
        if st and st.battery_known and st.lowest is not None:
            level = st.lowest
            charging = st.left_charging or st.right_charging
            color = theme.battery_color(pal, level, charging)
            bx = card.right() - 64
            by = card.center().y() - 8
            body = QRectF(bx, by, 26, 13)
            p.setPen(QPen(pal.secondary, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(body, 3.5, 3.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.secondary)
            p.drawRoundedRect(QRectF(body.right() + 1.2, by + 4, 2, 5), 1, 1)
            p.setBrush(color)
            fill = QRectF(bx + 2, by + 2, max(2.0, 22 * level / 100), 9)
            p.drawRoundedRect(fill, 2, 2)
            if charging:
                draw_bolt(p, QRectF(bx + 9, by + 1.5, 8, 10), pal.label)
            p.setFont(self._f_pct)
            p.setPen(pal.label)
            p.drawText(QRectF(bx - 4, by + 15, 40, 18), Qt.AlignmentFlag.AlignHCenter, f"{level}%")
