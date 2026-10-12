"""Mapping configuration: defaults in code, optionally overridden by a TOML file."""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from evdev import ecodes

from .protocol import BUTTON_NAMES

DEFAULTS = {
    "pointer": {"speed": 1.0, "acceleration": 1.0, "smoothing": 0.5},
    "scroll": {"speed": 1.0, "natural": False, "modifier": "back"},
    "buttons": {
        "trigger": "BTN_LEFT",
        "click": "BTN_RIGHT",
        "back": "KEY_BACK",
        "home": "KEY_LEFTMETA",
        "vol_up": "KEY_VOLUMEUP",
        "vol_down": "KEY_VOLUMEDOWN",
    },
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    pointer_speed: float = 1.0
    pointer_acceleration: float = 1.0
    pointer_smoothing: float = 0.5
    scroll_speed: float = 1.0
    scroll_natural: bool = False
    scroll_modifier: str = "back"
    # button name -> evdev codes pressed together (empty = disabled)
    buttons: dict[str, tuple[int, ...]] = field(default_factory=dict)


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "vrcontroller" / "config.toml"


def parse_action(value: str, where: str) -> tuple[int, ...]:
    """'KEY_LEFTCTRL+KEY_C' -> (29, 46); 'none' -> ()."""
    if not isinstance(value, str):
        raise ConfigError(f"{where}: expected a string, got {value!r}")
    if value.strip().lower() == "none":
        return ()
    codes = []
    for name in value.split("+"):
        name = name.strip().upper()
        if not name.startswith(("KEY_", "BTN_")) or name not in ecodes.ecodes:
            raise ConfigError(f"{where}: unknown key name {name!r}")
        codes.append(ecodes.ecodes[name])
    return tuple(codes)


def merge(overrides: dict) -> dict:
    merged = {section: dict(values) for section, values in DEFAULTS.items()}
    for section, values in overrides.items():
        if section not in DEFAULTS:
            raise ConfigError(f"unknown section [{section}]")
        if not isinstance(values, dict):
            raise ConfigError(f"[{section}] must be a table")
        for key, value in values.items():
            if key not in DEFAULTS[section]:
                raise ConfigError(f"unknown key {section}.{key}")
            default = DEFAULTS[section][key]
            if isinstance(default, float) and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            if type(value) is not type(default):
                raise ConfigError(
                    f"{section}.{key}: expected {type(default).__name__}, got {value!r}")
            merged[section][key] = value
    return merged


def build(overrides: dict) -> Config:
    m = merge(overrides)
    modifier = m["scroll"]["modifier"]
    if modifier not in BUTTON_NAMES:
        raise ConfigError(
            f"scroll.modifier: {modifier!r} is not one of {', '.join(BUTTON_NAMES)}")
    for section in ("pointer", "scroll"):
        if m[section]["speed"] <= 0:
            raise ConfigError(f"{section}.speed must be positive")
    if not 0 <= m["pointer"]["smoothing"] < 1:
        raise ConfigError("pointer.smoothing must be >= 0.0 and < 1.0")
    if m["pointer"]["acceleration"] < 1:
        raise ConfigError("pointer.acceleration must be >= 1.0")
    return Config(
        pointer_speed=m["pointer"]["speed"],
        pointer_acceleration=m["pointer"]["acceleration"],
        pointer_smoothing=m["pointer"]["smoothing"],
        scroll_speed=m["scroll"]["speed"],
        scroll_natural=m["scroll"]["natural"],
        scroll_modifier=modifier,
        buttons={name: parse_action(value, f"buttons.{name}")
                 for name, value in m["buttons"].items()},
    )


def load(path: Path | None = None) -> Config:
    """Load the config file; a missing file at the default path means defaults."""
    explicit = path is not None
    path = path or default_path()
    if not path.exists():
        if explicit:
            raise ConfigError(f"config file not found: {path}")
        return build({})
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e
    try:
        return build(data)
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from e
