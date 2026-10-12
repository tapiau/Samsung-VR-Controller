# Gear VR Controller BLE protocol
**Created:** 2026-10-12 17:05

Verified on ET-YO324 (firmware `YO324XXU0AQD4`, MAC `2C:BA:BA:5E:1B:6C`) with `tools/dump.py`.
Raw captures: `rest.log`, `buttons.log`, `ytest.log` (gitignored, local only).

## Connection
- BLE, public address, pairs without PIN.
- When it's already connected the controller doesn't advertise, so connect through the BlueZ
  object path (`/org/bluez/hci0/dev_2C_BA_BA_5E_1B_6C`) rather than by scanning.

## Characteristics (vendor service `4f63756c-7573-2054-6872-65656d6f7465`)
| UUID | Flags | Role |
|---|---|---|
| `c8c51726-81bc-483b-a052-f7a14ea3d281` | read, notify | data stream |
| `c8c51726-81bc-483b-a052-f7a14ea3d282` | read, write | commands (2 bytes) |

## Commands
| Bytes | Effect (observed) |
|---|---|
| `0800` then `0100` | VR mode + sensor mode: ~43 packets/s, magnetometer active. **Use this.** |
| `0100` alone | ~3 packets/s, magnetometer bytes zero |
| `0800` alone | almost no packets |
| `0400` | keepalive (sent every 1 s by the script) |
| `0000` | stop |

## Data packet (60 bytes, little endian)
| Offset | Type | Content |
|---|---|---|
| 0, 16, 32 | u32 | sample timestamp, ~1 MHz ticks (samples ~4.8 ms apart) |
| +4 | 3 × i16 | accelerometer X, Y, Z; 1 g ≈ 2048 |
| +10 | 3 × i16 | gyroscope X, Y, Z; at rest within ±15 (bias) |
| 48 | 3 × i16 | magnetometer X, Y, Z (VR mode only) |
| 54 | u8 | high nibble: `0x1` = finger on touchpad, `0x2` = no touch (`0x0` briefly on release); low nibble = touch X bits 9–6 |
| 55 | u8 | bits 7–2 = touch X bits 5–0; bits 1–0 = touch Y bits 9–8 |
| 56 | u8 | touch Y bits 7–0 |
| 57 | u8 | unknown (0x16 → 0x17 during the session) |
| 58 | u8 | buttons (below) |
| 59 | u8 | unknown, slowly decreasing (0x3b → 0x2f); maybe a temperature or status counter |

Each packet carries three IMU samples (offsets 0/16/32, each 16 bytes) but only one set of
touchpad, button and magnetometer values.

Touch coordinates: `x = (b54 & 0x0F) << 6 | b55 >> 2`, `y = (b55 & 0x03) << 8 | b56`.
Observed range: x 6–301, y 5–315 (the pad is circular, so the corners are never reached).
The orientation matches screen coordinates: x grows left → right, y grows top → bottom
(top = the edge away from the hand; a finger on it reads y ≈ 5, x ≈ 155). Centre ≈ (155, 160).

### Buttons (byte 58)
| Bit | Button |
|---|---|
| `0x01` | trigger |
| `0x02` | home |
| `0x04` | back |
| `0x08` | touchpad click |
| `0x10` | volume + |
| `0x20` | volume − |
| `0x40` | set while nothing is pressed (drops to `0x00` for one packet on release) |

## Open questions
- Meaning of bytes 57 and 59 and of bit `0x40`.
