import pytest

from vrcontroller.protocol import decode

# Real packets captured from the controller (buttons.log, 2026-10-12).
REST = "b9cc7d015600f902b8074700aefffeff2ad2a201b701f0039d06a2fe46fe3f0093e6a201e601fb03b4062fff2aff7b00000000000000200000164033"
TRIGGER = "251ec50159001706b106c30174000401fe30c501da007c03e4071b01d0fff100be43c50110020402de07ec0092fed200a50c00e82005200000170133"
HOME = "aec804020c022204cb0596ffb10012006edb04028801f103bd04e4ffc200e5ff47ee0402e60052032e047d007d016eff090c14e82805200000170233"
BACK = "29460c02b602ea04c4050cff27fbc3ffe9580c029d029604bb0574ff15fbc0ffc26b0c023f03ab04c704edff30fbe4ffe20b24e82205200000170433"
VOL_UP = "88ad1d023301bf03690638fafd01500161c01d02a40072038506e3fa2d02180121d31d0250005a03940670fb1902dd00870ce2e72605200000171033"
VOL_DOWN = "135f27028801eb02e10699ff1affc700d3712702d801d8021807b4ff26ffa000ac842702e901d8022b07bfff4bff8800260c95e7fb04200000172033"
TOUCH = "71143c028501fd05d405f9013b00730031273c0297011506b505aa01920064000a3a3c02b201020677057001c3006600510c9de85305122539174033"
TOUCH_CLICK = "69734402c4017f06f604d8ff1d012600428644028201a6063a05b7ff7f015d0002994402710164064c05a1ff7a017c00650c26e95b051250b5170833"


def p(hexstr):
    return decode(bytes.fromhex(hexstr))


@pytest.mark.parametrize("packet,button", [
    (TRIGGER, "trigger"), (HOME, "home"), (BACK, "back"),
    (VOL_UP, "vol_up"), (VOL_DOWN, "vol_down"),
])
def test_single_button(packet, button):
    assert p(packet).buttons == {button}
    assert p(packet).touch is None


def test_rest():
    pkt = p(REST)
    assert pkt.buttons == frozenset()
    assert pkt.touch is None
    s = pkt.imu[0]
    assert s.timestamp == 0x017DCCB9
    assert s.accel == (86, 761, 1976)  # lying still: magnitude ~1 g (2048)
    assert s.gyro == (71, -82, -2)


def test_touch_coordinates():
    # bytes 54-56 = 12 25 39 -> x = 2<<6 | 0x25>>2 = 137, y = 1<<8 | 0x39 = 313
    assert p(TOUCH).touch == (137, 313)
    assert p(TOUCH).buttons == frozenset()


def test_touch_with_click():
    pkt = p(TOUCH_CLICK)
    assert pkt.buttons == {"click"}
    assert pkt.touch == (128 + (0x50 >> 2), 0xB5)


def test_three_imu_samples_with_increasing_timestamps():
    ts = [s.timestamp for s in p(TOUCH).imu]
    assert ts[0] < ts[1] < ts[2]
    assert all(4000 < b - a < 6000 for a, b in zip(ts, ts[1:]))  # ~4.8 ms apart


def test_wrong_length_rejected():
    with pytest.raises(ValueError):
        decode(bytes.fromhex("0800"))
