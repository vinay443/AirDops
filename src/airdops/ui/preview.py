"""Sample states and offscreen rendering of the UI (docs screenshots, CI self-test)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter

from . import theme, widgets
from .model import ViewState

CONNECTED = ViewState(
    connected=True,
    name="AirPods Pro 2",
    mode="game",
    battery_known=True,
    left=80,
    right=70,
    case=45,
    case_charging=True,
    left_in_ear=True,
    right_in_ear=True,
    mic_name="Microphone Array",
    mic_gain_db=6.0,
    mics=("Microphone Array (Intel® Smart Sound Technology)", "Microphone (Blue Yeti)"),
    cable_installed=True,
    ns_active=True,
    hfp_blocked=True,
    version="0.3.0",
)
DISCONNECTED = ViewState(connected=False, name="AirPods", cable_installed=False, version="0.3.0")
CALL = ViewState(
    connected=True,
    name="AirPods Pro 2",
    mode="call",
    battery_known=True,
    left=15,
    right=9,
    case=None,
    mic_name="AirPods Pro 2 mic",
    cable_installed=True,
    version="0.3.0",
)


class _NoActions:
    def __getattr__(self, name):
        return lambda *a, **k: None


def _shoot(widget) -> QImage:
    widget.adjustSize()
    return widget.grab().toImage()


def render_all(out: Path) -> list[Path]:
    from airdops.ui.panel import Panel
    from airdops.ui.toast import Toast

    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for pal, tag in ((theme.LIGHT, "light"), (theme.DARK, "dark")):
        widgets.set_palette(pal)
        for st, name in ((CONNECTED, "connected"), (DISCONNECTED, "disconnected"), (CALL, "call")):
            panel = Panel(_NoActions())
            panel.set_state(st)
            panel._fit(4000)
            img = panel.grab().toImage()
            bg = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
            bg.fill(QColor("#7A8AA0") if pal.dark else QColor("#C9D3E0"))
            p = QPainter(bg)
            p.drawImage(0, 0, img)
            p.end()
            path = out / f"panel-{name}-{tag}.png"
            bg.save(str(path))
            paths.append(path)
        from airdops.ui.welcome import Welcome

        w = Welcome(cable_installed=False, on_done=lambda _o: None, on_get_cable=lambda: None)
        w.adjustSize()
        img = w.grab().toImage()
        bg = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        bg.fill(QColor("#7A8AA0") if pal.dark else QColor("#C9D3E0"))
        p = QPainter(bg)
        p.drawImage(0, 0, img)
        p.end()
        path = out / f"welcome-{tag}.png"
        bg.save(str(path))
        paths.append(path)
        toast = Toast()
        toast.set_state(CONNECTED)
        img = _shoot(toast)
        bg = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
        bg.fill(QColor("#7A8AA0") if pal.dark else QColor("#C9D3E0"))
        p = QPainter(bg)
        p.drawImage(0, 0, img)
        p.end()
        path = out / f"toast-{tag}.png"
        bg.save(str(path))
        paths.append(path)
    widgets.set_palette(theme.LIGHT)
    return paths


