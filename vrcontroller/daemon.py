"""Keep a BLE connection to the controller and replay its input through uinput."""
import asyncio
import logging
import time
from collections import deque
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakDeviceNotFoundError, BleakError
from evdev import UInput, ecodes

from . import bluez, protocol
from .config import Config
from .mapper import Mapper

log = logging.getLogger("vrcontroller")

CONNECT_TIMEOUT = 20.0
SCAN_TIMEOUT = 30.0  # per scan; the loop keeps scanning until home wakes the controller
RETRY_DELAY = 2.0
KEEPALIVE_INTERVAL = 1.0
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
# Connected, then dropped while BlueZ reads the services: the controller rejected our stored key,
# i.e. it forgot the pairing. After this many in a row, pair again (if auto_pair is on).
LOST_BOND_ATTEMPTS = 3
LOST_BOND_MESSAGE = "failed to discover services"


def stopping() -> bool:
    """True once the task was cancelled (SIGINT/SIGTERM).

    Cleanup code in bleak/dbus-fast can replace the CancelledError with another error
    (seen: EOFError while disconnecting), so retry loops must check this before retrying.
    """
    task = asyncio.current_task()
    return task is not None and task.cancelling() > 0


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
        if await bluez.is_connected(self.path):
            # Already connected (e.g. by bluetoothctl): it does not advertise, so a scan
            # would never find it. Use the BlueZ object directly.
            device = bluez.ble_device(self.address, self.path)
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

    async def repair(self) -> None:
        """The controller forgot the pairing: remove ours and pair again."""
        log.warning("controller keeps dropping the connection during setup; "
                    "it probably lost the pairing, pairing again")
        self.state = "pairing again (controller lost the pairing)"
        found = await bluez.pair_controller(bluez.PAIR_SCAN_TIMEOUT, remove_paths=(self.path,))
        if found:
            self.address, self.path = found

    async def run(self) -> None:
        waiting_logged = False
        lost_bond = 0
        reporter = asyncio.create_task(self.report())
        try:
            while True:
                try:
                    await self.session()
                    waiting_logged = False
                    lost_bond = 0
                except (BleakError, asyncio.TimeoutError, EOFError, OSError, bluez.BluezError) as ex:
                    if stopping():
                        raise asyncio.CancelledError from ex
                    lost_bond = lost_bond + 1 if LOST_BOND_MESSAGE in str(ex) else 0
                    if lost_bond >= LOST_BOND_ATTEMPTS and self.config.auto_pair:
                        lost_bond = 0
                        try:
                            await self.repair()
                        except (BleakError, bluez.BluezError) as e:
                            log.warning("pairing again failed: %s", e)
                        continue
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
