from evdev import ecodes as e

from vrcontroller.config import build
from vrcontroller.mapper import SYN, Mapper
from vrcontroller.protocol import ImuSample, Packet

def cfg(overrides=None):
    """Config without smoothing, so pixel counts in these tests are exact."""
    overrides = {k: dict(v) for k, v in (overrides or {}).items()}
    overrides.setdefault("pointer", {}).setdefault("smoothing", 0.0)
    return build(overrides)


IMU = (ImuSample(0, (0, 0, 2048), (0, 0, 0)),) * 3


def pkt(touch=None, *buttons):
    return Packet(imu=IMU, mag=(0, 0, 0), touch=touch, buttons=frozenset(buttons))


def keys(events):
    return [(code, value) for t, code, value in events if t == e.EV_KEY]


def rel(events, code):
    return sum(v for t, c, v in events if t == e.EV_REL and c == code)


def run(mapper, packets):
    out = []
    for p in packets:
        out += mapper.feed(p)
    return out


def test_idle_produces_nothing():
    m = Mapper(cfg({}))
    assert run(m, [pkt(), pkt()]) == []


def test_trigger_press_and_release():
    m = Mapper(cfg({}))
    assert m.feed(pkt(None, "trigger")) == [(e.EV_KEY, e.BTN_LEFT, 1), SYN]
    assert m.feed(pkt(None, "trigger")) == []  # held: no repeat
    assert m.feed(pkt()) == [(e.EV_KEY, e.BTN_LEFT, 0), SYN]


def test_every_default_button():
    m = Mapper(cfg({}))
    expected = {"trigger": e.BTN_LEFT, "click": e.BTN_RIGHT, "home": e.KEY_LEFTMETA,
                "vol_up": e.KEY_VOLUMEUP, "vol_down": e.KEY_VOLUMEDOWN}
    for name, code in expected.items():
        assert keys(run(m, [pkt(None, name), pkt()])) == [(code, 1), (code, 0)]


def test_combo_presses_in_order_releases_in_reverse():
    m = Mapper(cfg({"buttons": {"home": "KEY_LEFTCTRL+KEY_C"}}))
    ev = run(m, [pkt(None, "home"), pkt()])
    assert keys(ev) == [(e.KEY_LEFTCTRL, 1), (e.KEY_C, 1), (e.KEY_C, 0), (e.KEY_LEFTCTRL, 0)]


def test_disabled_button():
    m = Mapper(cfg({"buttons": {"vol_up": "none"}}))
    assert run(m, [pkt(None, "vol_up"), pkt()]) == []


def test_pointer_moves_relative_without_jump_on_touch_down():
    m = Mapper(cfg({}))
    assert m.feed(pkt((100, 100))) == []  # finger down: no movement
    ev = m.feed(pkt((104, 98)))
    assert rel(ev, e.REL_X) == 10 and rel(ev, e.REL_Y) == -5  # 2.5 px per unit
    m.feed(pkt())  # lift
    assert m.feed(pkt((250, 20))) == []  # new touch far away: still no jump


def test_pointer_speed_and_subpixel_remainder():
    m = Mapper(cfg({"pointer": {"speed": 0.2}}))  # 0.5 px per unit
    ev = run(m, [pkt((100, 100)), pkt((101, 100)), pkt((102, 100))])
    assert rel(ev, e.REL_X) == 1  # two half-pixels add up


def test_acceleration_makes_fast_moves_longer():
    def moved(acceleration, dx):
        m = Mapper(cfg({"pointer": {"acceleration": acceleration}}))
        return rel(run(m, [pkt((100, 100)), pkt((100 + dx, 100))]), e.REL_X)
    assert moved(1.5, 30) > moved(1.0, 30) == 75
    assert moved(1.5, 2) == moved(1.0, 2) == 5


def test_drag_with_trigger():
    m = Mapper(cfg({}))
    ev = run(m, [pkt((100, 100)), pkt((100, 100), "trigger"), pkt((110, 100), "trigger"),
                 pkt((110, 100))])
    assert keys(ev) == [(e.BTN_LEFT, 1), (e.BTN_LEFT, 0)]
    assert rel(ev, e.REL_X) == 25


