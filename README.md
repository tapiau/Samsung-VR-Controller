# Samsung VR Controller

Use a Samsung Gear VR Controller as a general-purpose input device for controlling the operating system.

## Background

I own a Samsung Gear VR Controller (originally sold as an accessory for the Gear VR headset). It is a small handheld Bluetooth Low Energy device with a rich set of inputs, and I would like to reuse it to control my system (e.g. mouse pointer, scrolling, media keys, shortcuts) instead of letting it sit unused.

## Hardware

Inputs available on the controller:

- **Touchpad**: circular, reports finger position and is also clickable
- **Buttons**: trigger, home, back, volume up and volume down
- **Motion sensors**: accelerometer, gyroscope and magnetometer (confirmed; see `doc/protocol.md`)
- **Connectivity**: Bluetooth Low Energy

## Goal

Turn the controller's inputs into system input events, for example:

- touchpad → mouse movement / scrolling
- touchpad click and trigger → mouse buttons
- other buttons → keyboard shortcuts or media keys
- motion sensors → pointer control or gestures

## Status

Touchpad and buttons work as mouse and keys through a uinput daemon. Gyro "air mouse"
pointing is planned. BLE protocol notes: `doc/protocol.md`.

## Setup

1. Pair the controller (hold home until the LED blinks):
   `bluetoothctl` → `scan on` → `pair <MAC>` → `trust <MAC>`.
2. Allow your user to create virtual input devices (one-time, needs sudo):
   ```
   echo 'KERNEL=="uinput", MODE="0660", TAG+="uaccess", OPTIONS+="static_node=uinput"' \
     | sudo tee /etc/udev/rules.d/60-uinput.rules
   sudo udevadm control --reload
   sudo modprobe uinput && echo uinput | sudo tee /etc/modules-load.d/uinput.conf
   ```
   The module must be loaded for the rule to apply; `/dev/uinput` exists even when it is not.
3. Python environment:
   ```
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```

## Usage

```
.venv/bin/python -m vrcontroller          # finds the paired controller by name
.venv/bin/python -m vrcontroller -v       # debug logging
```

If the controller is asleep the daemon keeps scanning; press home to wake it.
Live status (connection, battery, buttons, touchpad, IMU, emitted events, raw packet):
<http://127.0.0.1:8765/> (`--status-port 0` disables it).

If it connects but drops during service discovery every time, the controller has lost
its pairing: `bluetoothctl remove <MAC>`, then pair again (step 1).

Default mapping:

| Input | Action |
|---|---|
| Slide on touchpad | move pointer |
| Trigger | left click (hold to drag) |
| Touchpad click | right click |
| Back held + slide | scroll; a short press of back sends `KEY_BACK` |
| Home | Super |
| Vol+ / Vol− | volume up / down |

Change any of this in `~/.config/vrcontroller/config.toml`; see `config.example.toml`
for every key. Restart the daemon after editing.

### Autostart

```
mkdir -p ~/.config/systemd/user
cp systemd/vrcontroller.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now vrcontroller
journalctl --user -u vrcontroller -f
```

The unit assumes the repo is in `~/Workspace/gitlab/ai/samsung-vr-controller`.

## Tools and tests

- `tools/dump.py` prints raw and decoded packets (`--log FILE` saves them).
- Tests: `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest`
