# BLE packet dump for Gear VR Controller
**Created:** 2026-10-12 16:47

## Goal
Confirm how the controller (ET-YO324, `2C:BA:BA:5E:1B:6C`) streams input data over BLE
and verify the packet layout, so later work (OS input mapping) builds on facts.

## Known (from discovery)
- Vendor service `4f63756c-7573-2054-6872-65656d6f7465`
  - `c8c51726-81bc-483b-a052-f7a14ea3d281` read/notify — assumed data stream
  - `c8c51726-81bc-483b-a052-f7a14ea3d282` read/write — assumed command channel
- Community reverse-engineering (unverified on this unit): 2-byte commands
  `0100` = sensor mode, `0800` = VR mode, `0400` = keepalive, `0000` = off;
  60-byte packets with accel/gyro/mag int16 LE, touchpad X/Y at bytes 54–56,
  button bits at byte 58.

## Plan
- [x] Python venv in `.venv` with `bleak`; `.venv` gitignored
- [x] `tools/dump.py`: connect, subscribe to `…d281`, send start command(s) to `…d282`,
      print hex + tentative decode, periodic keepalive, optional raw log to file
- [x] Run it, confirm notifications arrive (rate, packet length)
- [x] Interactive check with user: press each button, touch/click touchpad, move/rotate controller
- [x] Correct decode where it disagrees with observed data
- [x] Write findings to `doc/protocol.md`

## Success criteria
- Notifications arrive continuously at a measured rate while the script runs
- Each button (trigger, home, back, vol+, vol−, touchpad click) maps to a confirmed bit
- Touchpad X/Y change consistently with finger position (range recorded)
- Accelerometer shows ~1 g on the axis pointing up when lying still; gyro ~0 at rest

## Findings so far
- bleak cannot connect by MAC to an already-connected device (it scans, and the
  device does not advertise) → connect via BlueZ object path instead.
- Packets are always 60 bytes: 3 × 16-byte IMU samples (u32 ts + accel xyz + gyro xyz, int16 LE),
  bytes 48–53 = probably magnetometer, 54–59 = touchpad/buttons (TBD).
- Start command matters: `0100` alone ≈ 3 pkt/s; `0800` then `0100` ≈ 40–50 pkt/s (~130 samples/s).
- At rest the tail bytes 54–59 read `20 00 00 16 40 3b`.
- Button test (`buttons.log`): all six buttons map to bits of byte 58; touchpad X/Y decoded,
  range x 6–301, y 23–315. Full layout in `doc/protocol.md`.
- Y test (`ytest.log`): finger at top edge → y ≈ 5, so y grows top → bottom.

## Review
Shipped `tools/dump.py` (bleak-based packet dumper with decoder) and `doc/protocol.md`
(characteristics, commands, packet layout, button bits, touchpad coordinates).

Decisions:
- Connect through the BlueZ object path, not by scanning. bleak 3.0.2 scans before connecting
  by MAC, and a connected controller does not advertise (`BleakDeviceNotFoundError`).
- Start the stream with `0800` then `0100`: measured ~43 packets/s vs ~3/s with `0100` alone.
- Python venv in `.venv` (gitignored); raw `*.log` captures stay local.

Verification against the success criteria:
- Continuous stream: 2729 packets in 62.9 s (43.4/s), all 60 bytes long.
- Buttons: trigger, home, back, vol+, vol− and touchpad click each set a single bit of byte 58,
  in the order the user pressed them.
- Touchpad: x 6–301, y 5–315; left → right swipe raises x; finger at top edge gives y ≈ 5.
- IMU lying flat: accel ≈ (141, 434, 2060), |a| ≈ 2110 ≈ 1 g; gyro mean within ±7.

Not resolved: meaning of bytes 57 and 59 and of button bit `0x40`. None of them is needed for input mapping.
