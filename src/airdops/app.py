"""AirDops tray application (Windows)."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from . import __version__, config, icons, startup
from .audio.router import CALL, GAME
from .ble.advert import PodsStatus, family
from .controller import Controller
from .earsense import PAUSE, RESUME, EarDetector

log = logging.getLogger(__name__)

BATTERY_STALE_S = 90.0
NOTIFY_COOLDOWN_S = 600.0


class _WinAudio:
    """Adapter from the endpoints module to the controller's backend protocol."""

    def __init__(self) -> None:
        from .audio import endpoints

        self._ep = endpoints

    def list_endpoints(self):
        return self._ep.list_endpoints()

    def get_default(self, flow, role):
        return self._ep.get_default(flow, role)

    def set_default(self, endpoint_id, roles):
        return self._ep.set_default(endpoint_id, tuple(roles))

    def set_enabled(self, endpoint_id, enabled):
        return self._ep.set_enabled(endpoint_id, enabled)


def _pipeline_factory(mic_name: str, cable_name: str, voice_gate: bool, gain_db: float):
    from .denoise.pipeline import NoisePipeline

    return NoisePipeline(mic_name, cable_name, voice_gate, gain_db)


def _fmt_batt(value: Optional[int], charging: bool) -> str:
    if value is None:
        return "--"
    return f"{value}%" + (" ⚡" if charging else "")


