"""Parser for the Bluetooth LE "proximity pairing" message AirPods broadcast.

AirPods (and Beats) continuously advertise a small Apple manufacturer-data
packet (company id 0x004C, message type 0x07) that contains the battery level
of each bud and the case, charging flags and in-ear sensor bits. macOS and iOS
use it for the battery widget; we use it the same way.

This module is pure Python with no Windows dependencies so it can be unit
tested anywhere. It never looks at, stores or returns the Bluetooth address
of the sender.

Byte layout (after the 2-byte company id, which bleak strips for us):

    0      message type (0x07)
    1      remaining length (0x19 for AirPods)
    2      prefix / pairing flag
    3..4   model id (big-endian, e.g. 0x1420 = AirPods Pro 2)
    5      status: bit1 this bud in ear, bit2 both in case,
                   bit3 other bud in ear, bit5 broadcasting bud is the LEFT one
    6      battery: low nibble = broadcasting bud, high nibble = other bud
    7      low nibble = case battery,
           high nibble flags: bit0 this bud charging, bit1 other bud charging,
                              bit2 case charging
    8      lid open counter
    9      colour
    10..   encrypted payload (ignored)

Battery nibbles are 0-10 (x10 = percent); 15 means "unknown / not present".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

APPLE_COMPANY_ID = 0x004C
PROXIMITY_PAIRING_TYPE = 0x07
_MIN_LENGTH = 10

# Model ids observed in proximity pairing messages. Unknown ids still parse;
# they are just shown as a generic name.
MODELS: dict[int, str] = {
    0x0220: "AirPods",
    0x0F20: "AirPods 2",
    0x1320: "AirPods 3",
    0x1920: "AirPods 4",
    0x1B20: "AirPods 4 (ANC)",
    0x0E20: "AirPods Pro",
    0x1420: "AirPods Pro 2",
    0x2420: "AirPods Pro 2 (USB-C)",
    0x0A20: "AirPods Max",
    0x1F20: "AirPods Max (USB-C)",
}

# Single-unit headphones: report one battery only.
_SINGLE_UNIT = {0x0A20, 0x1F20}


@dataclass(frozen=True)
class PodsStatus:
    model_id: int
    model_name: str
    left_battery: Optional[int]  # percent, None if unknown
    right_battery: Optional[int]
    case_battery: Optional[int]
    left_charging: bool
    right_charging: bool
    case_charging: bool
    left_in_ear: bool
    right_in_ear: bool
    single_unit: bool = False

    @property
    def lowest_bud_battery(self) -> Optional[int]:
        values = [v for v in (self.left_battery, self.right_battery) if v is not None]
        return min(values) if values else None

    @property
    def buds_in_ear(self) -> int:
        return int(self.left_in_ear) + int(self.right_in_ear)


def _battery(nibble: int) -> Optional[int]:
    if 0 <= nibble <= 10:
        return nibble * 10
    return None


def model_name(model_id: int) -> str:
    return MODELS.get(model_id, f"AirPods (model {model_id:#06x})")


def parse_proximity(data: bytes) -> Optional[PodsStatus]:
    """Parse Apple manufacturer data. Returns None if it is not an AirPods
    proximity-pairing message."""
    if not data or len(data) < _MIN_LENGTH or data[0] != PROXIMITY_PAIRING_TYPE:
        return None

    model_id = (data[3] << 8) | data[4]
    status = data[5]
    batt = data[6]
    flags_case = data[7]

    left_broadcasting = bool(status & 0x20)
    this_in_ear = bool(status & 0x02)
    other_in_ear = bool(status & 0x08)

    this_batt = _battery(batt & 0x0F)
    other_batt = _battery((batt >> 4) & 0x0F)
    case_batt = _battery(flags_case & 0x0F)

    charge_flags = (flags_case >> 4) & 0x0F
    this_charging = bool(charge_flags & 0x01)
    other_charging = bool(charge_flags & 0x02)
    case_charging = bool(charge_flags & 0x04)

    if left_broadcasting:
        left_b, right_b = this_batt, other_batt
        left_c, right_c = this_charging, other_charging
        left_e, right_e = this_in_ear, other_in_ear
    else:
        left_b, right_b = other_batt, this_batt
        left_c, right_c = other_charging, this_charging
        left_e, right_e = other_in_ear, this_in_ear

    single = model_id in _SINGLE_UNIT
    if single:
        # Headphones report one battery; mirror it and ignore ear bits.
        level = this_batt if this_batt is not None else other_batt
        left_b = right_b = level
        case_batt = None
        left_e = right_e = this_in_ear

    return PodsStatus(
        model_id=model_id,
        model_name=model_name(model_id),
        left_battery=left_b,
        right_battery=right_b,
        case_battery=case_batt,
        left_charging=left_c,
        right_charging=right_c,
        case_charging=case_charging,
        left_in_ear=left_e,
        right_in_ear=right_e,
        single_unit=single,
    )


def family(name: str) -> str:
    """Coarse product family used to avoid showing a stranger's AirPods.

    'Headphones (AirPods Pro)' -> 'pro', 'AirPods Pro 2' -> 'pro',
    'AirPods Max' -> 'max', anything else -> 'airpods'.
    """
    lowered = name.lower()
    if "max" in lowered:
        return "max"
    if "pro" in lowered:
        return "pro"
    return "airpods"
