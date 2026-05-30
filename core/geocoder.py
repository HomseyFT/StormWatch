"""
Reverse geocoding via Nominatim (OpenStreetMap).
Converts (lat, lon) → human-readable place name for UI display.
Free, no API key required. Rate limit: 1 req/sec — cache aggressively.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "StormWatch/1.0 (weather-tui; contact=stormwatch-app)"


@lru_cache(maxsize=64)
def _cache_key(lat: float, lon: float) -> str:
    """Round coords to 2 decimal places (~1km) for cache deduplication."""
    return f"{lat:.2f},{lon:.2f}"


async def reverse_geocode(
    lat: float,
    lon: float,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """
    Return a short place label like "Poughkeepsie, New York" for given coords.
    Falls back to raw "lat, lon" string on any failure.
    """
    fallback = f"{lat:.4f}, {lon:.4f}"

    _client = client or httpx.AsyncClient()
    try:
        resp = await _client.get(
            _NOMINATIM_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 10,          # city level
                "addressdetails": 1,
            },
            headers={"User-Agent": _USER_AGENT},
            timeout=8.0,
        )
        resp.raise_for_status()
        data = resp.json()

        addr = data.get("address", {})
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("county")
            or ""
        )
        state = addr.get("state", "")

        if city and state:
            return f"{city}, {state}"
        elif city:
            return city
        elif state:
            return state

        return data.get("display_name", fallback).split(",")[0]

    except Exception as exc:
        logger.warning("Reverse geocoding failed: %s", exc)
        return fallback
    finally:
        if client is None:
            await _client.aclose()
