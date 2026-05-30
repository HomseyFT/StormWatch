"""
Async polling scheduler.
Runs two independent loops:
  - Alert loop:      every N seconds (default 20)
  - Conditions loop: every N seconds (default 60)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Set

import httpx

from api import nws, weather
from cache.store import CacheStore, DataKey
from core.location import Coordinates
from processing.distance import annotate_alerts

logger = logging.getLogger(__name__)

AlertCallback = Callable[[], Awaitable[None]]
DataCallback = Callable[[str, object], Awaitable[None]]


@dataclass
class SchedulerConfig:
    alert_poll_seconds: int = 20
    conditions_poll_seconds: int = 60


class Scheduler:
    def __init__(
        self,
        config: SchedulerConfig,
        cache: CacheStore,
        on_new_alert: Optional[AlertCallback] = None,
        on_data_update: Optional[DataCallback] = None,
    ) -> None:
        self._cfg = config
        self._cache = cache
        self._on_new_alert = on_new_alert
        self._on_data_update = on_data_update
        self._coords: Optional[Coordinates] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._tasks: list[asyncio.Task] = []
        self._known_alert_ids: Set[str] = set()
        self._running = False

    def set_coordinates(self, coords: Coordinates) -> None:
        self._coords = coords

    async def start(self) -> None:
        self._running = True
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "StormWatch/1.0"},
            timeout=httpx.Timeout(12.0),
        )
        self._tasks = [
            asyncio.create_task(self._alert_loop(), name="alert-loop"),
            asyncio.create_task(self._conditions_loop(), name="conditions-loop"),
        ]
        logger.info("Scheduler started")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._client:
            await self._client.aclose()
        logger.info("Scheduler stopped")

    async def _alert_loop(self) -> None:
        while self._running:
            await self._fetch_alerts()
            await asyncio.sleep(self._cfg.alert_poll_seconds)

    async def _fetch_alerts(self) -> None:
        if not self._coords or not self._client:
            return
        try:
            result = await nws.fetch_alerts(
                self._coords.lat, self._coords.lon, self._client
            )
            annotate_alerts(self._coords.lat, self._coords.lon, result.alerts)

            new_ids = {a.id for a in result.alerts}
            incoming_new = new_ids - self._known_alert_ids
            if incoming_new and self._known_alert_ids:
                logger.info("New alerts detected: %s", incoming_new)
                if self._on_new_alert:
                    await self._on_new_alert()
            self._known_alert_ids = new_ids

            serialized = []
            for a in result.alerts:
                d = a.__dict__.copy()
                for key in ("onset", "expires", "sent"):
                    if d.get(key):
                        d[key] = d[key].isoformat()
                serialized.append(d)
            await self._cache.set(DataKey.ALERTS, serialized)

            if self._on_data_update:
                await self._on_data_update("alerts", result)

        except Exception as exc:
            logger.warning("Alert fetch failed: %s — serving cache", exc)
            cached = await self._cache.get(DataKey.ALERTS)
            if cached and self._on_data_update:
                alerts = []
                for a in cached:
                    try:
                        alert = nws.Alert(**a)
                        alerts.append(alert)
                    except Exception:
                        pass
                result = nws.AlertsResult(alerts=alerts, from_cache=True)
                await self._on_data_update("alerts", result)

    async def _conditions_loop(self) -> None:
        while self._running:
            await self._fetch_conditions()
            await asyncio.sleep(self._cfg.conditions_poll_seconds)

    async def _fetch_conditions(self) -> None:
        if not self._coords or not self._client:
            return
        try:
            # Get current conditions and forecast from Open-Meteo
            conditions, indicators = await weather.fetch_current_conditions(
                self._coords.lat, self._coords.lon, self._client
            )
            forecast = await weather.fetch_forecast(
                self._coords.lat, self._coords.lon, self._client
            )
            
            # Get severe indicators from NWS
            nws_severe = await weather.fetch_severe_indicators(
                self._coords.lat, self._coords.lon, self._client
            )
            
            # If NWS severe indicators are available, enhance the indicators
            if nws_severe:
                logger.info(f"NWS Severe Risk: {nws_severe.risk_level}")
                risk_map = {"Low": 0, "Moderate": 4, "High": 7, "Extreme": 10}
                indicators.risk_score = risk_map.get(nws_severe.risk_level, 0)
                indicators.risk_label = nws_severe.risk_level
                
                # Store additional severe info in cache
                try:
                    await self._cache.set(DataKey("nws_severe"), {
                        "risk_level": nws_severe.risk_level,
                        "hail_risk": nws_severe.hail_risk,
                        "tornado_risk": nws_severe.tornado_risk,
                        "wind_risk": nws_severe.wind_risk,
                        "flood_risk": nws_severe.flood_risk,
                        "active_warnings": nws_severe.active_warnings,
                        "summary": nws_severe.detailed_summary,
                    })
                except Exception as e:
                    logger.debug(f"Could not store NWS severe data: {e}")

            # Cache all data
            await self._cache.set(DataKey.CONDITIONS, conditions.__dict__)
            await self._cache.set(DataKey.INDICATORS, indicators.__dict__)
            await self._cache.set(DataKey.FORECAST, forecast.__dict__)

            # Send updates to UI
            if self._on_data_update:
                await self._on_data_update("conditions", conditions)
                await self._on_data_update("indicators", indicators)
                await self._on_data_update("forecast", forecast)

        except Exception as exc:
            logger.warning("Conditions fetch failed: %s — serving cache", exc)
            # Try to serve from cache
            for key, name in [
                (DataKey.CONDITIONS, "conditions"),
                (DataKey.INDICATORS, "indicators"),
                (DataKey.FORECAST, "forecast"),
            ]:
                cached = await self._cache.get(key)
                if cached and self._on_data_update:
                    if name == "conditions":
                        from api.open_meteo import CurrentConditions
                        obj = CurrentConditions(**cached)
                    elif name == "indicators":
                        from api.open_meteo import SevereIndicators
                        obj = SevereIndicators(**cached)
                    else:
                        from api.open_meteo import Forecast
                        obj = Forecast(**cached)
                    obj.from_cache = True
                    await self._on_data_update(name, obj)
