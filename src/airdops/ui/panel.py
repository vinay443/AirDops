"""The main popover panel, opened from the tray icon (like macOS Control Center)."""

from __future__ import annotations

import time
from typing import Optional, Protocol

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from . import art, theme
from .model import ViewState
from .widgets import (
    BatteryTile,
    Group,
    Label,
    LevelMeter,
    Slider,
    P,
    PopupButton,
    Row,
    Segmented,
    StatusDot,
    Switch,
    TextButton,
)

CARD_W = 344
SHADOW = 22
RADIUS = 16


class Actions(Protocol):
    def set_mode(self, mode: str) -> None: ...
    def set_setting(self, name: str, value: bool) -> None: ...
    def set_mic(self, name: str) -> None: ...
    def set_gain(self, db: float) -> None: ...
    def set_trigger(self, trigger: str) -> None: ...
    def open_bluetooth(self) -> None: ...
    def open_sound(self) -> None: ...
    def open_vbcable(self) -> None: ...
    def diagnostics(self) -> None: ...
    def open_logs(self) -> None: ...
    def open_settings_file(self) -> None: ...
    def restore(self) -> None: ...
    def quit(self) -> None: ...


def styled_menu(parent: QWidget) -> QMenu:
    """A QMenu that looks like a macOS context menu (rounded, padded, accent hover)."""
    pal = P()
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    m.setFont(theme.font(13))
    bg = pal.group.name(QColor.NameFormat.HexArgb) if not pal.dark else QColor("#2C2C2E").name()
    fg = pal.label.name(QColor.NameFormat.HexArgb)
    dis = pal.tertiary.name(QColor.NameFormat.HexArgb)
    sep = pal.separator.name(QColor.NameFormat.HexArgb)
    border = pal.border.name(QColor.NameFormat.HexArgb)
    acc = pal.accent.name()
    m.setStyleSheet(
        f"""
        QMenu {{ background: {bg}; border: 1px solid {border}; border-radius: 10px; padding: 5px; color: {fg}; }}
        QMenu::item {{ padding: 6px 22px 6px 24px; border-radius: 6px; margin: 0px; }}
        QMenu::item:selected {{ background: {acc}; color: white; }}
        QMenu::item:disabled {{ color: {dis}; }}
        QMenu::separator {{ height: 1px; background: {sep}; margin: 5px 10px; }}
        QMenu::indicator {{ width: 14px; height: 14px; left: 6px; }}
        """
    )
    return m


