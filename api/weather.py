"""
Weather API aggregator - hybrid approach:
- Current conditions + forecast: Open-Meteo (better interpolation)
- Severe indicators: NWS (more accurate alerts and risks)
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from api.nws_weather import fetch_nws_severe_indicators, NWSSevereIndicators
from api.open_meteo import (
    fetch_conditions_and_indicators as fetch_om_conditions,
    fetch_forecast as fetch_om_forecast,
    CurrentConditions,
    SevereIndicators as OMSevereIndicators,
    Forecast
)

logger = logging.getLogger(__name__)


async def fetch_current_conditions(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> tuple[CurrentConditions, OMSevereIndicators]:
    """
    Fetch current conditions from Open-Meteo (more accurate for local conditions).
    """
    logger.info(f"Fetching current conditions from Open-Meteo for {lat}, {lon}")
    conditions, indicators = await fetch_om_conditions(lat, lon, client)
    return conditions, indicators


async def fetch_severe_indicators(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> Optional[NWSSevereIndicators]:
    """
    Fetch severe weather indicators from NWS (more accurate for warnings).
    """
    logger.info(f"Fetching severe indicators from NWS for {lat}, {lon}")
    return await fetch_nws_severe_indicators(lat, lon, client)


async def fetch_forecast(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> Forecast:
    """
    Fetch forecast from Open-Meteo (hourly, more detailed).
    """
    logger.info(f"Fetching forecast from Open-Meteo for {lat}, {lon}")
    return await fetch_om_forecast(lat, lon, client)
