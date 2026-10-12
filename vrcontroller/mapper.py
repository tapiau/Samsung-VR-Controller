"""Turn decoded controller packets into input events. Pure logic, no I/O."""
import math
from typing import Optional

from evdev import ecodes as e

from .config import Config
from .protocol import Packet

Event = tuple[int, int, int]  # (type, code, value), as written to uinput
SYN: Event = (e.EV_SYN, e.SYN_REPORT, 0)

POINTER_GAIN = 2.5  # pixels per touchpad unit at speed 1.0 (full pad swipe ~750 px)
ACCEL_REF = 3.0  # touchpad units per packet where acceleration starts to add speed
SCROLL_UNITS_PER_NOTCH = 20.0  # touchpad units of slide per wheel notch at speed 1.0
MAX_STEP = 80  # touchpad units in one packet; larger jumps are glitches (seen at lift-off)
SLIDE_THRESHOLD = 10  # touchpad units the finger must travel before a modifier press counts as a slide
HI_RES_PER_NOTCH = 120


class Mapper:
    def __init__(self, config: Config):
        self.config = config
        self.buttons: frozenset[str] = frozenset()
        self.touch: Optional[tuple[int, int]] = None
        self.smooth: Optional[tuple[float, float]] = None  # filtered finger position
        self.pointer_rem = [0.0, 0.0]
        self.scroll_hires = [0.0, 0.0]  # [vertical, horizontal] in hi-res units, not yet emitted
        self.scroll_notch = [0, 0]  # hi-res units emitted since the last legacy notch
        self.held: set[int] = set()  # codes currently reported as pressed
        self.modifier_held = False
        self.modifier_travel = 0.0
        self.modifier_slid = False

    def capabilities(self) -> dict[int, list[int]]:
        keys = {e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE}
        for codes in self.config.buttons.values():
            keys.update(codes)
        return {
            e.EV_KEY: sorted(keys),
            e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL,
                       e.REL_WHEEL_HI_RES, e.REL_HWHEEL_HI_RES],
        }

    def feed(self, packet: Packet) -> list[Event]:
        events: list[Event] = []
        self._buttons(packet.buttons, events)
        self._touch(packet.touch, events)
        if events and events[-1] != SYN:
            events.append(SYN)
        return events

    def release_all(self) -> list[Event]:
        """Release everything still pressed (e.g. on disconnect) and reset state."""
        events = [(e.EV_KEY, code, 0) for code in sorted(self.held)]
        if events:
            events.append(SYN)
        self.__init__(self.config)
        return events

    # -- buttons ---------------------------------------------------------

    def _buttons(self, pressed: frozenset[str], events: list[Event]) -> None:
        modifier = self.config.scroll_modifier
        for name in sorted(pressed - self.buttons):
            if name == modifier:
                self.modifier_held = True
                self.modifier_travel = 0.0
                self.modifier_slid = False
            else:
                self._press(self.config.buttons[name], events)
        for name in sorted(self.buttons - pressed):
            if name == modifier:
                if self.modifier_held and not self.modifier_slid:
                    self._tap(self.config.buttons[name], events)
                self.modifier_held = False
            else:
                self._release(self.config.buttons[name], events)
        self.buttons = pressed

    def _press(self, codes: tuple[int, ...], events: list[Event]) -> None:
        for code in codes:
            if code not in self.held:
                self.held.add(code)
                events.append((e.EV_KEY, code, 1))

    def _release(self, codes: tuple[int, ...], events: list[Event]) -> None:
        for code in reversed(codes):
            if code in self.held:
                self.held.discard(code)
                events.append((e.EV_KEY, code, 0))

    def _tap(self, codes: tuple[int, ...], events: list[Event]) -> None:
        if not codes:
            return
        self._press(codes, events)
        events.append(SYN)  # press and release in separate frames, or it may be ignored
        self._release(codes, events)

    # -- touchpad --------------------------------------------------------

    def _touch(self, touch: Optional[tuple[int, int]], events: list[Event]) -> None:
        prev, self.touch = self.touch, touch
        if touch is None or prev is None:
            # Finger down or lifted: start fresh so a new touch never makes the pointer jump.
            self.smooth = None if touch is None else (float(touch[0]), float(touch[1]))
            self.pointer_rem = [0.0, 0.0]
            self.scroll_hires = [0.0, 0.0]
            return
        if math.dist(touch, prev) > MAX_STEP:
            self.smooth = (float(touch[0]), float(touch[1]))  # skip the glitch, don't move
            return
        # Exponential smoothing: packets arrive in bursts, and the raw position is jerky.
        k = 1.0 - self.config.pointer_smoothing
        old = self.smooth
        self.smooth = (old[0] + k * (touch[0] - old[0]), old[1] + k * (touch[1] - old[1]))
        dx, dy = self.smooth[0] - old[0], self.smooth[1] - old[1]
        if dx == 0 and dy == 0:
            return
        if self.modifier_held:
            self._scroll(dx, dy, events)
        else:
            self._move(dx, dy, events)

    def _move(self, dx: float, dy: float, events: list[Event]) -> None:
        gain = POINTER_GAIN * self.config.pointer_speed
        dist = math.hypot(dx, dy)
        if self.config.pointer_acceleration != 1.0 and dist > ACCEL_REF:
            gain *= (dist / ACCEL_REF) ** (self.config.pointer_acceleration - 1)
        for axis, (code, d) in enumerate(((e.REL_X, dx), (e.REL_Y, dy))):
            value = d * gain + self.pointer_rem[axis]
            whole = int(value)
            self.pointer_rem[axis] = value - whole
            if whole:
                events.append((e.EV_REL, code, whole))

    def _scroll(self, dx: float, dy: float, events: list[Event]) -> None:
        if not self.modifier_slid:
            self.modifier_travel += math.hypot(dx, dy)
            if self.modifier_travel < SLIDE_THRESHOLD:
                return
            self.modifier_slid = True
        # Wheel: positive = up / right. Classic: finger down scrolls down (like a scrollbar).
        sign = 1 if self.config.scroll_natural else -1
        per_unit = HI_RES_PER_NOTCH * self.config.scroll_speed / SCROLL_UNITS_PER_NOTCH
        axes = ((0, e.REL_WHEEL_HI_RES, e.REL_WHEEL, sign * dy),
                (1, e.REL_HWHEEL_HI_RES, e.REL_HWHEEL, -sign * dx))
        for axis, hires_code, notch_code, d in axes:
            value = d * per_unit + self.scroll_hires[axis]
            whole = int(value)
            self.scroll_hires[axis] = value - whole
            if not whole:
                continue
            events.append((e.EV_REL, hires_code, whole))
            self.scroll_notch[axis] += whole
            notches = int(self.scroll_notch[axis] / HI_RES_PER_NOTCH)
            if notches:
                self.scroll_notch[axis] -= notches * HI_RES_PER_NOTCH
                events.append((e.EV_REL, notch_code, notches))
