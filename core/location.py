"""
Location resolution chain:
  1. GPS dongle via gpsd
  2. Manual override from config.toml
  3. IP geolocation via ipinfo.io (no key required)

Returns a Coordinates dataclass consumed by all API modules.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lon: float
    source: str  # "gps" | "manual" | "ip"
    label: str = ""

    def __str__(self) -> str:
        src = f"[{self.source}]"
        if self.label:
            return f"{self.label} {src}"
        return f"{self.lat:.4f}, {self.lon:.4f} {src}"


# ---------------------------------------------------------------------------
# GPS via gpsd
# ---------------------------------------------------------------------------

async def _try_gps(timeout: float = 5.0) -> Optional[Coordinates]:
    """Attempt to get a fix from gpsd. Returns None on any failure."""
    try:
        import gpsd  # type: ignore

        loop = asyncio.get_running_loop()

        def _connect_and_read() -> Optional[tuple[float, float]]:
            gpsd.connect()
            packet = gpsd.get_current()
            if packet.mode >= 2:  # 2D or 3D fix
                return packet.lat, packet.lon
            return None

        result = await asyncio.wait_for(
            loop.run_in_executor(None, _connect_and_read),
            timeout=timeout,
        )
        if result:
            lat, lon = result
            logger.info("GPS fix acquired: %.4f, %.4f", lat, lon)
            return Coordinates(lat=lat, lon=lon, source="gps")

    except ImportError:
        logger.debug("gpsd-py3 not installed, skipping GPS")
    except asyncio.TimeoutError:
        logger.warning("GPS fix timed out after %.1fs", timeout)
    except Exception as exc:
        logger.warning("GPS unavailable: %s", exc)

    return None


# ---------------------------------------------------------------------------
# IP geolocation via ipinfo.io
# ---------------------------------------------------------------------------

async def _try_ip_geolocation(client: httpx.AsyncClient) -> Optional[Coordinates]:
    """Fall back to IP-based geolocation. Accurate to ~10–25 miles."""
    try:
        resp = await client.get(
            "https://ipinfo.io/json",
            timeout=8.0,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        loc: str = data.get("loc", "")
        if not loc:
            return None

        lat_str, lon_str = loc.split(",")
        city = data.get("city", "")
        region = data.get("region", "")
        label = f"{city}, {region}".strip(", ") if city or region else ""

        coords = Coordinates(
            lat=float(lat_str),
            lon=float(lon_str),
            source="ip",
            label=label,
        )
        logger.info("IP geolocation: %s", coords)
        return coords

    except Exception as exc:
        logger.warning("IP geolocation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

async def resolve_location(
    manual_lat: float = 0.0,
    manual_lon: float = 0.0,
    manual_label: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> Coordinates:
    """
    Resolve coordinates via the priority chain:
      GPS → manual config → IP geolocation

    Raises RuntimeError if all sources fail.
    """
    # 1. GPS dongle
    gps = await _try_gps()
    if gps:
        return gps

    # 2. Manual override
    if manual_lat != 0.0 or manual_lon != 0.0:
        logger.info("Using manual location: %.4f, %.4f", manual_lat, manual_lon)
        return Coordinates(
            lat=manual_lat,
            lon=manual_lon,
            source="manual",
            label=manual_label,
        )

    # 3. IP geolocation
    _client = client or httpx.AsyncClient()
    try:
        ip_coords = await _try_ip_geolocation(_client)
        if ip_coords:
            return ip_coords
    finally:
        if client is None:
            await _client.aclose()

    raise RuntimeError(
        "All location sources failed. "
        "Set lat/lon manually in config.toml or connect a GPS dongle."
    )
