"""Apple-style design tokens (iOS / macOS system colours, Inter typography).

Follows the Windows light/dark app setting, the way macOS follows its
appearance setting.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase

FONT_FAMILY = "Inter"
_FALLBACK = ["Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "Arial"]
_loaded = False


def _font_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "airdops" / "ui" / "fonts"
    return Path(__file__).resolve().parent / "fonts"


def load_fonts() -> None:
    global _loaded
    if _loaded:
        return
    for ttf in sorted(_font_dir().glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ttf))
    _loaded = True


def font(size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setFamilies([FONT_FAMILY, *_FALLBACK])
    f.setPixelSize(int(round(size)))
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    # Apple-like tracking: slightly tighter for larger text.
    if size >= 17:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98.5)
    return f


@dataclass(frozen=True)
class Palette:
    dark: bool
    window: QColor  # popover background
    border: QColor
    group: QColor  # inset grouped-list background
    separator: QColor
    label: QColor
    secondary: QColor
    tertiary: QColor
    fill: QColor  # segmented control track, ring track
    fill_strong: QColor
    knob: QColor
    segment_pill: QColor
    accent: QColor
    green: QColor
    orange: QColor
    red: QColor
    hover: QColor
    shadow: QColor


def _c(hex_rgb: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_rgb)
    c.setAlphaF(alpha)
    return c


LIGHT = Palette(
    dark=False,
    window=_c("#F2F2F7", 0.97),
    border=_c("#000000", 0.10),
    group=_c("#FFFFFF"),
    separator=_c("#3C3C43", 0.18),
    label=_c("#000000", 0.88),
    secondary=_c("#3C3C43", 0.62),
    tertiary=_c("#3C3C43", 0.32),
    fill=_c("#787880", 0.14),
    fill_strong=_c("#787880", 0.24),
    knob=_c("#FFFFFF"),
    segment_pill=_c("#FFFFFF"),
    accent=_c("#007AFF"),
    green=_c("#34C759"),
    orange=_c("#FF9500"),
    red=_c("#FF3B30"),
    hover=_c("#000000", 0.04),
    shadow=_c("#000000", 0.28),
)

DARK = Palette(
    dark=True,
    window=_c("#1C1C1E", 0.97),
    border=_c("#FFFFFF", 0.12),
    group=_c("#2C2C2E"),
    separator=_c("#545458", 0.55),
    label=_c("#FFFFFF", 0.92),
    secondary=_c("#EBEBF5", 0.60),
    tertiary=_c("#EBEBF5", 0.30),
    fill=_c("#767680", 0.24),
    fill_strong=_c("#767680", 0.36),
    knob=_c("#FFFFFF"),
    segment_pill=_c("#636366"),
    accent=_c("#0A84FF"),
    green=_c("#30D158"),
    orange=_c("#FF9F0A"),
    red=_c("#FF453A"),
    hover=_c("#FFFFFF", 0.05),
    shadow=_c("#000000", 0.55),
)


def system_prefers_dark() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except OSError:
        return False


def taskbar_is_dark() -> bool:
    """The tray glyph follows the *system* (taskbar) theme, not the app theme."""
    if sys.platform != "win32":
        return True
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return int(value) == 0
    except OSError:
        return True


def current() -> Palette:
    return DARK if system_prefers_dark() else LIGHT


def battery_color(p: Palette, level: int | None, charging: bool) -> QColor:
    if charging:
        return p.green
    if level is None:
        return p.tertiary
    if level <= 10:
        return p.red
    if level <= 20:
        return p.orange
    return p.green
