import pytest
from evdev import ecodes as e

from vrcontroller.config import ConfigError, build, load


def test_defaults():
    c = build({})
    assert c.scroll_modifier == "back"
    assert c.buttons["trigger"] == (e.BTN_LEFT,)
    assert c.buttons["click"] == (e.BTN_RIGHT,)
    assert c.buttons["home"] == (e.KEY_LEFTMETA,)
    assert c.pointer_speed == 1.0


def test_override_merges_over_defaults():
    c = build({"scroll": {"modifier": "click"}, "pointer": {"speed": 2}})
    assert c.scroll_modifier == "click"
    assert c.scroll_natural is False  # untouched default
    assert c.pointer_speed == 2.0  # int accepted for float
    assert c.buttons["back"] == (e.KEY_BACK,)


def test_combo_and_none():
    c = build({"buttons": {"home": "KEY_LEFTCTRL+KEY_C", "vol_up": "none"}})
    assert c.buttons["home"] == (e.KEY_LEFTCTRL, e.KEY_C)
    assert c.buttons["vol_up"] == ()


@pytest.mark.parametrize("overrides,message", [
    ({"pointr": {}}, "unknown section [pointr]"),
    ({"pointer": {"sped": 1}}, "unknown key pointer.sped"),
    ({"buttons": {"home": "KEY_NOPE"}}, "buttons.home: unknown key name 'KEY_NOPE'"),
    ({"buttons": {"home": "REL_X"}}, "unknown key name 'REL_X'"),
    ({"scroll": {"modifier": "thumb"}}, "scroll.modifier"),
    ({"scroll": {"natural": "yes"}}, "scroll.natural: expected bool"),
    ({"pointer": {"speed": 0}}, "pointer.speed must be positive"),
    ({"pointer": {"acceleration": 0.5}}, "acceleration must be >= 1.0"),
    ({"pointer": {"smoothing": 1.0}}, "smoothing must be"),
])
def test_invalid(overrides, message):
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("]", r"\]")):
        build(overrides)


def test_load_file(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('[scroll]\nmodifier = "click"\nnatural = true\n')
    c = load(f)
    assert c.scroll_modifier == "click" and c.scroll_natural is True


def test_load_missing_default_path_gives_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert load() == build({})


def test_load_missing_explicit_path_fails(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load(tmp_path / "nope.toml")


def test_load_bad_toml(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text("[scroll\n")
    with pytest.raises(ConfigError, match=str(f)):
        load(f)


def test_example_config_is_valid_and_equals_defaults():
    from pathlib import Path
    example = Path(__file__).resolve().parent.parent / "config.example.toml"
    assert load(example) == build({})
