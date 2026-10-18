"""Decides which Windows audio endpoints to use (pure logic, unit tested).

Windows exposes AirPods as one or two *render* endpoints and one *capture*
endpoint:

* Older drivers: "Headphones (AirPods Pro Stereo)" (A2DP, full quality) and
  "Headset (AirPods Pro Hands-Free AG Audio)" (HFP, call quality), plus the
  capture endpoint "Headset (AirPods Pro Hands-Free AG Audio)".
* Windows 11 unified endpoints: a single "Headphones (AirPods Pro)" render
  endpoint and a "Headset (AirPods Pro)" capture endpoint. The moment any app
  opens that capture endpoint, Windows drops the whole link to HFP.

So in Game mode we: play through the AirPods render endpoint that is not the
hands-free one, record from another microphone, and *disable* every AirPods
capture endpoint (and the separate hands-free render endpoint, if present)
so no game or chat app can drag the AirPods into HFP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

RENDER = "render"
CAPTURE = "capture"

STATE_ACTIVE = 0x1
STATE_DISABLED = 0x2
STATE_NOTPRESENT = 0x4
STATE_UNPLUGGED = 0x8

GAME = "game"
CALL = "call"

_BUILTIN_MIC_HINTS = (
    "microphone array",
    "internal",
    "built-in",
    "smart sound",
    "realtek",
    "intel",
)
_CABLE_RENDER = "cable input"
_CABLE_CAPTURE = "cable output"


@dataclass(frozen=True)
class Endpoint:
    id: str
    name: str
    flow: str  # RENDER or CAPTURE
    state: int

    @property
    def active(self) -> bool:
        return self.state == STATE_ACTIVE

    @property
    def disabled(self) -> bool:
        return self.state == STATE_DISABLED


@dataclass
class Plan:
    connected: bool = False
    device_name: str = ""
    render_id: Optional[str] = None  # where game audio goes
    handsfree_render_id: Optional[str] = None
    airpods_capture_ids: list[str] = field(default_factory=list)
    to_disable: list[str] = field(default_factory=list)  # game mode
    mic_id: Optional[str] = None  # laptop/other mic for game mode
    mic_name: str = ""
    cable_render_id: Optional[str] = None
    cable_render_name: str = ""
    cable_capture_id: Optional[str] = None


def matches(name: str, keywords: Iterable[str]) -> bool:
    lowered = name.lower()
    return any(k.strip() and k.strip().lower() in lowered for k in keywords)


def is_handsfree(name: str) -> bool:
    lowered = name.lower()
    return "hands-free" in lowered or "handsfree" in lowered or lowered.startswith("headset")


def is_cable(name: str) -> bool:
    lowered = name.lower()
    return _CABLE_RENDER in lowered or _CABLE_CAPTURE in lowered or "vb-audio" in lowered


def device_label(name: str) -> str:
    """'Headphones (AirPods Pro Stereo)' -> 'AirPods Pro'."""
    inner = name
    if "(" in name and name.endswith(")"):
        inner = name[name.index("(") + 1 : -1]
    for suffix in (" Hands-Free AG Audio", " Hands-Free", " Stereo"):
        if inner.endswith(suffix):
            inner = inner[: -len(suffix)]
    return inner.strip() or name


def short_name(name: str) -> str:
    """'Microphone Array (Intel® Smart Sound Technology)' -> 'Microphone Array'."""
    if " (" in name and name.endswith(")"):
        head = name[: name.index(" (")].strip()
        if head.lower() in ("microphone", "headset", "line in", "headphones", "speakers"):
            return name
        return head or name
    return name


def pick_mic(
    endpoints: Sequence[Endpoint],
    keywords: Iterable[str],
    preferred: str = "",
    previous_default: Optional[str] = None,
) -> Optional[Endpoint]:
    keywords = list(keywords)
    candidates = [
        e
        for e in endpoints
        if e.flow == CAPTURE and e.active and not matches(e.name, keywords) and not is_cable(e.name)
    ]
    if not candidates:
        return None
    if preferred.strip():
        for e in candidates:
            if preferred.strip().lower() in e.name.lower():
                return e
    if previous_default:
        for e in candidates:
            if e.id == previous_default:
                return e
    for hint in _BUILTIN_MIC_HINTS:
        for e in candidates:
            if hint in e.name.lower():
                return e
    return candidates[0]


def build_plan(
    endpoints: Sequence[Endpoint],
    keywords: Iterable[str],
    preferred_mic: str = "",
    previous_default_mic: Optional[str] = None,
) -> Plan:
    keywords = list(keywords)
    plan = Plan()

    target_render = [e for e in endpoints if e.flow == RENDER and matches(e.name, keywords)]
    target_capture = [e for e in endpoints if e.flow == CAPTURE and matches(e.name, keywords)]

    active_render = [e for e in target_render if e.active]
    stereo = [e for e in active_render if not is_handsfree(e.name)]
    handsfree = [e for e in target_render if is_handsfree(e.name) and not e.state == STATE_NOTPRESENT]

    # Connected = the AirPods' playback endpoint is live. (The hands-free one
    # may be disabled by us, so it does not count.)
    if stereo:
        plan.connected = True
        plan.render_id = stereo[0].id
        plan.device_name = device_label(stereo[0].name)
    elif active_render:
        # Only a hands-free style endpoint is active (unusual driver naming).
        plan.connected = True
        plan.render_id = active_render[0].id
        plan.device_name = device_label(active_render[0].name)

    # A separate hands-free render endpoint only exists with split endpoints;
    # with unified endpoints the stereo one is also used for calls.
    if handsfree and plan.render_id not in {h.id for h in handsfree}:
        plan.handsfree_render_id = handsfree[0].id

    plan.airpods_capture_ids = [e.id for e in target_capture if e.state != STATE_NOTPRESENT]
    plan.to_disable = list(plan.airpods_capture_ids)
    if plan.handsfree_render_id:
        plan.to_disable.append(plan.handsfree_render_id)

    mic = pick_mic(endpoints, keywords, preferred_mic, previous_default_mic)
    if mic:
        plan.mic_id = mic.id
        plan.mic_name = mic.name

    for e in endpoints:
        if not e.active:
            continue
        lowered = e.name.lower()
        if e.flow == RENDER and _CABLE_RENDER in lowered and plan.cable_render_id is None:
            plan.cable_render_id = e.id
            plan.cable_render_name = e.name
        elif e.flow == CAPTURE and _CABLE_CAPTURE in lowered and plan.cable_capture_id is None:
            plan.cable_capture_id = e.id

    return plan


def is_ours(endpoint_id: Optional[str], endpoints: Sequence[Endpoint], keywords: Iterable[str]) -> bool:
    """True if the endpoint id belongs to the AirPods (or is unknown)."""
    if endpoint_id is None:
        return False
    for e in endpoints:
        if e.id == endpoint_id:
            return matches(e.name, keywords)
    return False
