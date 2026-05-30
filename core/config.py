"""
Config loader — reads config.toml from project root.
Falls back to safe defaults if keys are missing.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

_CONFIG_PATH = Path(__file__).parent.parent / "config.toml"


@dataclass(frozen=True)
class LocationConfig:
    lat: float = 0.0
    lon: float = 0.0
    label: str = ""


@dataclass(frozen=True)
class RefreshConfig:
    alert_poll_seconds: int = 20
    conditions_poll_seconds: int = 60


@dataclass(frozen=True)
class NotificationConfig:
    sound: bool = True
    visual_flash: bool = True


@dataclass(frozen=True)
class CacheConfig:
    alerts_ttl_seconds: int = 60
    conditions_ttl_seconds: int = 120
    indicators_ttl_seconds: int = 120
    forecast_ttl_seconds: int = 300
    staleness_amber_minutes: int = 5
    staleness_red_minutes: int = 15


@dataclass(frozen=True)
class AppConfig:
    units: str = "imperial"
    alert_radius_miles: float = 50.0
    location: LocationConfig = field(default_factory=LocationConfig)
    refresh: RefreshConfig = field(default_factory=RefreshConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)

    @property
    def is_metric(self) -> bool:
        return self.units == "metric"

    @property
    def alert_radius_km(self) -> float:
        return self.alert_radius_miles * 1.60934

    @property
    def has_manual_location(self) -> bool:
        return self.location.lat != 0.0 or self.location.lon != 0.0


def load_config(path: Path = _CONFIG_PATH) -> AppConfig:
    """Load config.toml, returning AppConfig with safe defaults for missing keys."""
    if not path.exists():
        return AppConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    general = raw.get("general", {})
    loc = raw.get("location", {})
    ref = raw.get("refresh", {})
    notif = raw.get("notifications", {})
    cache = raw.get("cache", {})

    return AppConfig(
        units=general.get("units", "imperial"),
        alert_radius_miles=float(general.get("alert_radius_miles", 50.0)),
        location=LocationConfig(
            lat=float(loc.get("lat", 0.0)),
            lon=float(loc.get("lon", 0.0)),
            label=loc.get("label", ""),
        ),
        refresh=RefreshConfig(
            alert_poll_seconds=int(ref.get("alert_poll_seconds", 20)),
            conditions_poll_seconds=int(ref.get("conditions_poll_seconds", 60)),
        ),
        notifications=NotificationConfig(
            sound=bool(notif.get("sound", True)),
            visual_flash=bool(notif.get("visual_flash", True)),
        ),
        cache=CacheConfig(
            alerts_ttl_seconds=int(cache.get("alerts_ttl_seconds", 60)),
            conditions_ttl_seconds=int(cache.get("conditions_ttl_seconds", 120)),
            indicators_ttl_seconds=int(cache.get("indicators_ttl_seconds", 120)),
            forecast_ttl_seconds=int(cache.get("forecast_ttl_seconds", 300)),
            staleness_amber_minutes=int(cache.get("staleness_amber_minutes", 5)),
            staleness_red_minutes=int(cache.get("staleness_red_minutes", 15)),
        ),
    )
