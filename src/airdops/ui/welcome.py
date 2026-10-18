"""First-run welcome sheet (like a macOS app's "What's New" / onboarding)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import art
from .widgets import Badge, Group, Label, P, PrimaryButton, Row, Switch, TextButton

SHADOW = 26
RADIUS = 18
WIDTH = 440
_PAD = 34
_TEXT_W = WIDTH - 2 * _PAD - 34 - 14


class _Feature(QWidget):
    def __init__(self, badge: Badge, title: str, text: str) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = Label(title, 14, QFont.Weight.DemiBold)
        d = Label(text, 12.5, role="secondary")
        d.setWordWrap(True)
        # Fixed width so word-wrapped height is known before the window shows.
        d.setFixedWidth(_TEXT_W)
        d.setFixedHeight(d.heightForWidth(_TEXT_W))
        col.addWidget(t)
        col.addWidget(d)
        self.extra = QHBoxLayout()
        self.extra.setContentsMargins(0, 2, 0, 0)
        col.addLayout(self.extra)
        lay.addLayout(col, 1)


class Welcome(QWidget):
    def __init__(
        self,
        cable_installed: bool,
        on_done: Callable[[bool], None],
        on_get_cable: Callable[[], None],
    ) -> None:
        super().__init__(None)
        self._on_done = on_done
        self._drag: Optional[QPoint] = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Welcome to AirDops")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW - 8, SHADOW, SHADOW + 8)
        card = QWidget()
        card.setFixedWidth(WIDTH)
        outer.addWidget(card)
        self.card = card
        lay = QVBoxLayout(card)
        lay.setContentsMargins(_PAD, 30, _PAD, 26)
        lay.setSpacing(0)

        icon = QLabel()
        pm = QPixmap.fromImage(art.app_icon_image(192))
        pm.setDevicePixelRatio(2.0)
        icon.setPixmap(pm)
        icon.setFixedSize(96, 96)
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        title = Label("Welcome to AirDops", 24, QFont.Weight.Bold)
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title)
        lay.addSpacing(6)
        sub = Label("Full-quality AirPods sound on Windows, even while you voice chat.", 13.5, role="secondary")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        sub.setFixedWidth(WIDTH - 2 * _PAD)
        sub.setFixedHeight(sub.heightForWidth(WIDTH - 2 * _PAD))
        lay.addWidget(sub)
        lay.addSpacing(24)

        f1 = _Feature(
            Badge("green", "buds"),
            "Stereo that stays stereo",
            "AirDops stops games and chat apps from switching your AirPods into low-quality call mode.",
        )
        f2 = _Feature(
            Badge("accent", "mic"),
            "Your laptop mic, cleaned up",
            "AI noise suppression removes keyboard clicks and fan noise before anyone hears them.",
        )
        if cable_installed:
            ok = Label("✓  VB-Cable is installed", 12, QFont.Weight.Medium, role="green")
            f2.extra.addWidget(ok)
        else:
            get = TextButton("Get VB-Cable (free) to enable this", size=12)
            get.clicked.connect(on_get_cable)
            f2.extra.setContentsMargins(-8, 0, 0, 0)
            f2.extra.addWidget(get)
        f2.extra.addStretch(1)
        f3 = _Feature(
            Badge("orange", "wave"),
            "Battery and ear detection",
            "See every battery level at a glance. Media pauses when you take an AirPod out.",
        )
        for f in (f1, f2, f3):
            lay.addWidget(f)
            lay.addSpacing(16)
        lay.addSpacing(4)

        g = Group()
        self.sw_login = Switch()
        self.sw_login.setChecked(True)
        g.add(Row("Open at Login", "Start quietly in the tray when you sign in", self.sw_login))
        lay.addWidget(g)
        lay.addSpacing(22)

        btn = PrimaryButton("Continue")
        btn.clicked.connect(self._finish)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(12)
        foot = Label("AirDops lives in the system tray — click the AirPods icon anytime.", 11.5, role="tertiary")
        foot.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        foot.setWordWrap(True)
        foot.setFixedWidth(WIDTH - 2 * _PAD)
        foot.setFixedHeight(foot.heightForWidth(WIDTH - 2 * _PAD))
        lay.addWidget(foot)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(260)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _finish(self) -> None:
        self.hide()
        self._on_done(self.sw_login.isChecked())

    def present(self) -> None:
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    # frameless: drag anywhere on the card
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._drag = None

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._finish()

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(self.card.geometry())
        p.setPen(Qt.PenStyle.NoPen)
        steps = 18
        for i in range(steps, 0, -1):
            c = QColor(0, 0, 0)
            c.setAlphaF(pal.shadow.alphaF() * (1 - i / steps) ** 2 * 0.22)
            p.setBrush(c)
            grow = i * (SHADOW / steps)
            p.drawRoundedRect(card.adjusted(-grow, -grow + 8, grow, grow + 8), RADIUS + grow, RADIUS + grow)
        p.setBrush(pal.window)
        p.setPen(pal.border)
        p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
