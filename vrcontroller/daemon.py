"""Keep a BLE connection to the controller and replay its input through uinput."""
import asyncio
import logging
import time
from collections import deque
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDeviceNotFoundError, BleakError
from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from evdev import UInput, ecodes

from . import protocol
from .config import Config
from .mapper import Mapper

log = logging.getLogger("vrcontroller")

DEVICE_NAME_PREFIX = "Gear VR Controller"
CONNECT_TIMEOUT = 20.0
SCAN_TIMEOUT = 30.0  # per scan; the loop keeps scanning until home wakes the controller
RETRY_DELAY = 2.0
KEEPALIVE_INTERVAL = 1.0
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


async def bluez_devices() -> dict[str, dict]:
    """BlueZ Device1 properties keyed by object path."""
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        intro = await bus.introspect("org.bluez", "/")
        manager = bus.get_proxy_object("org.bluez", "/", intro).get_interface(
            "org.freedesktop.DBus.ObjectManager")
        objects = await manager.call_get_managed_objects()
    finally:
        bus.disconnect()
    return {path: {k: v.value for k, v in ifaces["org.bluez.Device1"].items()}
            for path, ifaces in objects.items() if "org.bluez.Device1" in ifaces}


async def find_controller() -> Optional[tuple[str, str]]:
    """Return (address, BlueZ path) of the first paired Gear VR Controller."""
    for path, dev in sorted((await bluez_devices()).items()):
        if dev.get("Paired") and dev.get("Name", "").startswith(DEVICE_NAME_PREFIX):
            return dev["Address"], path
    return None


async def is_connected(path: str) -> bool:
    return bool((await bluez_devices()).get(path, {}).get("Connected"))


def event_name(etype: int, code: int) -> str:
    name = ecodes.bytype[etype].get(code, str(code))
    return name if isinstance(name, str) else name[0]  # aliases come as a tuple


class Daemon:
    def __init__(self, config: Config, address: str, path: str):
        self.address = address
        self.path = path
        self.mapper = Mapper(config)
        self.ui = UInput(self.mapper.capabilities(), name="Gear VR Controller (vrcontroller)")
        # ui.device stays None when /dev/input/event* is not readable by us (normal without
        # the input group); the device is created all the same.
        node = self.ui.device.path if self.ui.device else "event node not readable"
        log.info("virtual input device '%s' created (%s)", self.ui.name, node)
        self.config = config
        self.packets = 0
        self.events = 0
        self.last: Optional[protocol.Packet] = None
        self.raw = b""
        self.state = "starting"
        self.battery: Optional[int] = None
        self.packet_times: deque[float] = deque(maxlen=200)
        self.recent_events: deque[tuple[float, str, int]] = deque(maxlen=40)

    def emit(self, events):
        now = time.time()
        for etype, code, value in events:
            self.ui.write(etype, code, value)
            if etype != ecodes.EV_SYN:
                self.recent_events.append((now, event_name(etype, code), value))
        self.events += len(events)

    def snapshot(self) -> dict:
        """Current state for the status page."""
        now = time.monotonic()
        rate = sum(1 for t in self.packet_times if now - t <= 1.0)
        p = self.last
        return {
            "state": self.state,
            "address": self.address,
            "battery": self.battery,
            "rate": rate,
            "packet": None if p is None else {
                "touch": p.touch,
                "buttons": sorted(p.buttons),
                "imu": [{"t": s.timestamp, "accel": s.accel, "gyro": s.gyro} for s in p.imu],
                "mag": p.mag,
                "raw": self.raw.hex(),
            },
            "events": list(self.recent_events),
            "config": {
                "scroll_modifier": self.config.scroll_modifier,
                "buttons": {name: [event_name(ecodes.EV_KEY, c) for c in codes]
                            for name, codes in self.config.buttons.items()},
            },
        }

    def on_data(self, _, data: bytearray) -> None:
        if len(data) != protocol.PACKET_LEN:
            log.debug("ignoring %d-byte notification %s", len(data), data.hex())
            return
        self.packets += 1
        self.packet_times.append(time.monotonic())
        self.raw = bytes(data)
        self.last = protocol.decode(self.raw)
        self.emit(self.mapper.feed(self.last))

    async def report(self, interval: float = 5.0) -> None:
        while True:
            await asyncio.sleep(interval)
            p = self.last
            log.info("%.1f packets/s, %d events; touch=%s buttons=%s",
                     self.packets / interval, self.events, p.touch if p else None,
                     ",".join(sorted(p.buttons)) if p else None)
            self.packets = self.events = 0

    async def session(self) -> None:
        """One connection: start the stream, keep it alive until disconnect."""
        disconnected = asyncio.Event()
        self.state = "connecting"
        if await is_connected(self.path):
            # Already connected (e.g. by bluetoothctl): it does not advertise, so a scan
            # would never find it. Use the BlueZ object directly.
            device = BLEDevice(self.address, None, {"path": self.path})
        else:
            # Asleep or just woken: BlueZ only connects after it has seen an advert.
            self.state = "scanning (press home to wake the controller)"
            device = await BleakScanner.find_device_by_address(self.address, timeout=SCAN_TIMEOUT)
            if device is None:
                raise BleakDeviceNotFoundError(self.address, "not advertising")
        client = BleakClient(device, disconnected_callback=lambda _: disconnected.set(),
                             timeout=CONNECT_TIMEOUT)
        async with client:
            log.info("connected to %s", self.address)
            self.state = "connected"
            try:
                self.battery = (await client.read_gatt_char(BATTERY_UUID))[0]
            except BleakError as ex:
                log.debug("battery read failed: %s", ex)
            await client.start_notify(protocol.DATA_UUID, self.on_data)
            for cmd in protocol.START_SEQUENCE:
                await client.write_gatt_char(protocol.CMD_UUID, cmd, response=True)
            while not disconnected.is_set():
                try:
                    await asyncio.wait_for(disconnected.wait(), KEEPALIVE_INTERVAL)
                except asyncio.TimeoutError:
                    await client.write_gatt_char(protocol.CMD_UUID, protocol.CMD_KEEPALIVE,
                                                 response=True)
        self.state = "disconnected"
        log.info("disconnected")

    async def run(self) -> None:
        waiting_logged = False
        reporter = asyncio.create_task(self.report())
        try:
            while True:
                try:
                    await self.session()
                    waiting_logged = False
                except (BleakError, asyncio.TimeoutError, EOFError, OSError) as ex:
                    level = logging.DEBUG if waiting_logged else logging.INFO
                    log.log(level, "controller not reachable (%s: %s); press home to wake it",
                            type(ex).__name__, ex)
                    waiting_logged = True
                    self.state = f"not connected ({type(ex).__name__}: {ex})"
                finally:
                    self.emit(self.mapper.release_all())
                await asyncio.sleep(RETRY_DELAY)
        finally:
            reporter.cancel()
            self.emit(self.mapper.release_all())
            self.ui.close()
