"""Qt application shell: tray icon, popover panel, banners, notifications."""

from __future__ import annotations

import logging
import sys
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import art, theme, widgets
from .model import ViewState
from .panel import Panel, styled_menu
from .toast import Toast

log = logging.getLogger(__name__)


class _ShowBridge(QObject):
    """Carries signals from background threads to the UI thread (queued)."""

    show = Signal()  # another launch asked for the panel
    changed = Signal()  # the engine has news (device, battery, notification)


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(art.app_icon_image(size)))
    return icon


class Shell:
    def __init__(self, core, background: bool = False) -> None:
        self.core = core
        self.background = background
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("AirDops")
        self.app.setApplicationDisplayName("AirDops")
        theme.load_fonts()
        self.app.setFont(theme.font(13))
        self.app.setWindowIcon(app_icon())
        self._palette = theme.current()
        widgets.set_palette(self._palette)
        self._dark_taskbar = theme.taskbar_is_dark()

        self.panel = Panel(self)
        self.toast = Toast()
        self.toast.clicked.connect(self._open_panel)
        self.tray = QSystemTrayIcon(self._tray_icon(False, None))
        self.tray.setToolTip("AirDops")
        self.tray.activated.connect(self._on_tray)
        self._last: Optional[ViewState] = None
        self._toast_due: Optional[float] = None
        self._theme_checked = 0.0

        # A second launch of AirDops signals this so the panel opens (see instance.py).
        from ..instance import ShowListener

        self._show_bridge = _ShowBridge()
        self._show_bridge.show.connect(self._open_panel)
        self.show_listener = ShowListener(self._show_bridge.show.emit)
        self.show_listener.start()

        # The engine signals changes (see Core.on_change), so this timer is only
        # housekeeping: theme changes, stale battery readings, banner timing.
        self._show_bridge.changed.connect(self._refresh)
        self.core.on_change = self._show_bridge.changed.emit
        self.timer = QTimer()
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self._refresh)
        # Fast timer just for the live mic meter while the panel is open.
        self.meter_timer = QTimer()
        self.meter_timer.setInterval(50)
        self.meter_timer.timeout.connect(self._tick_meter)
        self._banners: list[tuple[str, str]] = []
        self.welcome = None

        from .hotkey import GlobalHotkey

        self.hotkey = GlobalHotkey(self._on_hotkey)

    # --------------------------------------------------------- actions (Panel)
    def set_mode(self, mode: str) -> None:
        self.core.set_mode(mode)
        self._refresh()

    def set_setting(self, name: str, value: bool) -> None:
        self.core.set_setting(name, value)
        self._refresh()

    def set_mic(self, name: str) -> None:
        self.core.set_mic(name)
        self._refresh()

    def set_gain(self, db: float) -> None:
        self.core.set_gain(db)
        self._refresh()

    def set_trigger(self, trigger: str) -> None:
        self.core.set_trigger(trigger)
        self._refresh()

    def open_sound(self) -> None:
        self.panel.hide()
        self.core.open_sound()

    def open_bluetooth(self) -> None:
        self.panel.hide()
        self.core.open_bluetooth()

    def open_vbcable(self) -> None:
        self.panel.hide()
        self.core.open_vbcable()

    def diagnostics(self) -> None:
        self.panel.hide()
        self.core.diagnostics()
        self.toast.popup(self.core.snapshot(), "Running Diagnostics", "The report opens in about 10 seconds", ms=3500)

    def open_logs(self) -> None:
        self.panel.hide()
        self.core.open_logs()

    def open_settings_file(self) -> None:
        self.panel.hide()
        self.core.open_settings_file()

    def restore(self) -> None:
        self.core.restore()

    def quit(self) -> None:
        self.hotkey.unregister()
        self.show_listener.stop()
        self.meter_timer.stop()
        self.panel.hide()
        self.toast.hide()
        self.timer.stop()
        self.tray.hide()
        self.core.stop()
        self.app.quit()

    # -------------------------------------------------------------- tray
    def _tray_icon(self, connected: bool, battery: Optional[int]) -> QIcon:
        icon = QIcon()
        for size in (16, 20, 24, 32, 40, 48):
            icon.addPixmap(art.tray_pixmap(size, self._dark_taskbar, connected, battery))
        return icon

    def _open_panel(self) -> None:
        self.panel.set_state(self.core.snapshot())
        self.panel.show_at(self.tray.geometry())
        self._refresh()  # starts the level meter right away if needed

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toast.hide()
            self.panel.set_state(self.core.snapshot())
            self.panel.toggle_at(self.tray.geometry())
            self._refresh()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self._context_menu()

    def _context_menu(self) -> None:
        from PySide6.QtGui import QCursor

        st = self.core.snapshot()
        m = styled_menu(self.panel)
        head = m.addAction(f"{st.name} — {'Connected' if st.connected else 'Not Connected'}")
        head.setEnabled(False)
        if st.connected and st.battery_known:
            parts = []
            if st.single_unit:
                parts.append(f"Battery {st.left}%")
            else:
                for label, v in (("L", st.left), ("R", st.right), ("Case", st.case)):
                    if v is not None:
                        parts.append(f"{label} {v}%")
            b = m.addAction("   ".join(parts))
            b.setEnabled(False)
        m.addSeparator()
        m.addAction("Open AirDops", self._open_panel)
        m.addSeparator()
        g = m.addAction("Game Mode", lambda: self.set_mode("game"))
        g.setCheckable(True)
        g.setChecked(st.mode == "game")
        c = m.addAction("Call Mode", lambda: self.set_mode("call"))
        c.setCheckable(True)
        c.setChecked(st.mode == "call")
        m.addSeparator()
        m.addAction("Quit AirDops", self.quit)
        m.exec(QCursor.pos())

    # ------------------------------------------------------------ refresh
    def _check_theme(self) -> None:
        now = time.monotonic()
        if now - self._theme_checked < 1.9:
            return
        self._theme_checked = now
        pal = theme.current()
        dark_tb = theme.taskbar_is_dark()
        if pal is not self._palette:
            self._palette = pal
            widgets.set_palette(pal)
            self.panel.update()
            for w in self.panel.findChildren(widgets.QWidget):
                w.update()
            self.toast.update()
        if dark_tb != self._dark_taskbar:
            self._dark_taskbar = dark_tb
            self._last = None  # force tray icon redraw

    def _refresh(self) -> None:
        self._check_theme()
        st = self.core.snapshot()
        last = self._last
        if last is None or (st.connected, st.lowest, st.battery_known) != (last.connected, last.lowest, last.battery_known):
            self.tray.setIcon(self._tray_icon(st.connected, st.lowest))
        if last is None or st != last:
            self.tray.setToolTip(self._tooltip(st))
            if self.panel.isVisible():
                self.panel.set_state(st)

        # "Connected" banner, like an iPhone. Wait briefly for the battery level.
        now = time.monotonic()
        if last is not None and st.connected and not last.connected:
            self._toast_due = now + 3.0
            QTimer.singleShot(3050, self._refresh)
        if not st.connected:
            self._toast_due = None
        if self._toast_due is not None and (st.battery_known or now >= self._toast_due):
            self._toast_due = None
            if not self.panel.isVisible():
                self.toast.popup(st)

        # Alerts use the same Apple-style banner, one at a time.
        self._banners.extend(self.core.pop_notifications())
        if self._banners and not self.toast.isVisible() and self._toast_due is None:
            title, msg = self._banners.pop(0)
            self.toast.popup(st, title, msg, ms=6000)
        # The 50 ms level meter only runs while it is on screen.
        want_meter = self.panel.isVisible() and st.ns_active
        if want_meter != self.meter_timer.isActive():
            if want_meter:
                self.meter_timer.start()
            else:
                self.meter_timer.stop()
        self._last = st

    @staticmethod
    def _tooltip(st: ViewState) -> str:
        if not st.connected:
            return "AirDops — AirPods not connected"
        line = f"{st.name} — {'Game' if st.mode == 'game' else 'Call'} Mode"
        if st.battery_known:
            if st.single_unit:
                line += f"\nBattery {st.left}%"
            else:
                bits = [f"L {st.left}%" if st.left is not None else "", f"R {st.right}%" if st.right is not None else ""]
                line += "\n" + "  ".join(b for b in bits if b)
        return line

    def _tick_meter(self) -> None:
        if not self.panel.isVisible():
            self.meter_timer.stop()
            return
        try:
            self.panel.update_level(self.core.mic_level())
        except Exception:  # noqa: BLE001
            self.meter_timer.stop()

    def _on_hotkey(self) -> None:
        mode = self.core.toggle_mode()
        st = self.core.snapshot()
        self.toast.popup(
            st,
            "Game Mode" if mode == "game" else "Call Mode",
            "Full-quality sound · laptop mic" if mode == "game" else "Using the AirPods microphone",
            ms=2200,
        )
        self._refresh()

    def _show_welcome(self, waited: float = 0.0) -> None:
        from .welcome import Welcome

        # Wait for the first device scan so "VB-Cable installed" is accurate.
        if not getattr(self.core.controller, "endpoints", None) and waited < 4.0:
            QTimer.singleShot(250, lambda: self._show_welcome(waited + 0.25))
            return
        st = self.core.snapshot()

        def done(open_at_login: bool) -> None:
            self.core.finish_onboarding(open_at_login)
            self.welcome = None
            self._open_panel()

        self.welcome = Welcome(st.cable_installed, done, self.core.open_vbcable)
        self.welcome.present()

    # ---------------------------------------------------------------- run
    def run(self) -> int:
        self.core.start()
        # Windows sign-out / shutdown: still put the audio settings back.
        self.app.aboutToQuit.connect(self.core.stop)
        self.tray.show()
        self.timer.start()
        hk = getattr(self.core.settings, "hotkey", "")
        if hk:
            self.hotkey.register(hk)
        if not getattr(self.core.settings, "onboarded", True):
            QTimer.singleShot(500, self._show_welcome)
        elif not self.background:
            running = ViewState(name="AirDops is running", mode=self.core.settings.mode)
            QTimer.singleShot(
                900, lambda: self.toast.popup(running, "AirDops is running", "Click the AirPods icon in the tray")
            )
        log.info("UI started")
        return self.app.exec()
