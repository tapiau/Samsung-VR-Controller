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

## Install (Debian 13 package)

```
sudo apt install dh-python pybuild-plugin-pyproject python3-all python3-pytest \
    python3-bleak python3-evdev python3-dbus-fast        # build dependencies
dpkg-buildpackage -us -uc -b                             # builds ../vrcontroller_0.1.0_all.deb
sudo apt install ../vrcontroller_0.1.0_all.deb
```

The package installs the daemon (`/usr/bin/vrcontroller`), a udev rule giving the logged-in
user access to `/dev/uinput`, uinput module autoload, and a systemd user unit that is enabled
for everyone and starts with the graphical session. Start it right away with
`systemctl --user start vrcontroller`; logs: `journalctl --user -u vrcontroller -f`.

Pairing is automatic: hold home until the LED blinks and the daemon pairs the first
Gear VR Controller it hears (disable with `[device] auto_pair = false`). It also pairs again
when the controller has forgotten the pairing. Manual (re)pairing: `vrcontroller pair`.

Live status (connection, battery, buttons, touchpad, IMU, emitted events, raw packet):
<http://127.0.0.1:8765/> (`--status-port 0` disables it).

## Configuration

Default mapping:

| Input | Action |
|---|---|
| Slide on touchpad | move pointer |
| Trigger | left click (hold to drag) |
| Touchpad click | right click |
| Back held + slide | scroll; a short press of back sends `KEY_BACK` |
| Home | Super |
| Vol+ / Vol− | volume up / down |

Change any of this in `~/.config/vrcontroller/config.toml`; every key is documented in
`config.example.toml` (installed as `/usr/share/doc/vrcontroller/examples/`).
Restart after editing: `systemctl --user restart vrcontroller`.

## Development (venv)

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m vrcontroller -v
```

Without the package, set up `/dev/uinput` access by hand (once, needs sudo):
```
echo 'KERNEL=="uinput", MODE="0660", TAG+="uaccess", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/60-uinput.rules
sudo udevadm control --reload
sudo modprobe uinput && echo uinput | sudo tee /etc/modules-load.d/uinput.conf
```
The module must be loaded for the rule to apply; `/dev/uinput` exists even when it is not.

## Tools and tests

- `tools/dump.py` prints raw and decoded packets (`--log FILE` saves them).
- Tests: `.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest`
  (they also run during `dpkg-buildpackage`, against Debian's library versions)

## License

MIT, see `LICENSE`.
