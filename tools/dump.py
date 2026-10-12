#!/usr/bin/env python3
"""Dump raw notification packets from a Samsung Gear VR Controller.

Usage: .venv/bin/python tools/dump.py [--mac MAC] [--seconds N] [--cmd HEX ...] [--log FILE]
"""
import argparse
import asyncio
import struct
import time

from bleak import BleakClient
from bleak.backends.device import BLEDevice

DATA_UUID = "c8c51726-81bc-483b-a052-f7a14ea3d281"
CMD_UUID = "c8c51726-81bc-483b-a052-f7a14ea3d282"
KEEPALIVE = bytes.fromhex("0400")


def bluez_device(mac: str, adapter: str = "hci0") -> BLEDevice:
    """Address the device by its BlueZ object path, so bleak skips scanning.

    A paired controller that is already connected does not advertise, so the
    scan bleak normally runs before connecting would never find it.
    """
    path = f"/org/bluez/{adapter}/dev_{mac.upper().replace(':', '_')}"
    return BLEDevice(mac, None, {"path": path})

# Bits of byte 58; 0x40 is set when nothing is pressed (meaning unknown).
BUTTONS = {0x01: "trigger", 0x02: "home", 0x04: "back", 0x08: "click",
           0x10: "vol+", 0x20: "vol-"}


def decode(b: bytes) -> str:
    """Decode a 60-byte packet (layout in doc/protocol.md)."""
    if len(b) < 60:
        return f"(short packet: {len(b)} bytes)"
    ts, *acc = struct.unpack_from("<Ihhh", b, 0)
    gyro = struct.unpack_from("<hhh", b, 10)
    mag = struct.unpack_from("<hhh", b, 48)
    if b[54] & 0xF0 == 0x10:
        x = ((b[54] & 0x0F) << 6) | (b[55] >> 2)
        y = ((b[55] & 0x03) << 8) | b[56]
        touch = f"({x},{y})"
    else:
        touch = "-"
    pressed = [n for bit, n in BUTTONS.items() if b[58] & bit]
    return (f"ts={ts} acc={tuple(acc)} gyr={gyro} mag={mag} "
            f"touch={touch} btn={','.join(pressed) or '-'}")


async def main(args):
    count = 0
    log = open(args.log, "w") if args.log else None
    start = time.monotonic()

    def on_data(_, data: bytearray):
        nonlocal count
        count += 1
        t = time.monotonic() - start
        if log:
            log.write(f"{t:.4f} {data.hex()}\n")
        if count % args.every == 0:
            print(f"{t:7.3f} [{len(data)}] {data.hex()}")
            print(f"        {decode(bytes(data))}")

    async with BleakClient(bluez_device(args.mac)) as client:
        print(f"connected to {args.mac}")
        await client.start_notify(DATA_UUID, on_data)
        for cmd in args.cmd:
            await client.write_gatt_char(CMD_UUID, bytes.fromhex(cmd), response=True)
            print(f"sent command {cmd}")
            await asyncio.sleep(0.1)
        while time.monotonic() - start < args.seconds:
            await asyncio.sleep(1)
            await client.write_gatt_char(CMD_UUID, KEEPALIVE, response=True)
        await client.write_gatt_char(CMD_UUID, bytes.fromhex("0000"), response=True)
        await client.stop_notify(DATA_UUID)

    elapsed = time.monotonic() - start
    print(f"{count} packets in {elapsed:.1f}s ({count / elapsed:.1f}/s)")
    if log:
        log.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mac", default="2C:BA:BA:5E:1B:6C")
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--cmd", nargs="*", default=["0800", "0100"],
                   help="hex commands written to the command characteristic at start; "
                        "VR mode then sensor mode gives ~45 packets/s")
    p.add_argument("--every", type=int, default=10, help="print every Nth packet")
    p.add_argument("--log", help="write every raw packet to this file")
    asyncio.run(main(p.parse_args()))