class HeroArt(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.connected = False
        self.setFixedSize(210, 100)

    def set_connected(self, on: bool) -> None:
        if on != self.connected:
            self.connected = on
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        art.draw_hero(p, QRectF(self.rect()).adjusted(8, 2, -8, -2), self.connected, led=P().green)


def section(title: str) -> Label:
    lab = Label(title, 12, QFont.Weight.DemiBold, role="secondary")
    lab.setContentsMargins(16, 0, 0, 0)
    return lab


class Panel(QWidget):
    def __init__(self, actions: Actions) -> None:
        super().__init__(None)
        self.actions = actions
        self.state: Optional[ViewState] = None
        self._menu_open = False
        self._hidden_at = 0.0
        self._anchor: Optional[QRect] = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("AirDops")
        self._build()
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(170)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(220)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ------------------------------------------------------------- build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW - 6, SHADOW, SHADOW + 6)
        card = QWidget()
        card.setFixedWidth(CARD_W)
        outer.addWidget(card)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 12px 2px 12px 0; }"
            "QScrollBar::handle:vertical { background: rgba(128,128,128,0.45); border-radius: 3px; min-height: 30px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"
        )
        card_lay.addWidget(self.scroll)
        content = QWidget()
        content.setAutoFillBackground(False)
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.scroll.setWidget(content)
        self.content = content
        lay = QVBoxLayout(content)
        lay.setContentsMargins(14, 14, 14, 10)
        lay.setSpacing(0)

        # header
        self.hero = HeroArt()
        lay.addWidget(self.hero, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)
        self.name = Label("AirPods", 19, QFont.Weight.Bold)
        self.name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.name)
        status = QHBoxLayout()
        status.setSpacing(6)
        status.addStretch(1)
        self.dot = StatusDot()
        self.status = Label("Not Connected", 12.5, role="secondary")
        status.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        status.addWidget(self.status)
        status.addStretch(1)
        lay.addSpacing(2)
        lay.addLayout(status)
        lay.addSpacing(12)

        # batteries / not-connected hint
        self.batteries = QWidget()
        bl = QHBoxLayout(self.batteries)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)
        bl.addStretch(1)
        self.t_left = BatteryTile("left", "Left")
        self.t_right = BatteryTile("right", "Right")
        self.t_case = BatteryTile("case", "Case")
        for t in (self.t_left, self.t_right, self.t_case):
            bl.addWidget(t)
        bl.addStretch(1)
        lay.addWidget(self.batteries)

        self.hint = QWidget()
        hl = QVBoxLayout(self.hint)
        hl.setContentsMargins(12, 0, 12, 4)
        hl.setSpacing(4)
        self.hint_text = Label("", 12.5, role="secondary")
        self.hint_text.setWordWrap(True)
        self.hint_text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        hl.addWidget(self.hint_text)
        self.bt_button = TextButton("Bluetooth Settings…")
        self.bt_button.clicked.connect(self.actions.open_bluetooth)
        hl.addWidget(self.bt_button, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.hint)
        lay.addSpacing(10)

        # mode
        self.mode = Segmented(["Game Mode", "Call Mode"])
        self.mode.changed.connect(lambda i: self.actions.set_mode("game" if i == 0 else "call"))
        mode_wrap = QHBoxLayout()
        mode_wrap.setContentsMargins(2, 0, 2, 0)
        mode_wrap.addWidget(self.mode)
        lay.addLayout(mode_wrap)
        lay.addSpacing(7)
        self.mode_caption = Label("", 11.5, role="secondary")
        self.mode_caption.setWordWrap(True)
        self.mode_caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.mode_caption.setContentsMargins(10, 0, 10, 0)
        lay.addWidget(self.mode_caption)
        lay.addSpacing(12)

        # microphone
        lay.addWidget(section("Microphone"))
        lay.addSpacing(6)
        g = Group()
        self.mic_button = PopupButton(self._open_mic_menu)
        self.row_mic = g.add(Row("Input", accessory=self.mic_button))
        self.meter = LevelMeter()
        self.row_level = g.add(Row("Input Level", accessory=self.meter))
        boost = QWidget()
        bl2 = QHBoxLayout(boost)
        bl2.setContentsMargins(0, 0, 0, 0)
        bl2.setSpacing(8)
        self.boost = Slider(-6, 18, 1)
        self.boost.setFixedWidth(118)
        self.boost_label = Label("0 dB", 12, QFont.Weight.Medium, role="secondary")
        self.boost_label.setFixedWidth(44)
        self.boost_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bl2.addWidget(self.boost)
        bl2.addWidget(self.boost_label)
        self.boost.valueChanged.connect(self._boost_preview)
        self.boost.released.connect(lambda v: self.actions.set_gain(float(v)))
        self.row_boost = g.add(Row("Mic Boost", accessory=boost))
        self.sw_ns = Switch()
        self.row_ns = g.add(Row("Noise Suppression", "Removes keyboard and fan noise", self.sw_ns))
        self.sw_gate = Switch()
        self.row_gate = g.add(Row("Voice Gate", "Mutes the mic between words", self.sw_gate))
        lay.addWidget(g)
        self.cable_link = TextButton("Get VB-Cable (free) to turn on noise suppression", size=11.5)
        self.cable_link.clicked.connect(self.actions.open_vbcable)
        lay.addSpacing(2)
        lay.addWidget(self.cable_link, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(8)

        # sound & airpods
        lay.addWidget(section("Sound & AirPods"))
        lay.addSpacing(6)
        g2 = Group()
        self.sw_duck = Switch()
        g2.add(Row("Keep Game Volume", "No ducking during voice chat", self.sw_duck))
        self.sw_ear = Switch()
        g2.add(Row("Automatic Ear Detection", "Pauses when an AirPod comes out", self.sw_ear))
        self.trigger_button = PopupButton(self._open_trigger_menu)
        self.row_trigger = g2.add(Row("Pause When", accessory=self.trigger_button))
        self.sw_batt = Switch()
        g2.add(Row("Low Battery Alerts", "", self.sw_batt))
        self.sw_login = Switch()
        g2.add(Row("Open at Login", "", self.sw_login))
        lay.addWidget(g2)
        lay.addSpacing(8)

        # footer
        foot = QHBoxLayout()
        foot.setContentsMargins(4, 0, 0, 0)
        self.version = Label("", 11, role="tertiary")
        foot.addWidget(self.version)
        foot.addStretch(1)
        more = TextButton("More", role="secondary", size=12.5)
        more.clicked.connect(lambda: self._open_more(more))
        quit_btn = TextButton("Quit", role="secondary", size=12.5)
        quit_btn.clicked.connect(self.actions.quit)
        foot.addWidget(more)
        foot.addWidget(quit_btn)
        lay.addLayout(foot)

        for sw, name in (
            (self.sw_ns, "noise_suppression"),
            (self.sw_gate, "voice_gate"),
            (self.sw_duck, "prevent_ducking"),
            (self.sw_ear, "auto_pause"),
            (self.sw_batt, "battery_notifications"),
            (self.sw_login, "start_with_windows"),
        ):
            sw.toggled.connect(lambda on, n=name: self.actions.set_setting(n, on))

        self.card = card
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------ menus
    def _exec_menu(self, menu: QMenu, at: QPoint) -> None:
        self._menu_open = True
        try:
            menu.exec(at)
        finally:
            self._menu_open = False
            self.activateWindow()

    def _open_mic_menu(self, button: PopupButton) -> None:
        st = self.state
        if st is None:
            return
        m = styled_menu(self)
        auto = m.addAction("Automatic (built-in mic)")
        auto.setCheckable(True)
        auto.setChecked(not st.preferred_mic)
        auto.triggered.connect(lambda: self.actions.set_mic(""))
        if st.mics:
            m.addSeparator()
        for name in st.mics:
            a = m.addAction(name)
            a.setCheckable(True)
            a.setChecked(bool(st.preferred_mic) and st.preferred_mic.lower() in name.lower())
            a.triggered.connect(lambda _=False, n=name: self.actions.set_mic(n))
        self._exec_menu(m, button.mapToGlobal(QPoint(0, button.height() + 4)))

    def _boost_preview(self, v: float) -> None:
        self.boost_label.setText(f"{v:+.0f} dB" if v else "0 dB")

    def update_level(self, level: float) -> None:
        if self.isVisible() and not self.row_level.isHidden():
            self.meter.set_level(level)

    def _open_trigger_menu(self, button: PopupButton) -> None:
        st = self.state
        m = styled_menu(self)
        for key, text in (("one", "Either AirPod Is Removed"), ("both", "Both AirPods Are Removed")):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked(bool(st) and st.auto_pause_trigger == key)
            a.triggered.connect(lambda _=False, k=key: self.actions.set_trigger(k))
        self._exec_menu(m, button.mapToGlobal(QPoint(0, button.height() + 4)))

    def _open_more(self, anchor: QWidget) -> None:
        m = styled_menu(self)
        m.addAction("Bluetooth Settings…", self.actions.open_bluetooth)
        m.addAction("Sound Settings…", self.actions.open_sound)
        if self.state and self.state.hotkey:
            hk = m.addAction(f"Switch Game/Call Mode:  {self.state.hotkey}")
            hk.setEnabled(False)
        m.addSeparator()
        m.addAction("Run Diagnostics", self.actions.diagnostics)
        m.addAction("Open Log Folder", self.actions.open_logs)
        m.addAction("Edit Settings File", self.actions.open_settings_file)
        m.addSeparator()
        m.addAction("Restore Windows Audio Settings", self.actions.restore)
        self._exec_menu(m, anchor.mapToGlobal(QPoint(0, anchor.height() + 4)))

    # ----------------------------------------------------------- update
    def set_state(self, st: ViewState) -> None:
        if st == self.state:
            return
        first = self.state is None
        self.state = st
        self.hero.set_connected(st.connected)
        self.name.setText(st.name if st.connected else (st.name or "AirPods"))
        self.status.setText(st.status_line())
        self.dot.set_role("green" if st.connected else "tertiary")

        show_batt = st.connected and st.battery_known
        self.batteries.setVisible(show_batt)
        self.hint.setVisible(not show_batt)
        if show_batt:
            if st.single_unit:
                self.t_left.caption = "Battery"
                self.t_right.hide()
                self.t_case.hide()
            else:
                self.t_left.caption = "Left"
                self.t_right.show()
                self.t_case.show()
            self.t_left.set_value(st.left, st.left_charging)
            self.t_right.set_value(st.right, st.right_charging)
            self.t_case.set_value(st.case, st.case_charging)
        elif st.connected:
            self.hint_text.setText("Battery levels appear when your AirPods are out of the case nearby.")
            self.bt_button.hide()
        else:
            self.hint_text.setText("Open the case near your PC, or connect your AirPods in Bluetooth settings.")
            self.bt_button.show()

        self.mode.set_index(0 if st.mode == "game" else 1, animate=not first and self.isVisible())
        self.mode_caption.setText(st.mode_caption())

        game = st.mode == "game"
        self.mic_button.setText(st.mic_name if (st.connected and st.mic_name) else (st.preferred_mic or "Automatic"))
        self.row_mic.setEnabled(game)
        self.sw_ns.setChecked(st.noise_suppression)
        self.row_ns.setEnabled(game and st.cable_installed)
        ns_sub = "Removes keyboard and fan noise"
        if st.connected and game and st.noise_suppression and st.ns_active:
            ns_sub = "On · cleaning up your voice"
        self.row_ns.set_subtitle(ns_sub)
        live = st.connected and game and st.ns_active
        self.row_level.setVisible(live)
        self.row_boost.setVisible(live)
        if not self.boost._drag:
            self.boost.set_value(st.mic_gain_db)
            self._boost_preview(st.mic_gain_db)
        self.sw_gate.setChecked(st.voice_gate)
        self.row_gate.setEnabled(game and st.cable_installed and st.noise_suppression)
        self.cable_link.setVisible(not st.cable_installed)
        self.sw_duck.setChecked(st.prevent_ducking)
        self.sw_ear.setChecked(st.auto_pause)
        self.row_trigger.setVisible(st.auto_pause)
        self.trigger_button.setText("Either AirPod Is Removed" if st.auto_pause_trigger == "one" else "Both Are Removed")
        self.sw_batt.setChecked(st.battery_notifications)
        self.sw_login.setChecked(st.start_with_windows)
        self.version.setText(f"AirDops {st.version}")
        self._fit()
        self.update()

    def _fit(self, max_card_h: Optional[int] = None) -> None:
        """Card as tall as its content, but never taller than the screen allows."""
        self.content.adjustSize()
        want = self.content.sizeHint().height()
        if max_card_h is None:
            screen = self.screen() or QGuiApplication.primaryScreen()
            max_card_h = screen.availableGeometry().height() - 2 * SHADOW - 16 if screen else want
        h = min(want, max_card_h)
        if h == self.card.height() and self.card.minimumHeight() == h:
            return
        old = self.geometry()
        self.scroll.setFixedHeight(h)
        self.card.setFixedHeight(h)
        self.adjustSize()
        # While open above a bottom taskbar, grow upwards so the panel never
        # slides under the taskbar when rows appear or disappear.
        if self.isVisible() and self._slide.state() != QPropertyAnimation.State.Running:
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen and old.center().y() > screen.availableGeometry().center().y():
                self.move(old.x(), old.bottom() - self.height() + 1)

    # ---------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        pal = P()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(self.card.geometry())
        # layered soft shadow
        p.setPen(Qt.PenStyle.NoPen)
        steps = 16
        for i in range(steps, 0, -1):
            a = pal.shadow.alphaF() * (1 - i / steps) ** 2 * 0.22
            c = QColor(0, 0, 0)
            c.setAlphaF(a)
            p.setBrush(c)
            grow = i * (SHADOW / steps)
            p.drawRoundedRect(card.adjusted(-grow, -grow + 6, grow, grow + 6), RADIUS + grow, RADIUS + grow)
        p.setBrush(pal.window)
        p.setPen(pal.border)
        p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)

    # ---------------------------------------------------------- showing
    def toggle_at(self, anchor: Optional[QRect]) -> None:
        if self.isVisible():
            self.hide()
            return
        # Clicking the tray icon while open first deactivates (hides) the panel;
        # don't immediately re-open it on that same click.
        if time.monotonic() - self._hidden_at < 0.35:
            return
        self.show_at(anchor)

    def hideEvent(self, e) -> None:  # noqa: N802
        self._hidden_at = time.monotonic()
        super().hideEvent(e)

    def show_at(self, anchor: Optional[QRect]) -> None:
        self._anchor = anchor
        ref = anchor.center() if anchor and anchor.isValid() and not anchor.isEmpty() else QCursor.pos()
        screen = QGuiApplication.screenAt(ref) or QGuiApplication.primaryScreen()
        self._fit(screen.availableGeometry().height() - 2 * SHADOW - 16)
        target = self._target_pos(anchor)
        self.setWindowOpacity(0.0)
        start = QPoint(target.x(), target.y() + (10 if target.y() > 200 else -10))
        self.move(start)
        self.show()
        self.raise_()
        self.activateWindow()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._slide.stop()
        self._slide.setStartValue(start)
        self._slide.setEndValue(target)
        self._slide.start()

    def _target_pos(self, anchor: Optional[QRect]) -> QPoint:
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(anchor.center() if anchor and anchor.isValid() else cursor)
        screen = screen or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        full = screen.geometry()
        w, h = self.width(), self.height()
        ref = anchor.center() if anchor and anchor.isValid() and not anchor.isEmpty() else cursor
        x = ref.x() - w // 2
        # Taskbar edge = where the available area is smaller than the screen.
        if avail.top() > full.top():
            y = avail.top() - SHADOW + 14
        elif avail.left() > full.left():
            x = avail.left() - SHADOW + 14
            y = ref.y() - h // 2
        elif avail.right() < full.right():
            x = avail.right() - w + SHADOW - 14
            y = ref.y() - h // 2
        else:
            y = avail.bottom() - h + SHADOW - 8
        x = max(avail.left() - SHADOW + 8, min(x, avail.right() - w + SHADOW - 8))
        y = max(avail.top() - SHADOW + 8, min(y, avail.bottom() - h + SHADOW))
        return QPoint(x, y)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WindowDeactivate and not self._menu_open and self.isVisible():
            self.hide()
        return super().event(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)
