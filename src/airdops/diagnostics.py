"""Diagnostics report and CI self-test.

The report lists sound device *names* and states, which microphone/cable
AirDops would use, and a few seconds of decoded AirPods broadcasts. It
contains no Bluetooth addresses, device ids, serial numbers or account data,
so it is safe to share when asking for help.
"""

from __future__ import annotations

import asyncio
import os
import platform
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from . import __version__, config

_STATE_NAMES = {1: "active", 2: "disabled", 4: "not present", 8: "unplugged"}


def _section(lines: list[str], title: str) -> None:
    lines.append("")
    lines.append(f"== {title} ==")


def _guard(lines: list[str], fn: Callable[[], None]) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        lines.append(f"  ERROR: {exc.__class__.__name__}: {exc}")


def build_report(ble_seconds: float = 8.0) -> str:
    lines = [f"AirDops {__version__} diagnostics", f"Python {sys.version.split()[0]} on {platform.platform()}"]
    settings = config.load_settings()

    from .audio import endpoints as ep_mod
    from .audio.router import build_plan

    ep_mod.com_init()
    eps = []

    def audio_section() -> None:
        nonlocal eps
        eps = ep_mod.list_endpoints()
        names = {e.id: e.name for e in eps}
        for e in sorted(eps, key=lambda x: (x.flow, x.name)):
            lines.append(f"  [{e.flow:7}] {_STATE_NAMES.get(e.state, e.state):11} {e.name}")
        for flow in ("render", "capture"):
            for role, label in ((0, "default"), (2, "communications")):
                cur = ep_mod.get_default(flow, role)
                lines.append(f"  {flow} {label}: {names.get(cur, 'none') if cur else 'none'}")

    _section(lines, "Windows sound devices")
    _guard(lines, audio_section)

    def plan_section() -> None:
        state = config.load_state()
        p = build_plan(eps, settings.device_keywords, settings.preferred_mic, state.saved_defaults.get("capture"))
        names = {e.id: e.name for e in eps}
        lines.append(f"  AirPods connected: {p.connected} ({p.device_name or '-'})")
        lines.append(f"  play game audio on: {names.get(p.render_id, '-')}")
        lines.append(f"  separate hands-free output: {names.get(p.handsfree_render_id, '-')}")
        lines.append(f"  AirPods mic endpoints to block: {[names.get(i, '?') for i in p.airpods_capture_ids]}")
        lines.append(f"  laptop mic: {p.mic_name or '-'}")
        lines.append(f"  VB-Cable present: {bool(p.cable_render_id and p.cable_capture_id)}")
        lines.append(f"  mode setting: {settings.mode}; noise suppression: {settings.noise_suppression}")
        lines.append(f"  endpoints AirDops has disabled: {len(state.disabled_endpoints)}")

    _section(lines, "AirDops plan")
    _guard(lines, plan_section)

    def ducking_section() -> None:
        from .audio import ducking

        exists, value = ducking.read()
        lines.append(f"  UserDuckingPreference: {value if exists else 'not set (Windows default: reduce 80%)'}")

    _section(lines, "Communications ducking")
    _guard(lines, ducking_section)

    def denoise_section() -> None:
        import numpy as np

        from .denoise.rnnoise import Denoiser

        d = Denoiser()
        rng = np.random.default_rng(0)
        noise = (rng.standard_normal(480 * 50) * 0.05).astype(np.float32)
        out = np.concatenate([d.process(noise[i : i + 480])[0] for i in range(0, len(noise), 480)])
        d.close()
        reduction = 20 * np.log10((np.std(noise) + 1e-9) / (np.std(out[480 * 10 :]) + 1e-9))
        lines.append(f"  RNNoise loaded; white-noise reduction: {reduction:.1f} dB")

    _section(lines, "Noise suppression engine")
    _guard(lines, denoise_section)

    def sd_section() -> None:
        import sounddevice as sd

        apis = sd.query_hostapis()
        for d in sd.query_devices():
            if "wasapi" in apis[d["hostapi"]]["name"].lower():
                lines.append(
                    f"  in={d['max_input_channels']} out={d['max_output_channels']} "
                    f"{int(d['default_samplerate'])} Hz  {d['name']}"
                )

    _section(lines, "WASAPI devices (PortAudio)")
    _guard(lines, sd_section)

    def ble_section() -> None:
        from bleak import BleakScanner

        from .ble.advert import APPLE_COMPANY_ID, parse_proximity

        seen: list[str] = []

        def cb(device, adv) -> None:
            data = adv.manufacturer_data.get(APPLE_COMPANY_ID)
            status = parse_proximity(data) if data else None
            if status is None or len(seen) >= 12:
                return
            seen.append(
                f"  rssi={adv.rssi:4} {status.model_name}: L={status.left_battery} R={status.right_battery} "
                f"case={status.case_battery} inEar=L{int(status.left_in_ear)}/R{int(status.right_in_ear)}"
            )

        async def scan() -> None:
            scanner = BleakScanner(detection_callback=cb)
            await scanner.start()
            await asyncio.sleep(ble_seconds)
            await scanner.stop()

        # Run in a fresh thread: this one is a COM STA, which WinRT/bleak dislike.
        errors: list[BaseException] = []

        def runner() -> None:
            try:
                asyncio.run(scan())
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join(ble_seconds + 15)
        if errors:
            raise errors[0]
        lines.extend(seen or ["  no AirPods broadcasts heard (open the case or wear them, Bluetooth on?)"])

    _section(lines, f"AirPods Bluetooth LE broadcasts ({ble_seconds:.0f} s)")
    if ble_seconds > 0:
        _guard(lines, ble_section)
    else:
        lines.append("  skipped")

    lines.append("")
    lines.append("This report contains device names only - no addresses or ids.")
    return "\n".join(lines)


