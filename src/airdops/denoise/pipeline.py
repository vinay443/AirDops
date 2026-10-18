"""Real-time mic -> RNNoise -> virtual cable pipeline (Windows, WASAPI).

    laptop mic  ──►  RNNoise (+ optional voice gate, gain)  ──►  "CABLE Input"
                                                                     │
    Discord / game voice chat  ◄──  "CABLE Output" (default mic)  ◄──┘

VB-Audio Virtual Cable is a free, signed driver that provides the virtual
"CABLE Input" speaker and "CABLE Output" microphone pair. AirDops only plays
into it; it does not install or modify any driver.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

from .gate import VoiceGate
from .rnnoise import FRAME_SIZE, SAMPLE_RATE, Denoiser

log = logging.getLogger(__name__)


def _wasapi_index(sd) -> Optional[int]:
    for i, api in enumerate(sd.query_hostapis()):
        if "wasapi" in api["name"].lower():
            return i
    return None


def find_device(sd, name: str, want_input: bool) -> Optional[int]:
    """Map a Windows endpoint friendly name to a PortAudio WASAPI device index."""
    api = _wasapi_index(sd)
    key = "max_input_channels" if want_input else "max_output_channels"
    devices = list(enumerate(sd.query_devices()))
    pools = [[(i, d) for i, d in devices if d["hostapi"] == api and d[key] > 0]]
    pools.append([(i, d) for i, d in devices if d[key] > 0])  # any host API as fallback
    lowered = name.lower()
    for pool in pools:
        for i, d in pool:
            if d["name"].lower() == lowered:
                return i
        for i, d in pool:
            dn = d["name"].lower()
            if lowered in dn or dn in lowered:
                return i
    return None


class NoisePipeline:
    def __init__(self, mic_name: str, cable_name: str, voice_gate: bool = False, gain_db: float = 0.0) -> None:
        self.mic_name = mic_name
        self.cable_name = cable_name
        self.voice_gate_enabled = voice_gate
        self.gain = float(10 ** (gain_db / 20.0))
        self._stream = None
        self._denoiser: Optional[Denoiser] = None
        self._gate = VoiceGate()
        self._lock = threading.Lock()
        self._status_count = 0
        self.last_voice_prob = 0.0

    @property
    def running(self) -> bool:
        return self._stream is not None and bool(self._stream.active)

    def set_voice_gate(self, enabled: bool) -> None:
        self.voice_gate_enabled = enabled

    def set_gain_db(self, gain_db: float) -> None:
        self.gain = float(10 ** (gain_db / 20.0))

    def _callback(self, indata, outdata, frames, time_info, status) -> None:  # realtime thread
        if status:
            self._status_count += 1
        mono = indata.mean(axis=1) if indata.shape[1] > 1 else indata[:, 0]
        out = np.empty(frames, dtype=np.float32)
        den = self._denoiser
        for start in range(0, frames, FRAME_SIZE):
            chunk = mono[start : start + FRAME_SIZE]
            if den is None:
                clean = chunk.astype(np.float32)
                prob = 1.0
            else:
                clean, prob = den.process(chunk)
            if self.voice_gate_enabled:
                clean = self._gate.apply(clean, prob)
            out[start : start + len(chunk)] = clean
            self.last_voice_prob = prob
        if self.gain != 1.0:
            out *= self.gain
        np.clip(out, -1.0, 1.0, out=out)
        outdata[:] = out[:, None]

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            if self._stream is not None:
                return
            in_idx = find_device(sd, self.mic_name, want_input=True)
            out_idx = find_device(sd, self.cable_name, want_input=False)
            if in_idx is None:
                raise RuntimeError(f"microphone not found for noise suppression: {self.mic_name}")
            if out_idx is None:
                raise RuntimeError("VB-Cable 'CABLE Input' not found")
            in_info = sd.query_devices(in_idx)
            out_info = sd.query_devices(out_idx)
            in_ch = max(1, min(2, int(in_info["max_input_channels"])))
            out_ch = max(1, min(2, int(out_info["max_output_channels"])))
            self._denoiser = Denoiser()
            self._gate = VoiceGate()
            extra = None
            if hasattr(sd, "WasapiSettings"):
                try:
                    extra = (sd.WasapiSettings(auto_convert=True), sd.WasapiSettings(auto_convert=True))
                except TypeError:  # very old sounddevice
                    extra = None
            # Only pass WASAPI settings when both devices are WASAPI devices.
            api = _wasapi_index(sd)
            if extra and not (in_info["hostapi"] == api and out_info["hostapi"] == api):
                extra = None
            stream = sd.Stream(
                device=(in_idx, out_idx),
                samplerate=SAMPLE_RATE,
                blocksize=FRAME_SIZE,
                dtype="float32",
                channels=(in_ch, out_ch),
                latency="low",
                extra_settings=extra,
                callback=self._callback,
            )
            stream.start()
            self._stream = stream
            log.info("noise suppression running: %s -> %s", in_info["name"], out_info["name"])

    def stop(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:  # noqa: BLE001
                    log.debug("stream close: %r", exc)
            if self._denoiser is not None:
                self._denoiser.close()
                self._denoiser = None
            if self._status_count:
                log.info("audio over/underruns during session: %d", self._status_count)
                self._status_count = 0
