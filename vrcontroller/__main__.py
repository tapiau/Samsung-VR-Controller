"""Run the daemon: python -m vrcontroller [--config PATH] [--mac MAC] [-v]"""
import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from evdev import UInputError

from . import config, protocol
from .daemon import Daemon, find_controller
from .status import StatusServer

log = logging.getLogger("vrcontroller")


async def main(args) -> int:
    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        log.error("config error: %s", e)
        return 2

    if args.mac:
        address, path = args.mac.upper(), protocol.bluez_path(args.mac)
    else:
        found = await find_controller()
        if not found:
            log.error("no paired Gear VR Controller found; pair it with bluetoothctl first")
            return 1
        address, path = found

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

    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, task.cancel)
    try:
        await daemon.run()
    except asyncio.CancelledError:
        log.info("stopped")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="vrcontroller", description=__doc__)
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
