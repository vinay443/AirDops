"""The audio controller: applies Game / Call mode when the AirPods come and go.

All Windows calls go through small injectable backends so the logic can be
unit tested on any OS with fakes (see tests/test_controller.py).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence

from .audio import router
from .audio.router import CALL, CAPTURE, GAME, RENDER, Endpoint, Plan
from .config import Settings, State

log = logging.getLogger(__name__)

ROLE_CONSOLE, ROLE_MULTIMEDIA, ROLE_COMMUNICATIONS = 0, 1, 2
ALL_ROLES = (ROLE_CONSOLE, ROLE_MULTIMEDIA, ROLE_COMMUNICATIONS)
NON_COMM_ROLES = (ROLE_CONSOLE, ROLE_MULTIMEDIA)
DUCKING_DO_NOTHING = 3


class AudioBackend(Protocol):
    def list_endpoints(self) -> list[Endpoint]: ...
    def get_default(self, flow: str, role: int) -> Optional[str]: ...
    def set_default(self, endpoint_id: str, roles: Sequence[int]) -> bool: ...
    def set_enabled(self, endpoint_id: str, enabled: bool) -> bool: ...


class DuckingBackend(Protocol):
    def read(self) -> tuple[bool, Optional[int]]: ...
    def write(self, value: Optional[int]) -> bool: ...


class Pipeline(Protocol):
    mic_name: str
    running: bool

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def set_voice_gate(self, enabled: bool) -> None: ...
    def set_gain_db(self, gain_db: float) -> None: ...


@dataclass
class Status:
    connected: bool = False
    device_name: str = ""
    mode: str = GAME
    mic_name: str = ""
    noise_suppression_active: bool = False
    hfp_blocked: bool = False
    note: str = ""  # one-line hint for the tray menu


class Controller:
    def __init__(
        self,
        settings: Settings,
        state: State,
        audio: AudioBackend,
        ducking: Optional[DuckingBackend],
        pipeline_factory: Optional[Callable[[str, str, bool, float], Pipeline]],
        save_state: Callable[[State], None],
        notify: Callable[[str, str], None] = lambda title, msg: None,
    ) -> None:
        self.settings = settings
        self.state = state
        self.audio = audio
        self.ducking = ducking
        self.pipeline_factory = pipeline_factory
        self._save_state = save_state
        self.notify = notify
        self.status = Status(mode=settings.mode)
        self.plan = Plan()
        self.endpoints: list[Endpoint] = []
        self._pipeline: Optional[Pipeline] = None
        self._applied_mode: Optional[str] = None  # mode last applied while connected
        self._was_connected = False
        self._lock = threading.RLock()
        self._warned_no_cable = False
        self._warned_disable_failed = False
        self._ns_failed_for: Optional[str] = None
        self._we_set_capture: Optional[str] = None

    # ------------------------------------------------------------------ utils
    def _persist(self) -> None:
        try:
            self._save_state(self.state)
        except Exception:  # noqa: BLE001
            log.exception("could not save state")

    def _keywords(self) -> list[str]:
        return self.settings.device_keywords

    def _is_foreign(self, endpoint_id: Optional[str], endpoints: Sequence[Endpoint]) -> bool:
        """An endpoint that is neither the AirPods nor the virtual cable."""
        if not endpoint_id:
            return False
        for e in endpoints:
            if e.id == endpoint_id:
                return not router.matches(e.name, self._keywords()) and not router.is_cable(e.name)
        return False

    def _remember_defaults(self, endpoints: Sequence[Endpoint]) -> None:
        """While the AirPods are away, remember the user's normal defaults."""
        changed = False
        for key, flow, role in (
            ("render", RENDER, ROLE_CONSOLE),
            ("render_comm", RENDER, ROLE_COMMUNICATIONS),
            ("capture", CAPTURE, ROLE_CONSOLE),
            ("capture_comm", CAPTURE, ROLE_COMMUNICATIONS),
        ):
            current = self.audio.get_default(flow, role)
            if current and self._is_foreign(current, endpoints) and self.state.saved_defaults.get(key) != current:
                self.state.saved_defaults[key] = current
                changed = True
        if changed:
            self._persist()

    # -------------------------------------------------------------- ducking
    def _set_ducking(self, off: bool) -> None:
        if self.ducking is None:
            return
        if off:
            if not self.state.ducking_changed:
                exists, value = self.ducking.read()
                if exists and value == DUCKING_DO_NOTHING:
                    return
                self.state.ducking_original = value if exists else None
                if self.ducking.write(DUCKING_DO_NOTHING):
                    self.state.ducking_changed = True
                    self._persist()
        elif self.state.ducking_changed:
            if self.ducking.write(self.state.ducking_original):
                self.state.ducking_changed = False
                self.state.ducking_original = None
                self._persist()

    # ---------------------------------------------------------- endpoints
    def _disable(self, ids: Sequence[str], endpoints: Sequence[Endpoint]) -> bool:
        by_id = {e.id: e for e in endpoints}
        ok = True
        for eid in ids:
            ep = by_id.get(eid)
            if ep is None or ep.disabled:
                # Already disabled (by us earlier, or by the user - in which
                # case it is not in our list and we will not re-enable it).
                continue
            if self.audio.set_enabled(eid, False):
                if eid not in self.state.disabled_endpoints:
                    self.state.disabled_endpoints.append(eid)
                    self._persist()
                log.info("blocked hands-free endpoint: %s", ep.name)
            else:
                ok = False
        return ok

    def _reenable_all(self) -> None:
        remaining = []
        for eid in self.state.disabled_endpoints:
            if not self.audio.set_enabled(eid, True):
                remaining.append(eid)
        if remaining != self.state.disabled_endpoints:
            self.state.disabled_endpoints = remaining
            self._persist()

    # ------------------------------------------------------------ pipeline
    def _stop_pipeline(self) -> None:
        if self._pipeline is not None:
            try:
                self._pipeline.stop()
            except Exception:  # noqa: BLE001
                log.exception("stopping noise suppression failed")
            self._pipeline = None
        self.status.noise_suppression_active = False

    def _ensure_pipeline(self, plan: Plan) -> bool:
        """Start (or keep) noise suppression. Returns True when it is running."""
        s = self.settings
        if not (s.noise_suppression and self.pipeline_factory and plan.mic_name):
            self._stop_pipeline()
            return False
        if not (plan.cable_render_id and plan.cable_capture_id):
            self._stop_pipeline()
            if not self._warned_no_cable:
                self._warned_no_cable = True
                self.notify(
                    "Noise suppression needs VB-Cable",
                    "Install the free VB-Audio Virtual Cable to clean up your mic. Using the laptop mic directly for now.",
                )
            return False
        if self._pipeline is not None and self._pipeline.mic_name != plan.mic_name:
            self._stop_pipeline()
        if self._pipeline is None:
            if self._ns_failed_for == plan.mic_name:
                return False
            try:
                p = self.pipeline_factory(plan.mic_name, plan.cable_render_name, s.voice_gate, s.mic_gain_db)
                p.start()
                self._pipeline = p
                self._ns_failed_for = None
            except Exception as exc:  # noqa: BLE001
                log.warning("noise suppression could not start: %s", exc)
                self._ns_failed_for = plan.mic_name
                self.notify("Noise suppression unavailable", f"{exc}. Using the mic directly.")
                return False
        else:
            self._pipeline.set_voice_gate(s.voice_gate)
            self._pipeline.set_gain_db(s.mic_gain_db)
        self.status.noise_suppression_active = True
        return True

    # ---------------------------------------------------------------- modes
    def _apply_game(self, plan: Plan, endpoints: Sequence[Endpoint], first: bool) -> None:
        blocked = self._disable(plan.to_disable, endpoints)
        if not blocked and not self._warned_disable_failed:
            self._warned_disable_failed = True
            self.notify(
                "Couldn't fully block the AirPods mic",
                "Windows refused to disable the hands-free device. Run AirDops as administrator once, or see the README.",
            )
        self.status.hfp_blocked = blocked and bool(plan.to_disable)

        if first and plan.render_id:
            self.audio.set_default(plan.render_id, ALL_ROLES)

        ns = self._ensure_pipeline(plan)
        capture = plan.cable_capture_id if ns else plan.mic_id
        if capture and (first or capture != self._we_set_capture):
            if self.audio.set_default(capture, ALL_ROLES):
                self._we_set_capture = capture
        self.status.mic_name = router.short_name(plan.mic_name)
        if not plan.mic_id:
            self.status.note = "No other microphone found"
        self._set_ducking(self.settings.prevent_ducking)

    def _apply_call(self, plan: Plan, endpoints: Sequence[Endpoint], first: bool) -> bool:
        """Returns False when it must run again next tick (endpoints just re-enabled)."""
        self._stop_pipeline()
        self.status.hfp_blocked = False
        self._set_ducking(False)
        self.status.mic_name = plan.device_name
        if self.state.disabled_endpoints:
            self._reenable_all()
            return False  # let Windows bring the endpoints back before choosing defaults
        if first:
            if plan.render_id:
                self.audio.set_default(plan.render_id, NON_COMM_ROLES)
                self.audio.set_default(plan.handsfree_render_id or plan.render_id, (ROLE_COMMUNICATIONS,))
            if plan.airpods_capture_ids:
                self.audio.set_default(plan.airpods_capture_ids[0], ALL_ROLES)
                self._we_set_capture = plan.airpods_capture_ids[0]
        return True

    def _restore_capture_default(self, endpoints: Sequence[Endpoint]) -> None:
        current = self.audio.get_default(CAPTURE, ROLE_CONSOLE)
        if current and self._is_foreign(current, endpoints) and current != self._we_set_capture:
            return  # the user picked something else themselves; leave it
        saved = self.state.saved_defaults.get("capture")
        if not saved:
            # Never seen the normal default (first run with AirPods already on):
            # fall back to the best non-AirPods, non-cable mic.
            mic = router.pick_mic(endpoints, self._keywords(), self.settings.preferred_mic)
            saved = mic.id if mic else None
        saved_comm = self.state.saved_defaults.get("capture_comm", saved)
        if saved:
            self.audio.set_default(saved, NON_COMM_ROLES)
        if saved_comm:
            self.audio.set_default(saved_comm, (ROLE_COMMUNICATIONS,))
        self._we_set_capture = None

    def _on_disconnect(self, endpoints: Sequence[Endpoint]) -> None:
        self._stop_pipeline()
        self._restore_capture_default(endpoints)
        self._set_ducking(False)
        self._applied_mode = None
        self.status.hfp_blocked = False

    # ----------------------------------------------------------------- tick
    def tick(self) -> Status:
        with self._lock:
            endpoints = self.audio.list_endpoints()
            plan = router.build_plan(
                endpoints,
                self._keywords(),
                self.settings.preferred_mic,
                self.state.saved_defaults.get("capture"),
            )
            self.plan = plan
            self.endpoints = list(endpoints)
            self.status.connected = plan.connected
            self.status.device_name = plan.device_name
            self.status.mode = self.settings.mode
            self.status.note = ""

            if not plan.connected:
                if self._was_connected:
                    log.info("AirPods disconnected")
                    self._on_disconnect(endpoints)
                self._was_connected = False
                self._remember_defaults(endpoints)
                self.status.mic_name = ""
                return self.status

            if not self._was_connected:
                log.info("AirPods connected: %s", plan.device_name)
            first = self._applied_mode != self.settings.mode
            if first:
                self._remember_defaults(endpoints)
            done = True
            if self.settings.mode == CALL:
                done = self._apply_call(plan, endpoints, first)
            else:
                self._apply_game(plan, endpoints, first)
            self._applied_mode = self.settings.mode if done else None
            self._was_connected = True
            return self.status

    def mic_level(self) -> float:
        p = self._pipeline
        return float(getattr(p, "level", 0.0)) if p is not None else 0.0

    def available_mics(self) -> list[str]:
        """Names of microphones usable in Game mode (not the AirPods, not the cable)."""
        names = []
        for e in self.endpoints:
            if e.flow == CAPTURE and e.active and not router.matches(e.name, self._keywords()) and not router.is_cable(e.name):
                names.append(e.name)
        return names

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self.settings.mode = mode if mode in (GAME, CALL) else GAME

    def settings_changed(self) -> None:
        """Re-apply after a toggle (noise suppression, ducking...)."""
        with self._lock:
            self._ns_failed_for = None
            self._warned_no_cable = False
            if not self.settings.prevent_ducking:
                self._set_ducking(False)
            self._applied_mode = None  # forces a full re-apply on next tick

    def restore_all(self) -> None:
        """Undo everything AirDops changed (on quit, or from the menu)."""
        with self._lock:
            self._stop_pipeline()
            try:
                endpoints = self.audio.list_endpoints()
            except Exception:  # noqa: BLE001
                endpoints = []
            self._reenable_all()
            self._restore_capture_default(endpoints)
            self._set_ducking(False)
            self._applied_mode = None
            self._was_connected = False
            log.info("restored Windows audio settings")