def report_path() -> Path:
    return config.data_dir() / "diagnostics.txt"


def run_and_open() -> None:
    path = report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = build_report()
    except Exception:  # noqa: BLE001
        text = "Diagnostics failed:\n" + traceback.format_exc()
    path.write_text(text, encoding="utf-8")
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]


def self_test(out_path: str) -> int:
    """Used by CI on the built .exe: every module imports and RNNoise works."""
    results: list[str] = []
    ok = True

    def check(name: str, fn: Callable[[], object]) -> None:
        nonlocal ok
        t = time.perf_counter()
        try:
            detail = fn()
            results.append(f"PASS {name} ({(time.perf_counter() - t) * 1000:.0f} ms) {detail or ''}".rstrip())
        except Exception as exc:  # noqa: BLE001
            ok = False
            results.append(f"FAIL {name}: {exc.__class__.__name__}: {exc}")

    def imports() -> str:
        import bleak  # noqa: F401
        import comtypes  # noqa: F401
        import numpy  # noqa: F401
        import pycaw  # noqa: F401
        import sounddevice  # noqa: F401
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager  # noqa: F401

        from . import controller, core, media  # noqa: F401
        from .ble import scanner  # noqa: F401
        from .denoise import pipeline  # noqa: F401
        from .ui import panel, shell, toast  # noqa: F401

        return ""

    def ui() -> str:
        import tempfile

        from PySide6.QtGui import QImage
        from PySide6.QtWidgets import QApplication

        from .ui import theme
        from .ui.preview import render_all

        app = QApplication.instance() or QApplication([])
        theme.load_fonts()
        out = Path(out_path).with_name("previews") if out_path else Path(tempfile.mkdtemp())
        paths = render_all(out)
        for path in paths:
            img = QImage(str(path))
            if img.isNull() or img.width() < 200:
                raise AssertionError(f"bad render {path.name}")
        from PySide6.QtGui import QFontDatabase

        if "Inter" not in QFontDatabase.families():
            raise AssertionError("Inter font not bundled")
        del app
        return f"{len(paths)} screens rendered"

    def rnnoise() -> str:
        import numpy as np

        from .denoise.rnnoise import Denoiser

        d = Denoiser()
        noise = (np.random.default_rng(1).standard_normal(480 * 100) * 0.05).astype(np.float32)
        out = np.concatenate([d.process(noise[i : i + 480])[0] for i in range(0, len(noise), 480)])
        d.close()
        red = 20 * np.log10(np.std(noise) / (np.std(out[4800:]) + 1e-9))
        if red < 6:
            raise AssertionError(f"noise only reduced by {red:.1f} dB")
        return f"{red:.1f} dB reduction"

    def com() -> str:
        from .audio import endpoints

        endpoints.com_init()
        eps = endpoints.list_endpoints()
        endpoints._policy_config()  # interface must be creatable
        return f"{len(eps)} endpoints"

    def media_api() -> str:
        from . import media

        asyncio.run(media.pause_playing())  # no sessions on CI: must simply return
        return ""

    def portaudio() -> str:
        import sounddevice as sd

        return f"{len(sd.query_hostapis())} host APIs"

    check("imports", imports)
    check("rnnoise", rnnoise)
    check("ui", ui)
    check("portaudio", portaudio)
    # WinRT async before COM init on this thread (COM init makes it an STA).
    check("media-session-api", media_api)
    check("core-audio-com", com)
    Path(out_path).write_text("\n".join(results) + "\n", encoding="utf-8")
    return 0 if ok else 1
