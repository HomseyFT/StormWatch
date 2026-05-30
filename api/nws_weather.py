"""
National Weather Service API client - Focused on severe indicators.
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
class NWSSevereIndicators:
    """Severe weather indicators from NWS alerts and forecasts."""
    risk_level: str  # "Low", "Moderate", "High", "Extreme"
    hail_risk: str
    tornado_risk: str
    wind_risk: str
    flood_risk: str
    active_warnings: list[str]  # List of active warning types
    detailed_summary: str
    updated_at: datetime = field(default_factory=datetime.now)
    from_cache: bool = False


async def fetch_nws_severe_indicators(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> Optional[NWSSevereIndicators]:
    """Fetch severe weather indicators from NWS alerts and forecast text."""
    
    active_warnings = []
    risk_level = "Low"
    hail_risk = "Low"
    tornado_risk = "Low"
    wind_risk = "Low"
    flood_risk = "Low"
    
    try:
        # Get active alerts for this point
        alerts_url = f"{_NWS_BASE}/alerts/active/point/{lat},{lon}"
        resp = await client.get(alerts_url, headers=_HEADERS, timeout=10.0)
        
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            
            for feature in features:
                props = feature.get("properties", {})
                event = props.get("event", "")
                severity = props.get("severity", "")
                
                if event and severity in ["Severe", "Extreme"]:
                    active_warnings.append(event)
                    
                    # Update risk levels based on warning type
                    if "Tornado" in event:
                        tornado_risk = "Extreme"
                        risk_level = "Extreme"
                    elif "Severe Thunderstorm" in event:
                        wind_risk = "High"
                        hail_risk = "High"
                        if risk_level != "Extreme":
                            risk_level = "High"
                    elif "Flash Flood" in event or "Flood" in event:
                        flood_risk = "High"
                        if risk_level == "Low":
                            risk_level = "Moderate"
        
        # Get forecast to check for severe wording
        points_url = f"{_NWS_BASE}/points/{lat},{lon}"
        resp = await client.get(points_url, headers=_HEADERS, timeout=10.0)
        
        if resp.status_code == 200:
            points_data = resp.json()
            forecast_url = points_data.get("properties", {}).get("forecast")
            
            if forecast_url:
                resp = await client.get(forecast_url, headers=_HEADERS, timeout=10.0)
                if resp.status_code == 200:
                    forecast_data = resp.json()
                    periods = forecast_data.get("properties", {}).get("periods", [])
                    
                    if periods:
                        detailed = periods[0].get("detailedForecast", "").lower()
                        
                        # Parse forecast text for severe language
                        if "tornado" in detailed:
                            tornado_risk = max(tornado_risk, "Moderate", key=lambda x: ["Low", "Moderate", "High", "Extreme"].index(x))
                        if "large hail" in detailed or "quarter size" in detailed:
                            hail_risk = max(hail_risk, "Moderate", key=lambda x: ["Low", "Moderate", "High", "Extreme"].index(x))
                        if "damaging wind" in detailed or "60 mph" in detailed:
                            wind_risk = max(wind_risk, "Moderate", key=lambda x: ["Low", "Moderate", "High", "Extreme"].index(x))
                        
                        # Update overall risk
                        risks = [tornado_risk, hail_risk, wind_risk, flood_risk]
                        risk_order = ["Low", "Moderate", "High", "Extreme"]
                        max_risk = max(risks, key=lambda x: risk_order.index(x))
                        risk_level = max_risk
        
        # Create summary
        if active_warnings:
            summary = f"⚠️ Active: {', '.join(active_warnings)}"
        elif risk_level == "High":
            summary = "⚠️ Severe weather possible - monitor conditions"
        elif risk_level == "Moderate":
            summary = "🌩️ Thunderstorms possible - stay aware"
        else:
            summary = "✅ No severe weather expected"
        
        return NWSSevereIndicators(
            risk_level=risk_level,
            hail_risk=hail_risk,
            tornado_risk=tornado_risk,
            wind_risk=wind_risk,
            flood_risk=flood_risk,
            active_warnings=active_warnings,
            detailed_summary=summary,
        )
        
    except Exception as e:
        logger.warning(f"Failed to fetch NWS severe indicators: {e}")
        return None