class App:
    def __init__(self, background: bool = False) -> None:
        import pystray

        from .audio import ducking
        from .ble.scanner import BatteryMonitor

        self.background = background
        self.settings = config.load_settings()
        self.state = config.load_state()
        self.controller = Controller(
            self.settings,
            self.state,
            _WinAudio(),
            ducking,
            _pipeline_factory,
            config.save_state,
            notify=self.notify,
        )
        self.ear = EarDetector(trigger=self.settings.auto_pause_trigger)
        self.monitor = BatteryMonitor(self._on_pods, self.settings.ble_min_rssi)
        self.pods: Optional[PodsStatus] = None
        self.pods_at = 0.0
        self._paused_apps: list[str] = []
        self._low_warned: set[str] = set()
        self._last_notified: dict[str, float] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._last_menu_key: tuple = ()
        self._pystray = pystray
        self.icon = pystray.Icon("AirDops", icons.render("off"), "AirDops", menu=self._build_menu())

    # ------------------------------------------------------------ helpers
    def notify(self, title: str, message: str) -> None:
        now = time.monotonic()
        key = title + "|" + message
        if now - self._last_notified.get(key, -1e9) < NOTIFY_COOLDOWN_S:
            return
        self._last_notified[key] = now
        log.info("notify: %s - %s", title, message)
        try:
            self.icon.notify(message, title)
        except Exception:  # noqa: BLE001
            log.debug("notification failed", exc_info=True)

    def _pods_fresh(self) -> Optional[PodsStatus]:
        if self.pods and time.monotonic() - self.pods_at < BATTERY_STALE_S:
            return self.pods
        return None

    # ---------------------------------------------------------- menu text
    def _title_text(self) -> str:
        st = self.controller.status
        if not st.connected:
            return "AirPods not connected"
        pods = self._pods_fresh()
        name = pods.model_name if pods else st.device_name
        return f"{name} — connected"

    def _battery_text(self) -> str:
        pods = self._pods_fresh()
        if not pods or not self.controller.status.connected:
            return ""
        if pods.single_unit:
            return f"Battery {_fmt_batt(pods.left_battery, pods.left_charging)}"
        return (
            f"L {_fmt_batt(pods.left_battery, pods.left_charging)}   "
            f"R {_fmt_batt(pods.right_battery, pods.right_charging)}   "
            f"Case {_fmt_batt(pods.case_battery, pods.case_charging)}"
        )

    def _mic_text(self) -> str:
        st = self.controller.status
        if not st.connected:
            return ""
        text = f"Mic: {st.mic_name or 'none'}"
        if st.note:
            text += f" ({st.note})"
        return text

    def _tooltip(self) -> str:
        parts = ["AirDops", self._title_text()]
        b = self._battery_text()
        if b:
            parts.append(b)
        return "\n".join(parts)[:120]

    # ------------------------------------------------------------- actions
    def _set_mode(self, mode: str):
        def handler(icon, item):
            self.controller.set_mode(mode)
            config.save_settings(self.settings)
            self._wake.set()

        return handler

    def _toggle(self, name: str):
        def handler(icon, item):
            setattr(self.settings, name, not getattr(self.settings, name))
            config.save_settings(self.settings)
            self.controller.settings_changed()
            self._wake.set()

        return handler

    def _checked(self, name: str):
        return lambda item: bool(getattr(self.settings, name))

    def _toggle_startup(self, icon, item) -> None:
        startup.set_enabled(not startup.is_enabled())

    def _open_settings(self, icon, item) -> None:
        os.startfile(str(config.settings_path()))  # type: ignore[attr-defined]

    def _open_logs(self, icon, item) -> None:
        config.log_dir().mkdir(parents=True, exist_ok=True)
        os.startfile(str(config.log_dir()))  # type: ignore[attr-defined]

    def _reload_settings(self, icon, item) -> None:
        fresh = config.load_settings()
        for field_name, value in vars(fresh).items():
            setattr(self.settings, field_name, value)
        self.ear.trigger = self.settings.auto_pause_trigger
        self.monitor.min_rssi = self.settings.ble_min_rssi
        self.controller.settings_changed()
        self._wake.set()

    def _diagnostics(self, icon, item) -> None:
        from .diagnostics import run_and_open

        threading.Thread(target=run_and_open, name="airdops-diag", daemon=True).start()

    def _restore(self, icon, item) -> None:
        # Switch to call mode so we don't immediately re-apply game mode.
        self.controller.set_mode(CALL)
        config.save_settings(self.settings)
        self.controller.restore_all()
        self.notify("Windows audio restored", "AirDops switched to Call mode and undid its changes.")
        self._wake.set()

    def _quit(self, icon, item) -> None:
        self._stop.set()
        self._wake.set()
        if self._worker:
            self._worker.join(timeout=15)
        self.monitor.shutdown()
        icon.stop()

    def _build_menu(self):
        Menu = self._pystray.Menu
        Item = self._pystray.MenuItem
        s = self.settings
        return Menu(
            Item(lambda i: self._title_text(), None, enabled=False),
            Item(lambda i: self._battery_text(), None, enabled=False, visible=lambda i: bool(self._battery_text())),
            Item(lambda i: self._mic_text(), None, enabled=False, visible=lambda i: bool(self._mic_text())),
            Menu.SEPARATOR,
            Item(
                "Game mode (full-quality sound, laptop mic)",
                self._set_mode(GAME),
                checked=lambda i: s.mode == GAME,
                radio=True,
            ),
            Item("Call mode (use the AirPods mic)", self._set_mode(CALL), checked=lambda i: s.mode == CALL, radio=True),
            Menu.SEPARATOR,
            Item("AI noise suppression", self._toggle("noise_suppression"), checked=self._checked("noise_suppression")),
            Item(
                "Voice gate (silence between words)",
                self._toggle("voice_gate"),
                checked=self._checked("voice_gate"),
                enabled=lambda i: s.noise_suppression,
            ),
            Item("Pause media when AirPods are removed", self._toggle("auto_pause"), checked=self._checked("auto_pause")),
            Item(
                "Keep game volume during voice chat",
                self._toggle("prevent_ducking"),
                checked=self._checked("prevent_ducking"),
            ),
            Item("Battery level", self._toggle("battery_monitor"), checked=self._checked("battery_monitor")),
            Item(
                "Low battery notifications",
                self._toggle("battery_notifications"),
                checked=self._checked("battery_notifications"),
                enabled=lambda i: s.battery_monitor,
            ),
            Menu.SEPARATOR,
            Item("Start with Windows", self._toggle_startup, checked=lambda i: startup.is_enabled()),
            Item(
                "More",
                Menu(
                    Item("Open settings file", self._open_settings),
                    Item("Reload settings file", self._reload_settings),
                    Item("Open log folder", self._open_logs),
                    Item("Run diagnostics", self._diagnostics),
                    Item("Restore Windows audio settings", self._restore),
                    Item(f"AirDops {__version__}", None, enabled=False),
                ),
            ),
            Item("Quit", self._quit),
        )

    # ------------------------------------------------------------ BLE side
    def _on_pods(self, pods: PodsStatus, now: float) -> None:
        """Called on the BLE thread for every accepted AirPods broadcast."""
        self.pods = pods
        self.pods_at = time.monotonic()
        if not self.controller.status.connected:
            return

        if self.settings.auto_pause:
            self.ear.trigger = self.settings.auto_pause_trigger
            action = self.ear.update(pods.left_in_ear, pods.right_in_ear, now, pods.single_unit)
            if action == PAUSE:
                self.monitor.submit(self._pause())
            elif action == RESUME:
                self.monitor.submit(self._resume())

        if self.settings.battery_notifications:
            self._check_low_battery(pods)

    async def _pause(self) -> None:
        from . import media

        try:
            ids = await media.pause_playing()
        except Exception:  # noqa: BLE001
            log.debug("pause failed", exc_info=True)
            return
        if ids:
            self._paused_apps = ids
            self.ear.paused_by_us = True
            log.info("paused media (bud removed)")

    async def _resume(self) -> None:
        from . import media

        ids, self._paused_apps = self._paused_apps, []
        self.ear.paused_by_us = False
        try:
            await media.resume(ids)
            log.info("resumed media (buds back in)")
        except Exception:  # noqa: BLE001
            log.debug("resume failed", exc_info=True)

    def _check_low_battery(self, pods: PodsStatus) -> None:
        limit = self.settings.low_battery_percent
        parts = [("left", pods.left_battery, pods.left_charging), ("right", pods.right_battery, pods.right_charging)]
        if pods.single_unit:
            parts = [("battery", pods.left_battery, pods.left_charging)]
        for key, level, charging in parts:
            if level is None:
                continue
            if charging or level > limit + 5:
                self._low_warned.discard(key)
            elif level <= limit and key not in self._low_warned:
                self._low_warned.add(key)
                label = "AirPods" if key == "battery" else f"{key.capitalize()} AirPod"
                self.notify("AirPods battery low", f"{label} is at {level}%.")

    # -------------------------------------------------------------- worker
    def _refresh_icon(self) -> None:
        st = self.controller.status
        pods = self._pods_fresh()
        state = "off" if not st.connected else ("call" if st.mode == CALL else "game")
        batt = pods.lowest_bud_battery if (pods and st.connected) else None
        key = (state, batt, self._title_text(), self._battery_text(), self._mic_text(), self.settings.mode)
        if key == self._last_menu_key:
            return
        self._last_menu_key = key
        try:
            self.icon.icon = icons.render(state, batt)
            self.icon.title = self._tooltip()
            self.icon.update_menu()
        except Exception:  # noqa: BLE001
            log.debug("icon refresh failed", exc_info=True)

    def _work(self) -> None:
        from .audio.endpoints import com_init, com_uninit

        com_init()
        try:
            while not self._stop.is_set():
                try:
                    st = self.controller.tick()
                    self.monitor.expected_family = family(st.device_name) if st.connected else None
                    wants_ble = self.settings.battery_monitor or self.settings.auto_pause
                    self.monitor.set_scanning(wants_ble and st.connected)
                    if not st.connected:
                        self.ear.reset()
                        self._paused_apps = []
                    self._refresh_icon()
                except Exception:  # noqa: BLE001
                    log.exception("tick failed")
                self._wake.wait(self.settings.poll_seconds)
                self._wake.clear()
            self.monitor.set_scanning(False)
            self.controller.restore_all()
        finally:
            com_uninit()

    def _setup(self, icon) -> None:
        icon.visible = True
        self.monitor.start()
        self._worker = threading.Thread(target=self._work, name="airdops-audio", daemon=True)
        self._worker.start()
        if not self.background:
            self.notify("AirDops is running", "Look for the AirPods icon in the system tray.")

    def run(self) -> None:
        log.info("AirDops %s starting", __version__)
        self.icon.run(setup=self._setup)
        log.info("AirDops stopped")
