"""Background Bluetooth LE listener for AirPods battery / in-ear broadcasts.

Runs its own asyncio loop on a daemon thread (WinRT needs an MTA thread, so
this thread never touches COM itself). Other async Windows calls - e.g. media
play/pause - are scheduled onto the same loop with ``submit``.

Privacy: AirPods broadcasts are public radio packets, and other people's
AirPods nearby send them too. We only accept packets that are strong (close
to this PC), whose product family matches the AirPods Windows says are
connected, and we never store or log Bluetooth addresses or raw payloads.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import Future
from typing import Callable, Coroutine, Optional

from .advert import APPLE_COMPANY_ID, PodsStatus, family, parse_proximity

log = logging.getLogger(__name__)

PASSIVE_GRACE_S = 30.0


class BatteryMonitor:
    def __init__(self, on_status: Callable[[PodsStatus, float], None], min_rssi: int = -70) -> None:
        self._on_status = on_status
        self.min_rssi = min_rssi
        self.expected_family: Optional[str] = None  # set from the connected device name
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop: Optional[asyncio.Event] = None
        self._scanning = threading.Event()
        self._want_scan = threading.Event()
        self._best_rssi = -999
        self._best_at = 0.0
        self.error: Optional[str] = None
        # Passive scanning only listens (no scan requests), which is all AirPods
        # broadcasts need. Falls back to active if passive hears nothing.
        self.passive = True
        self._heard = False

    # ---- lifecycle -------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        ready = threading.Event()

        def runner() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            self._stop = asyncio.Event()
            ready.set()
            try:
                loop.run_until_complete(self._main())
            finally:
                loop.close()

        self._thread = threading.Thread(target=runner, name="airdops-ble", daemon=True)
        self._thread.start()
        ready.wait(5)

    def shutdown(self) -> None:
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=5)

    def set_scanning(self, enabled: bool) -> None:
        if enabled:
            self._want_scan.set()
        else:
            self._want_scan.clear()

    def submit(self, coro: Coroutine) -> Optional[Future]:
        if not self._loop:
            coro.close()
            return None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ---- scanning --------------------------------------------------------
    def _detection(self, device, adv) -> None:  # called on the loop thread
        data = adv.manufacturer_data.get(APPLE_COMPANY_ID)
        if not data:
            return
        status = parse_proximity(data)
        if status is None:
            return
        self._heard = True
        rssi = adv.rssi if adv.rssi is not None else -999
        if rssi < self.min_rssi:
            return
        if self.expected_family and family(status.model_name) != self.expected_family:
            return
        now = time.monotonic()
        # Stick with the strongest nearby set; a weaker one only wins once the
        # stronger one has gone quiet.
        if now - self._best_at > 6:
            self._best_rssi = rssi
        if rssi >= self._best_rssi - 6:
            self._best_rssi = max(self._best_rssi, rssi)
            self._best_at = now
            try:
                self._on_status(status, now)
            except Exception:  # noqa: BLE001
                log.exception("status callback failed")

    async def _main(self) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            if not self._want_scan.is_set():
                await asyncio.sleep(1)
                continue
            try:
                from bleak import BleakScanner

                mode = "passive" if self.passive else "active"
                scanner = BleakScanner(detection_callback=self._detection, scanning_mode=mode)
                try:
                    await scanner.start()
                except Exception:
                    if not self.passive:
                        raise
                    log.info("passive BLE scanning unavailable; using active scanning")
                    self.passive = False
                    continue
                self._scanning.set()
                self._heard = False
                self.error = None
                started = time.monotonic()
                log.info("Bluetooth LE battery scan started (%s)", mode)
                try:
                    while self._want_scan.is_set() and not self._stop.is_set():
                        await asyncio.sleep(1)
                        if self.passive and not self._heard and time.monotonic() - started > PASSIVE_GRACE_S:
                            log.info("no AirPods broadcasts heard passively; switching to active scanning")
                            self.passive = False
                            break
                finally:
                    await scanner.stop()
                    self._scanning.clear()
                    self._best_rssi = -999
                    log.info("Bluetooth LE battery scan stopped")
            except Exception as exc:  # noqa: BLE001 - Bluetooth off, adapter busy...
                self.error = str(exc) or exc.__class__.__name__
                log.warning("BLE scan unavailable: %s (retrying in 20 s)", self.error)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=20)
                except asyncio.TimeoutError:
                    pass
