"""Gear VR Controller BLE protocol (layout documented in doc/protocol.md)."""
import struct
from dataclasses import dataclass
from typing import Optional

DATA_UUID = "c8c51726-81bc-483b-a052-f7a14ea3d281"
CMD_UUID = "c8c51726-81bc-483b-a052-f7a14ea3d282"

CMD_VR_MODE = bytes.fromhex("0800")
CMD_SENSOR = bytes.fromhex("0100")
CMD_KEEPALIVE = bytes.fromhex("0400")
CMD_OFF = bytes.fromhex("0000")
# VR mode then sensor mode gives ~43 packets/s; sensor mode alone only ~3/s.
START_SEQUENCE = (CMD_VR_MODE, CMD_SENSOR)

PACKET_LEN = 60

# Bits of byte 58. 0x40 is set while nothing is pressed (meaning unknown), so it is ignored.
BUTTON_BITS = {
    "trigger": 0x01,
    "home": 0x02,
    "back": 0x04,
    "click": 0x08,
    "vol_up": 0x10,
    "vol_down": 0x20,
}
BUTTON_NAMES = tuple(BUTTON_BITS)


@dataclass(frozen=True)
class ImuSample:
    timestamp: int  # ~1 MHz ticks
    accel: tuple[int, int, int]  # 1 g ~= 2048
    gyro: tuple[int, int, int]


@dataclass(frozen=True)
class Packet:
    imu: tuple[ImuSample, ImuSample, ImuSample]
    mag: tuple[int, int, int]
    touch: Optional[tuple[int, int]]  # (x, y), x grows left->right, y top->bottom; None = no finger
    buttons: frozenset[str]


def decode(b: bytes) -> Packet:
    if len(b) != PACKET_LEN:
        raise ValueError(f"expected {PACKET_LEN} bytes, got {len(b)}")
    imu = tuple(
        ImuSample(
            timestamp=struct.unpack_from("<I", b, off)[0],
            accel=struct.unpack_from("<hhh", b, off + 4),
            gyro=struct.unpack_from("<hhh", b, off + 10),
        )
        for off in (0, 16, 32)
    )
    if b[54] & 0xF0 == 0x10:
        touch = (((b[54] & 0x0F) << 6) | (b[55] >> 2), ((b[55] & 0x03) << 8) | b[56])
    else:
        touch = None
    buttons = frozenset(name for name, bit in BUTTON_BITS.items() if b[58] & bit)
    return Packet(imu=imu, mag=struct.unpack_from("<hhh", b, 48), touch=touch, buttons=buttons)


def bluez_path(mac: str, adapter: str = "hci0") -> str:
    return f"/org/bluez/{adapter}/dev_{mac.upper().replace(':', '_')}"
