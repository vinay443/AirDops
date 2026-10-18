"""AirDops engine: audio controller + Bluetooth LE monitor + ear detection.

UI-agnostic. The Qt shell (``ui/shell.py``) polls ``snapshot()`` and calls the
action methods; notifications are queued for the UI to display.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import deque
from typing import Optional

from . import __version__, config, startup
from .audio.router import CALL, GAME
from .ble.advert import PodsStatus, family
from .controller import Controller
from .earsense import PAUSE, RESUME, EarDetector
from .ui.model import ViewState

log = logging.getLogger(__name__)

BATTERY_STALE_S = 90.0
NOTIFY_COOLDOWN_S = 600.0
VBCABLE_URL = "https://vb-audio.com/Cable/"


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


def pipeline_factory(mic_name: str, cable_name: str, voice_gate: bool, gain_db: float):
    from .denoise.pipeline import NoisePipeline

    return NoisePipeline(mic_name, cable_name, voice_gate, gain_db)


def make_controller(settings: config.Settings, state: config.State, notify=lambda t, m: None) -> Controller:
    from .audio import ducking

    return Controller(settings, state, _WinAudio(), ducking, pipeline_factory, config.save_state, notify=notify)


def _open(target: str) -> None:
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]


class Core:
    def __init__(self) -> None:
        from .ble.scanner import BatteryMonitor

        self.settings = config.load_settings()
        self.state = config.load_state()
        self.controller = make_controller(self.settings, self.state, notify=self.notify)
        self.ear = EarDetector(trigger=self.settings.auto_pause_trigger)
        self.monitor = BatteryMonitor(self._on_pods, self.settings.ble_min_rssi)
        self.pods: Optional[PodsStatus] = None
        self.pods_at = 0.0
        self._paused_apps: list[str] = []
        self._low_warned: set[str] = set()
        self._last_notified: dict[str, float] = {}
        self._notifications: deque[tuple[str, str]] = deque(maxlen=20)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._restore_requested = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._startup_enabled = self._read_startup()

    # --------------------------------------------------------- lifecycle
    def start(self) -> None:
        self.monitor.start()
        self._worker = threading.Thread(target=self._work, name="airdops-audio", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Stop and undo every change (runs the restore on the worker thread)."""
        self._stop.set()
        self._wake.set()
        if self._worker:
            self._worker.join(timeout=15)
        self.monitor.shutdown()

    def _work(self) -> None:
        from .audio.endpoints import com_init, com_uninit

        com_init()
        from .audio.endpoints import DeviceWatcher

        watcher = DeviceWatcher(self._wake.set)
        if watcher.start():
            log.info("listening for audio device changes")
        try:
            while not self._stop.is_set():
                try:
                    if self._restore_requested.is_set():
                        self._restore_requested.clear()
                        self.controller.restore_all()
                        self.notify("Windows Audio Restored", "AirDops switched to Call Mode and undid its changes.")
                    st = self.controller.tick()
                    self.monitor.expected_family = family(st.device_name) if st.connected else None
                    wants_ble = self.settings.battery_monitor or self.settings.auto_pause
                    self.monitor.set_scanning(wants_ble and st.connected)
                    if not st.connected:
                        self.ear.reset()
                        self._paused_apps = []
                except Exception:  # noqa: BLE001
                    log.exception("tick failed")
                # Device events wake us instantly (so the AirPods mic is blocked
                # before apps can grab it); polling is the safety net.
                if self._wake.wait(self.settings.poll_seconds):
                    time.sleep(0.12)  # coalesce bursts of events
                self._wake.clear()
            self.monitor.set_scanning(False)
            self.controller.restore_all()
        finally:
            watcher.stop()
            com_uninit()

    # ------------------------------------------------------ notifications
    def notify(self, title: str, message: str) -> None:
        now = time.monotonic()
        key = title + "|" + message
        if now - self._last_notified.get(key, -1e9) < NOTIFY_COOLDOWN_S:
            return
        self._last_notified[key] = now
        log.info("notify: %s - %s", title, message)
        self._notifications.append((title, message))

    def pop_notifications(self) -> list[tuple[str, str]]:
        out = []
        while self._notifications:
            out.append(self._notifications.popleft())
        return out

    # ------------------------------------------------------------ state
    def _pods_fresh(self) -> Optional[PodsStatus]:
        if self.pods and time.monotonic() - self.pods_at < BATTERY_STALE_S:
            return self.pods
        return None

    def snapshot(self) -> ViewState:
        st = self.controller.status
        pods = self._pods_fresh() if st.connected else None
        s = self.settings
        name = (pods.model_name if pods else st.device_name) or "AirPods"
        return ViewState(
            connected=st.connected,
            name=name,
            mode=s.mode,
            battery_known=pods is not None,
            single_unit=bool(pods and pods.single_unit),
            left=pods.left_battery if pods else None,
            right=pods.right_battery if pods else None,
            case=pods.case_battery if pods else None,
            left_charging=bool(pods and pods.left_charging),
            right_charging=bool(pods and pods.right_charging),
            case_charging=bool(pods and pods.case_charging),
            left_in_ear=bool(pods and pods.left_in_ear),
            right_in_ear=bool(pods and pods.right_in_ear),
            mic_name=st.mic_name,
            mics=tuple(self.controller.available_mics()),
            preferred_mic=s.preferred_mic,
            cable_installed=bool(self.controller.plan.cable_render_id and self.controller.plan.cable_capture_id),
            ns_active=st.noise_suppression_active,
            hfp_blocked=st.hfp_blocked,
            note=st.note,
            noise_suppression=s.noise_suppression,
            voice_gate=s.voice_gate,
            mic_gain_db=s.mic_gain_db,
            auto_pause_trigger=s.auto_pause_trigger,
            hotkey=s.hotkey,
            prevent_ducking=s.prevent_ducking,
            auto_pause=s.auto_pause,
            battery_notifications=s.battery_notifications,
            start_with_windows=self._startup_enabled,
            version=__version__,
        )

    # ---------------------------------------------------------- actions
    def _changed(self) -> None:
        config.save_settings(self.settings)
        self.controller.settings_changed()
        self._wake.set()

    def set_mode(self, mode: str) -> None:
        self.controller.set_mode(mode if mode in (GAME, CALL) else GAME)
        config.save_settings(self.settings)
        self._wake.set()

    def set_setting(self, name: str, value: bool) -> None:
        if name == "start_with_windows":
            if startup.set_enabled(value):
                self._startup_enabled = value
            return
        if not hasattr(self.settings, name):
            return
        setattr(self.settings, name, bool(value))
        self._changed()

    def set_gain(self, db: float) -> None:
        self.settings.mic_gain_db = max(-12.0, min(24.0, float(db)))
        config.save_settings(self.settings)
        self.controller.settings_changed()
        self._wake.set()

    def set_trigger(self, trigger: str) -> None:
        if trigger in ("one", "both"):
            self.settings.auto_pause_trigger = trigger
            self.ear.trigger = trigger
            config.save_settings(self.settings)

    def mic_level(self) -> float:
        return self.controller.mic_level()

    def finish_onboarding(self, open_at_login: bool) -> None:
        self.settings.onboarded = True
        config.save_settings(self.settings)
        self.set_setting("start_with_windows", open_at_login)

    def toggle_mode(self) -> str:
        new = CALL if self.settings.mode == GAME else GAME
        self.set_mode(new)
        return new

    def set_mic(self, name: str) -> None:
        self.settings.preferred_mic = name
        self._changed()

    def restore(self) -> None:
        """Undo AirDops' changes; done on the worker thread (it owns COM)."""
        self.controller.set_mode(CALL)
        config.save_settings(self.settings)
        self._restore_requested.set()
        self._wake.set()

    def reload_settings(self) -> None:
        fresh = config.load_settings()
        for field_name, value in vars(fresh).items():
            setattr(self.settings, field_name, value)
        self.ear.trigger = self.settings.auto_pause_trigger
        self.monitor.min_rssi = self.settings.ble_min_rssi
        self._changed()

    def open_bluetooth(self) -> None:
        _open("ms-settings:bluetooth")

    def open_sound(self) -> None:
        _open("ms-settings:sound")

    def open_vbcable(self) -> None:
        _open(VBCABLE_URL)

    def open_logs(self) -> None:
        config.log_dir().mkdir(parents=True, exist_ok=True)
        _open(str(config.log_dir()))

    def open_settings_file(self) -> None:
        config.save_settings(self.settings)
        _open(str(config.settings_path()))

    def diagnostics(self) -> None:
        from .diagnostics import run_and_open

        threading.Thread(target=run_and_open, name="airdops-diag", daemon=True).start()

    @staticmethod
    def _read_startup() -> bool:
        try:
            return startup.is_enabled()
        except Exception:  # noqa: BLE001
            return False

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
            log.info("paused media (AirPod removed)")

    async def _resume(self) -> None:
        from . import media

        ids, self._paused_apps = self._paused_apps, []
        self.ear.paused_by_us = False
        try:
            await media.resume(ids)
            log.info("resumed media (AirPods back in)")
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
                label = pods.model_name if key == "battery" else f"Your {key} AirPod"
                self.notify("Low Battery", f"{label} is at {level}%.")
