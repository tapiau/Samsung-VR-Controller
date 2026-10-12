#!/usr/bin/env python3
"""Dump raw notification packets from a Samsung Gear VR Controller.

Usage: .venv/bin/python tools/dump.py [--mac MAC] [--seconds N] [--cmd HEX ...] [--log FILE]
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

from bleak import BleakClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vrcontroller import bluez, protocol  # noqa: E402

def describe(b: bytes) -> str:
    if len(b) != protocol.PACKET_LEN:
        return f"(packet of {len(b)} bytes)"
    p = protocol.decode(b)
    s = p.imu[0]
    touch = f"({p.touch[0]},{p.touch[1]})" if p.touch else "-"
    return (f"ts={s.timestamp} acc={s.accel} gyr={s.gyro} mag={p.mag} "
            f"touch={touch} btn={','.join(sorted(p.buttons)) or '-'}")


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
            print(f"        {describe(bytes(data))}")

    async with BleakClient(bluez.ble_device(args.mac, protocol.bluez_path(args.mac))) as client:
        print(f"connected to {args.mac}")
        await client.start_notify(protocol.DATA_UUID, on_data)
        for cmd in args.cmd:
            await client.write_gatt_char(protocol.CMD_UUID, bytes.fromhex(cmd), response=True)
            print(f"sent command {cmd}")
            await asyncio.sleep(0.1)
        while time.monotonic() - start < args.seconds:
            await asyncio.sleep(1)
            await client.write_gatt_char(protocol.CMD_UUID, protocol.CMD_KEEPALIVE, response=True)
        await client.write_gatt_char(protocol.CMD_UUID, protocol.CMD_OFF, response=True)
        await client.stop_notify(protocol.DATA_UUID)

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
