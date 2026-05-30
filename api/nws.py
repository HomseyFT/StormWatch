"""
National Weather Service API client.
Fetches active alerts for a given point and parses response into
strongly-typed Alert dataclasses including polygon geometry.

Docs: https://www.weather.gov/documentation/services-web-api
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx
from dateutil import parser as dtparser

logger = logging.getLogger(__name__)

_NWS_BASE = "https://api.weather.gov"
_HEADERS = {
    "User-Agent": "StormWatch/1.0 (weather-tui)",
    "Accept": "application/geo+json",
}

# NWS severity → internal severity level (1=lowest, 4=highest)
_SEVERITY_MAP: dict[str, int] = {
    "Minor": 1,
    "Moderate": 2,
    "Severe": 3,
    "Extreme": 4,
    "Unknown": 0,
}

# NWS urgency ordering
_URGENCY_MAP: dict[str, int] = {
    "Past": 0,
    "Future": 1,
    "Expected": 2,
    "Immediate": 3,
    "Unknown": 0,
}


@dataclass
class AlertPolygon:
    """GeoJSON polygon coordinates as list of (lon, lat) tuples."""
    coordinates: list[tuple[float, float]]  # exterior ring only

    @classmethod
    def from_geojson(cls, geometry: Optional[dict]) -> Optional["AlertPolygon"]:
        if not geometry:
            return None
        geo_type = geometry.get("type", "")
        coords = geometry.get("coordinates")
        if not coords:
            return None
        if geo_type == "Polygon":
            ring = [(float(c[0]), float(c[1])) for c in coords[0]]
            return cls(coordinates=ring)
        elif geo_type == "MultiPolygon":
            # Use the largest polygon (most coordinates)
            largest = max(coords, key=lambda p: len(p[0]))
            ring = [(float(c[0]), float(c[1])) for c in largest[0]]
            return cls(coordinates=ring)
        return None


@dataclass
class Alert:
    id: str
    event: str                        # e.g. "Tornado Warning"
    headline: str
    description: str
    instruction: str
    severity: str                     # "Minor" | "Moderate" | "Severe" | "Extreme"
    severity_level: int               # 0–4 mapped from severity
    urgency: str
    urgency_level: int
    certainty: str
    status: str
    area_desc: str                    # Human-readable affected area
    onset: Optional[datetime]
    expires: Optional[datetime]
    sent: Optional[datetime]
    polygon: Optional[AlertPolygon]
    # Populated by distance module after fetch
    distance_to_edge_miles: Optional[float] = None
    distance_to_center_miles: Optional[float] = None

    @classmethod
    def from_feature(cls, feature: dict) -> Optional["Alert"]:
        props = feature.get("properties", {})
        if not props:
            return None

        def _parse_dt(val: Optional[str]) -> Optional[datetime]:
            if not val:
                return None
            try:
                return dtparser.parse(val)
            except Exception:
                return None

        severity = props.get("severity", "Unknown")
        urgency = props.get("urgency", "Unknown")

        polygon = AlertPolygon.from_geojson(feature.get("geometry"))

        return cls(
            id=props.get("id", feature.get("id", "")),
            event=props.get("event", "Unknown Event"),
            headline=props.get("headline", ""),
            description=props.get("description", ""),
            instruction=props.get("instruction", ""),
            severity=severity,
            severity_level=_SEVERITY_MAP.get(severity, 0),
            urgency=urgency,
            urgency_level=_URGENCY_MAP.get(urgency, 0),
            certainty=props.get("certainty", "Unknown"),
            status=props.get("status", "Actual"),
            area_desc=props.get("areaDesc", ""),
            onset=_parse_dt(props.get("onset")),
            expires=_parse_dt(props.get("expires")),
            sent=_parse_dt(props.get("sent")),
            polygon=polygon,
        )


@dataclass
class AlertsResult:
    alerts: list[Alert] = field(default_factory=list)
    updated_at: Optional[datetime] = None
    from_cache: bool = False

    @property
    def has_severe(self) -> bool:
        return any(a.severity_level >= 3 for a in self.alerts)

    @property
    def highest_severity(self) -> int:
        if not self.alerts:
            return 0
        return max(a.severity_level for a in self.alerts)


async def fetch_alerts(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> AlertsResult:
    """
    Fetch active NWS alerts for the given coordinates.
    Returns AlertsResult with parsed Alert list sorted by severity descending.
    Raises httpx.HTTPError on network/API failure — caller handles caching.
    """
    url = f"{_NWS_BASE}/alerts/active"
    params = {"point": f"{lat},{lon}", "status": "actual"}

    resp = await client.get(url, headers=_HEADERS, params=params, timeout=10.0)
    resp.raise_for_status()

    data = resp.json()
    features = data.get("features", [])

    alerts: list[Alert] = []
    for feat in features:
        alert = Alert.from_feature(feat)
        if alert and alert.status == "Actual":
            alerts.append(alert)

    # Sort: highest severity + urgency first
    alerts.sort(key=lambda a: (a.severity_level, a.urgency_level), reverse=True)

    logger.info("Fetched %d active alerts for %.4f, %.4f", len(alerts), lat, lon)
    return AlertsResult(alerts=alerts, updated_at=datetime.now())
