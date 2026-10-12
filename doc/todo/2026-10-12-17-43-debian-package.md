# Debian package for vrcontroller
**Created:** 2026-10-12 17:43

## Goal
`apt install ./vrcontroller_*.deb` on this Debian 13 (trixie) machine gives a working daemon:
code, CLI, udev rule, uinput module autoload and a systemd user unit. No venv, no manual
steps except pairing the controller.

## Approach (chosen): native package on Debian's own Python libraries
- `Architecture: all`, `Depends: python3-bleak, python3-evdev, python3-dbus-fast, bluez`.
- Built with debhelper + dh-python (pybuild) from a new `pyproject.toml`.
- Trixie has older versions than the venv (bleak 0.22.3 vs 3.0.2, evdev 1.9.1 vs 2.0.0,
  dbus-fast 2.44.1 vs 5.2.0), so the code must work on both. Known spot: `BLEDevice(...)`
  takes a required `rssi` argument in bleak 0.22. Verified by running the tests and a live
  session in a second venv pinned to the trixie versions before packaging.

Alternative: bundle the PyPI versions inside the package (`/usr/lib/vrcontroller/`).
Exact tested versions, but `Architecture: amd64` (compiled evdev/dbus-fast), ~10 MB,
duplicates system libraries and gets no Debian security updates.

## Package contents
| Path | What |
|---|---|
| `/usr/lib/python3/dist-packages/vrcontroller/` | code + `status.html` |
| `/usr/bin/vrcontroller` | entry point (`python3 -m vrcontroller`) |
| `/usr/lib/udev/rules.d/60-vrcontroller-uinput.rules` | uinput access for the logged-in user (`uaccess`) |
| `/usr/lib/modules-load.d/vrcontroller.conf` | load `uinput` at boot |
| `/usr/lib/systemd/user/vrcontroller.service` | user unit, `ExecStart=/usr/bin/vrcontroller`, enabled globally (decided) |
| `/usr/share/doc/vrcontroller/config.example.toml` | config reference |

`postinst`: `modprobe uinput` and `udevadm trigger` so it works without a reboot.
Note: the `uaccess` rule lets any user logged in at the local seat create virtual input
devices (that is, inject keystrokes into their own session). That is normal for desktop
input tools, but the package description says so.

## Pairing (decided 2026-10-12)
Not in postinst (runs as root, non-interactive, controller would have to be in pairing mode at that
exact moment; BlueZ bonds are system-wide anyway). Instead:
- **Auto-pair in the daemon** (`[device] auto_pair = true`, default): no paired controller →
  scan for a "Gear VR Controller" advert → remove any stale BlueZ entry → Pair → Trusted.
  Same path repairs a lost bond: repeated "connected, then dropped during service discovery" →
  remove + pair again. Known risk, accepted: the advert looks the same in pairing mode and
  after wake-up, so it would also pair a stranger's unpaired Gear VR in range.
- **`vrcontroller pair`**: manual (re)pair with progress messages, for when auto-pair is off or fails.
- postinst only prints a hint.

## Plan
- [x] Daemon waits (re-checks every 30 s) when no controller is paired instead of exiting,
      since the globally enabled unit also runs for users without a controller
- [x] `vrcontroller/bluez.py` (was: pairing.py) (scan by name, remove stale, Pair, Trusted) + `[device] auto_pair`
      config + `vrcontroller pair` subcommand + stale-bond detection in the daemon
- [x] `pyproject.toml` (setuptools, package data `status.html`, console script `vrcontroller`)
- [x] Compat with trixie libs: venv `.venv-trixie` pinned to bleak 0.22.3 / evdev 1.9.1 /
      dbus-fast 2.44.1; fix what breaks; tests pass on both venvs
- [x] `debian/`: control, changelog, copyright, rules, install files, udev rule,
      modules-load file, user unit, postinst; `debian/source/format` = 3.0 (native)
- [x] User installs build deps (`dh-python`, `pybuild-plugin-pyproject`, `python3-pytest`)
- [x] `dpkg-buildpackage -us -uc -b`; tests run during the build
- [x] `lintian` clean (or remaining warnings explained)
- [ ] User installs the .deb; stop the venv daemon; unit is enabled globally, start it with
      `systemctl --user start vrcontroller` (later logins start it automatically)
- [ ] Live check: status page, pointer, buttons, scroll; `dpkg -L` shows the expected files
- [x] README: install-from-deb section; repo-local systemd unit removed (the package ships it)
- [ ] Write-up in `doc/done/`

## Success criteria
- Package builds from a clean tree with `dpkg-buildpackage -us -uc -b`, tests running inside the build.
- `lintian` reports no errors.
- After `apt install ./vrcontroller_0.1.0_all.deb` the user unit is enabled for all users; the daemon
  runs with no venv, `/dev/uinput` is writable without manual udev/modprobe steps,
  and pointer, buttons and the status page work like they do from the venv.
- A user without a paired controller: daemon keeps running quietly, no restart loop.
- `apt remove vrcontroller` removes everything except the user's `~/.config` file.

## Progress notes (2026-10-12)
- Build: `dpkg-buildpackage -us -uc -b` → `../vrcontroller_0.1.0_all.deb` (23 KB), 46 tests pass in
  the build against trixie's bleak 0.22.3 / evdev 1.9.1 / dbus-fast 2.44.1. `lintian`: no E/W
  (two justified overrides; one I: `status.html` flagged as documentation, it is the web UI).
- First build skipped dh_python3 (compat 13 needs `dh-sequence-python3`): files went to
  `python3.13/`, `__pycache__` was shipped, no `python3` dependency. Fixed.
- Unit starts with `graphical-session.target`, not `default.target`: outside a graphical
  session (SSH) `/dev/uinput` has no `uaccess` ACL and the daemon would restart-loop.
- Bug found while stopping the venv daemon: SIGINT/SIGTERM while connected could be swallowed,
  because bleak/dbus-fast cleanup replaced the CancelledError with EOFError, which the retry
  loop treats as "not reachable". Fixed with a `Task.cancelling()` check; 5/5 SIGTERM runs while
  connected now exit 0 in ~2 s.
- Auto-pair verified (pairing removed → daemon paired + trusted in 4 s → connected);
  `vrcontroller pair` verified with the daemon running (needed Pair() retries: the daemon's
  own reconnect raced the first attempt → "Page Timeout").
- Not yet verified: the installed package (the user reported "works", but at 18:1x
  `dpkg -l vrcontroller` showed it not installed and no user unit existed); automatic re-pair
  after the controller loses the bond on its own.
