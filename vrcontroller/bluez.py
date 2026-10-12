"""BlueZ helpers over D-Bus: find, pair, trust and remove the controller."""
import asyncio
import logging
from typing import Optional

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

log = logging.getLogger("vrcontroller")

DEVICE_NAME_PREFIX = "Gear VR Controller"
PAIR_SCAN_TIMEOUT = 30.0
PAIR_ATTEMPTS = 3


class BluezError(Exception):
    pass


async def _call(path: str, interface: str, member: str, signature: str = "", body=()):
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        reply = await bus.call(Message(destination="org.bluez", path=path, interface=interface,
                                       member=member, signature=signature, body=list(body)))
    finally:
        bus.disconnect()
    if reply.message_type == MessageType.ERROR:
        raise BluezError(f"{member}: {reply.error_name} {' '.join(map(str, reply.body))}".strip())
    return reply.body


async def devices() -> dict[str, dict]:
    """BlueZ Device1 properties keyed by object path."""
    (objects,) = await _call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    return {path: {k: v.value for k, v in ifaces["org.bluez.Device1"].items()}
            for path, ifaces in objects.items() if "org.bluez.Device1" in ifaces}


def is_controller(props: dict) -> bool:
    return props.get("Name", "").startswith(DEVICE_NAME_PREFIX)


async def find_controller() -> Optional[tuple[str, str]]:
    """(address, path) of the first paired Gear VR Controller, if any."""
    for path, props in sorted((await devices()).items()):
        if props.get("Paired") and is_controller(props):
            return props["Address"], path
    return None


async def is_connected(path: str) -> bool:
    return bool((await devices()).get(path, {}).get("Connected"))


def ble_device(address: str, path: str) -> BLEDevice:
    """A BLEDevice for a known BlueZ object, so bleak connects without scanning.

    bleak 0.22 (Debian trixie) requires rssi; newer versions accept it as an extra kwarg.
    """
    return BLEDevice(address, None, {"path": path, "props": {}}, rssi=0)


async def remove(path: str) -> None:
    adapter = path.rsplit("/", 1)[0]
    try:
        await _call(adapter, "org.bluez.Adapter1", "RemoveDevice", "o", [path])
    except BluezError as e:
        if "DoesNotExist" not in str(e):
            raise


async def scan(timeout: float) -> Optional[BLEDevice]:
    """Wait for an advertising Gear VR Controller."""
    return await BleakScanner.find_device_by_filter(
        lambda d, adv: (adv.local_name or d.name or "").startswith(DEVICE_NAME_PREFIX),
        timeout=timeout)


async def pair_controller(timeout: float, remove_paths: tuple[str, ...] = ()) -> Optional[tuple[str, str]]:
    """Remove stale entries, find an advertising controller, pair and trust it.

    Returns (address, path), or None if no controller advertised within the timeout.
    """
    for path in remove_paths:
        log.info("removing old pairing %s", path)
        await remove(path)
    device = await scan(timeout)
    if device is None:
        return None
    path = device.details["path"]
    log.info("pairing with %s (%s)", device.address, device.name)
    # A running daemon may open its own connection at the same moment, and then our connection
    # attempt fails. Retrying pairs over whichever link exists by then.
    for attempt in range(1, PAIR_ATTEMPTS + 1):
        try:
            await _call(path, "org.bluez.Device1", "Pair")
            break
        except BluezError as e:
            if "AlreadyExists" in str(e):
                break
            if attempt == PAIR_ATTEMPTS:
                raise
            log.info("pairing attempt %d failed (%s), retrying", attempt, e)
            await asyncio.sleep(2)
    await _call(path, "org.freedesktop.DBus.Properties", "Set", "ssv",
                ["org.bluez.Device1", "Trusted", Variant("b", True)])
    log.info("paired and trusted %s", device.address)
    return device.address, path
