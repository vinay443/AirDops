"""Qt application shell: tray icon, popover panel, banners, notifications."""

from __future__ import annotations

import logging
import sys
import time
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import art, theme, widgets
from .model import ViewState
from .panel import Panel, styled_menu
from .toast import Toast

log = logging.getLogger(__name__)


def _server_name() -> str:
    import getpass

    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "AirDops-" + "".join(ch for ch in user if ch.isalnum())[:32]


def signal_running_instance() -> bool:
    """Ask an already-running AirDops to open its panel. True if it answered."""
    from PySide6.QtCore import QCoreApplication

    _app = QCoreApplication.instance() or QCoreApplication(sys.argv)  # noqa: F841 - keep alive
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(800):
        return False
    sock.write(b"show")
    sock.flush()
    sock.waitForBytesWritten(800)
    sock.disconnectFromServer()
    return True


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
        self._theme_tick = 0

        self.server = QLocalServer()
        QLocalServer.removeServer(_server_name())
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if self.server.listen(_server_name()):
            self.server.newConnection.connect(self._on_local_connection)

        self.timer = QTimer()
        self.timer.setInterval(350)
        self.timer.timeout.connect(self._refresh)

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

    def open_bluetooth(self) -> None:
        self.panel.hide()
        self.core.open_bluetooth()

    def open_vbcable(self) -> None:
        self.panel.hide()
        self.core.open_vbcable()

    def diagnostics(self) -> None:
        self.panel.hide()
        self.core.diagnostics()
        self.tray.showMessage("Running Diagnostics", "The report opens in a few seconds.", app_icon(), 3000)

    def open_logs(self) -> None:
        self.panel.hide()
        self.core.open_logs()

    def open_settings_file(self) -> None:
        self.panel.hide()
        self.core.open_settings_file()

    def restore(self) -> None:
        self.core.restore()

    def quit(self) -> None:
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

    def _on_local_connection(self) -> None:
        sock = self.server.nextPendingConnection()
        if sock is None:
            return

        def read() -> None:
            if bytes(sock.readAll()).startswith(b"show"):
                self._open_panel()
            sock.disconnectFromServer()

        sock.readyRead.connect(read)

    def _open_panel(self) -> None:
        self.panel.set_state(self.core.snapshot())
        self.panel.show_at(self.tray.geometry())

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toast.hide()
            self.panel.set_state(self.core.snapshot())
            self.panel.toggle_at(self.tray.geometry())
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
        self._theme_tick += 1
        if self._theme_tick % 6:
            return
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
        if not st.connected:
            self._toast_due = None
        if self._toast_due is not None and (st.battery_known or now >= self._toast_due):
            self._toast_due = None
            if not self.panel.isVisible():
                self.toast.popup(st)

        for title, msg in self.core.pop_notifications():
            self.tray.showMessage(title, msg, app_icon(), 6000)
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

    # ---------------------------------------------------------------- run
    def run(self) -> int:
        self.core.start()
        self.tray.show()
        self.timer.start()
        if not self.background:
            welcome = ViewState(name="AirDops is running", mode=self.core.settings.mode)
            QTimer.singleShot(
                900, lambda: self.toast.popup(welcome, "AirDops is running", "Click the AirPods icon in the tray")
            )
        log.info("UI started")
        return self.app.exec()
