"""
National Weather Service forecast API.
Provides more accurate US-specific forecasts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_NWS_BASE = "https://api.weather.gov"
_HEADERS = {
    "User-Agent": "StormWatch/1.0 (weather-tui)",
    "Accept": "application/json",
}


@dataclass
class NWSForecastPeriod:
    name: str  # "This Afternoon", "Tonight", etc.
    start_time: datetime
    end_time: datetime
    temperature: int
    temperature_unit: str  # "F"
    wind_speed: str  # "10 to 15 mph"
    wind_direction: str
    short_forecast: str
    detailed_forecast: str
    precipitation_probability: int  # 0-100
    relative_humidity: int
    icon: str


@dataclass
class NWSForecast:
    periods: list[NWSForecastPeriod]
    updated_at: datetime = field(default_factory=datetime.now)
    from_cache: bool = False


async def get_forecast_gridpoint(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> Optional[str]:
    """Get NWS gridpoint for coordinates."""
    try:
        # Find gridpoint from coordinates
        points_url = f"{_NWS_BASE}/points/{lat},{lon}"
        resp = await client.get(points_url, headers=_HEADERS, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        
        # Extract forecast URL
        forecast_url = data.get("properties", {}).get("forecast")
        if not forecast_url:
            logger.warning("No forecast URL found for coordinates")
            return None
            
        return forecast_url
    except Exception as e:
        logger.warning(f"Failed to get NWS gridpoint: {e}")
        return None


async def fetch_nws_forecast(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> Optional[NWSForecast]:
    """Fetch NWS forecast for given coordinates."""
    
    # First get the forecast gridpoint
    forecast_url = await get_forecast_gridpoint(lat, lon, client)
    if not forecast_url:
        return None
    
    try:
        resp = await client.get(forecast_url, headers=_HEADERS, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        
        periods_data = data.get("properties", {}).get("periods", [])
        
        periods = []
        for p in periods_data[:12]:  # Next 24-36 hours
            period = NWSForecastPeriod(
                name=p.get("name", "Unknown"),
                start_time=datetime.fromisoformat(p.get("startTime", "").replace("Z", "+00:00")),
                end_time=datetime.fromisoformat(p.get("endTime", "").replace("Z", "+00:00")),
                temperature=p.get("temperature", 0),
                temperature_unit=p.get("temperatureUnit", "F"),
                wind_speed=p.get("windSpeed", ""),
                wind_direction=p.get("windDirection", ""),
                short_forecast=p.get("shortForecast", ""),
                detailed_forecast=p.get("detailedForecast", ""),
                precipitation_probability=p.get("probabilityOfPrecipitation", {}).get("value", 0) or 0,
                relative_humidity=p.get("relativeHumidity", {}).get("value", 0) or 0,
                icon=p.get("icon", ""),
            )
            periods.append(period)
        
        logger.info(f"Fetched {len(periods)} NWS forecast periods")
        return NWSForecast(periods=periods)
        
    except Exception as e:
        logger.warning(f"Failed to fetch NWS forecast: {e}")
        return None