def test_modifier_tap_sends_its_action_on_release():
    m = Mapper(cfg({}))  # modifier = back
    assert m.feed(pkt(None, "back")) == []  # nothing on press
    ev = m.feed(pkt())
    assert ev == [(e.EV_KEY, e.KEY_BACK, 1), SYN, (e.EV_KEY, e.KEY_BACK, 0), SYN]


def test_modifier_slide_scrolls_and_suppresses_tap():
    m = Mapper(cfg({}))
    ev = run(m, [pkt((150, 100), "back")] +
             [pkt((150, 100 + 5 * i), "back") for i in range(1, 11)] + [pkt()])
    assert keys(ev) == []  # no KEY_BACK, no pointer buttons
    assert rel(ev, e.REL_X) == 0 and rel(ev, e.REL_Y) == 0
    # 50 units down in steps of 5. The step reaching the 10-unit slide threshold already
    # scrolls, so 45 units scroll: 45 * 120/20 = 270 hi-res = 2 whole notches, downward.
    assert rel(ev, e.REL_WHEEL_HI_RES) == -270
    assert rel(ev, e.REL_WHEEL) == -2


def test_small_wiggle_while_modifier_held_is_still_a_tap():
    m = Mapper(cfg({}))
    ev = run(m, [pkt((150, 100), "back"), pkt((153, 102), "back"), pkt()])
    assert keys(ev) == [(e.KEY_BACK, 1), (e.KEY_BACK, 0)]
    assert rel(ev, e.REL_WHEEL_HI_RES) == 0


def test_natural_and_horizontal_scroll():
    m = Mapper(cfg({"scroll": {"natural": True}}))
    ev = run(m, [pkt((100, 150), "back"), pkt((112, 150), "back"), pkt((140, 150), "back")])
    # 40 units right with natural scrolling -> content follows -> view scrolls left (negative)
    assert rel(ev, e.REL_HWHEEL_HI_RES) == -240
    assert rel(ev, e.REL_HWHEEL) == -2


def test_click_as_modifier_user_setup():
    m = Mapper(cfg({"scroll": {"modifier": "click"}}))
    tap = run(m, [pkt((150, 150)), pkt((150, 150), "click"), pkt((150, 150))])
    assert keys(tap) == [(e.BTN_RIGHT, 1), (e.BTN_RIGHT, 0)]
    slide = run(m, [pkt((150, 150), "click"), pkt((150, 190), "click"), pkt((150, 190))])
    assert keys(slide) == []
    assert rel(slide, e.REL_WHEEL_HI_RES) < 0
    # back is a plain button now
    assert keys(run(m, [pkt(None, "back"), pkt()])) == [(e.KEY_BACK, 1), (e.KEY_BACK, 0)]


def test_release_all_on_disconnect():
    m = Mapper(cfg({}))
    run(m, [pkt((100, 100), "trigger", "vol_up")])
    ev = m.release_all()
    assert sorted(keys(ev)) == sorted([(e.BTN_LEFT, 0), (e.KEY_VOLUMEUP, 0)])
    assert m.release_all() == []
    # after reconnect, a still-pressed trigger is a fresh press
    assert keys(m.feed(pkt(None, "trigger"))) == [(e.BTN_LEFT, 1)]


def test_smoothing_spreads_movement_but_keeps_total():
    m = Mapper(build({}))  # default smoothing 0.5
    first = m.feed(pkt((100, 100))) + m.feed(pkt((120, 100)))
    assert rel(first, e.REL_X) == 25  # half of 20 units * 2.5 px
    rest = run(m, [pkt((120, 100))] * 20)
    assert rel(first + rest, e.REL_X) in (49, 50)  # converges to the full 50 px


def test_glitch_jump_is_ignored():
    m = Mapper(cfg())
    ev = run(m, [pkt((10, 150)), pkt((14, 150)), pkt((200, 150)), pkt((204, 150))])
    assert rel(ev, e.REL_X) == 20  # 4 + 4 units; the 186-unit jump is dropped


def test_capabilities_cover_configured_keys():
    m = Mapper(cfg({"buttons": {"home": "KEY_LEFTCTRL+KEY_C"}}))
    caps = m.capabilities()
    assert {e.KEY_LEFTCTRL, e.KEY_C, e.BTN_LEFT, e.KEY_BACK} <= set(caps[e.EV_KEY])
    assert e.REL_WHEEL_HI_RES in caps[e.EV_REL]
