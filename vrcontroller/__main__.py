"""vrcontroller [run|pair] [--config PATH] [--mac MAC] [--status-port N] [-v]"""
import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from evdev import UInputError

from . import config, protocol
from . import bluez
from .daemon import Daemon, stopping
from .status import StatusServer

log = logging.getLogger("vrcontroller")

FIND_INTERVAL = 30.0  # seconds between looks for a paired controller


async def wait_for_controller(auto_pair: bool) -> tuple[str, str]:
    """Wait until a paired controller exists (the unit also runs for users without one).

    With auto_pair, pair the first Gear VR Controller that advertises.
    """
    logged = False
    while True:
        try:
            found = await bluez.find_controller()
            if not found and auto_pair:
                if not logged:
                    log.info("no paired controller; waiting for one to pair with "
                             "(hold home until the LED blinks)")
                    logged = True
                found = await bluez.pair_controller(bluez.PAIR_SCAN_TIMEOUT)
                if found:
                    return found
                continue  # the scan itself took PAIR_SCAN_TIMEOUT
        except Exception as e:  # BlueZ not running, adapter off, pairing refused: retry later
            if stopping():
                raise asyncio.CancelledError from e
            found = None
            reason = f"Bluetooth not ready ({e})"
        else:
            reason = "no paired Gear VR Controller; pair it with `vrcontroller pair`"
        if found:
            return found
        if not logged:
            log.info("%s; checking again every %d s", reason, FIND_INTERVAL)
            logged = True
        await asyncio.sleep(FIND_INTERVAL)


async def pair_command(timeout: float) -> int:
    """`vrcontroller pair`: forget old pairings and pair the controller in pairing mode."""
    old = tuple(path for path, props in (await bluez.devices()).items()
                if bluez.is_controller(props))
    print(f"Hold home on the controller until the LED blinks; waiting up to {timeout:.0f} s...")
    try:
        found = await bluez.pair_controller(timeout, remove_paths=old)
    except bluez.BluezError as e:
        print(f"Pairing failed: {e}")
        return 1
    if not found:
        print("No Gear VR Controller found. Is it in pairing mode and close to the computer?")
        return 1
    print(f"Paired {found[0]}. The daemon will connect to it on its own.")
    return 0


async def main(args) -> int:
    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        log.error("config error: %s", e)
        return 2

    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, task.cancel)
    try:
        if args.command == "pair":
            return await pair_command(args.timeout)
        return await run(args, cfg)
    except asyncio.CancelledError:
        log.info("stopped")
        return 0


async def run(args, cfg) -> int:
    if args.mac:
        address, path = args.mac.upper(), protocol.bluez_path(args.mac)
    else:
        address, path = await wait_for_controller(cfg.auto_pair)

    try:
        daemon = Daemon(cfg, address, path)
    except (OSError, UInputError) as e:
        log.error("cannot create uinput device (%s); is /dev/uinput writable? see README", e)
        return 1

    if args.status_port:
        try:
            await StatusServer(daemon, port=args.status_port).start()
        except OSError as e:
            log.warning("status page disabled: cannot listen on port %d (%s)", args.status_port, e)

    await daemon.run()
    return 0


def cli() -> None:
    p = argparse.ArgumentParser(prog="vrcontroller", description=__doc__)
    p.add_argument("command", nargs="?", choices=("run", "pair"), default="run",
                   help="run the daemon (default) or pair a controller in pairing mode")
    p.add_argument("--timeout", type=float, default=60,
                   help="pair: seconds to wait for the controller (default: 60)")
    p.add_argument("--config", type=Path, help=f"default: {config.default_path()}")
    p.add_argument("--mac", help="controller address (default: first paired Gear VR Controller)")
    p.add_argument("--status-port", type=int, default=8765,
                   help="local status page port, 0 to disable (default: 8765)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if not args.verbose:
        logging.getLogger("bleak").setLevel(logging.WARNING)
    sys.exit(asyncio.run(main(args)))


if __name__ == "__main__":
    cli()
