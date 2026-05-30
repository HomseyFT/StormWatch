"""
Open-Meteo API client - FIXED unit handling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code descriptions
_WMO_CODES: dict[int, str] = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog", 51: "Light drizzle", 53: "Moderate drizzle", 
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Moderate showers", 82: "Heavy showers",
    85: "Light snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


@dataclass
class CurrentConditions:
    temperature_f: float
    feels_like_f: float
    humidity_pct: float
    wind_speed_mph: float
    wind_direction_deg: float
    wind_gusts_mph: float
    pressure_inhg: float
    visibility_miles: float
    dew_point_f: float
    precipitation_in: float
    weather_code: int
    weather_desc: str
    updated_at: datetime = field(default_factory=datetime.now)
    from_cache: bool = False

    @property
    def wind_direction_label(self) -> str:
        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                "S","SSW","SW","WSW","W","WNW","NW","NNW"]
        idx = round(self.wind_direction_deg / 22.5) % 16
        return dirs[idx]


@dataclass
class SevereIndicators:
    cape_jkg: float
    lifted_index: float
    cin_jkg: float
    precipitable_water_in: float
    wind_shear_mph: float
    risk_score: int
    risk_label: str
    updated_at: datetime = field(default_factory=datetime.now)
    from_cache: bool = False


@dataclass
class HourlySlice:
    time: datetime
    temperature_f: float
    wind_speed_mph: float
    wind_gusts_mph: float
    precipitation_prob_pct: float
    precipitation_in: float
    weather_code: int
    weather_desc: str
    cape_jkg: float


@dataclass
class Forecast:
    hourly: list[HourlySlice] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.now)
    from_cache: bool = False


def _c_to_f(c: float) -> float:
    return c * 9 / 5 + 32

def _kmh_to_mph(kmh: float) -> float:
    return kmh * 0.621371

def _mm_to_in(mm: float) -> float:
    return mm * 0.0393701

def _hpa_to_inhg(hpa: float) -> float:
    return hpa * 0.02953

def _km_to_miles(km: float) -> float:
    return km * 0.621371


async def fetch_conditions_and_indicators(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> tuple[CurrentConditions, SevereIndicators]:
    """Fetch current weather conditions with correct unit handling."""
    
    # Request ALL data in Celsius/km/h (the API default)
    # Then convert to imperial ourselves
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "hourly": [
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", 
            "pressure_msl", "visibility", "dew_point_2m", 
            "precipitation", "weather_code"
        ],
        "timezone": "auto",
        "forecast_days": 1,
    }

    logger.info(f"Fetching Open-Meteo data for {lat}, {lon}")
    
    resp = await client.get(_BASE_URL, params=params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()

    current_weather = data.get("current_weather", {})
    hourly = data.get("hourly", {})
    
    # CRITICAL: current_weather.temperature is ALWAYS in Celsius
    temp_c = float(current_weather.get("temperature", 0.0))
    windspeed_kmh = float(current_weather.get("windspeed", 0.0))
    wind_dir = float(current_weather.get("winddirection", 0.0))
    weather_code = int(current_weather.get("weathercode", 0))
    
    # Find index matching current time
    current_time_str = current_weather.get("time")
    hourly_times = hourly.get("time", [])
    
    current_index = 0
    if current_time_str and hourly_times:
        try:
            current_index = hourly_times.index(current_time_str)
            logger.info(f"Current time {current_time_str} matches hourly index {current_index}")
        except ValueError:
            current_dt = datetime.fromisoformat(current_time_str)
            for i, t_str in enumerate(hourly_times):
                t_dt = datetime.fromisoformat(t_str)
                if t_dt >= current_dt:
                    current_index = i
                    break

    def _get_hourly(key: str, default: float = 0.0) -> float:
        vals = hourly.get(key, [])
        if current_index < len(vals) and vals[current_index] is not None:
            return float(vals[current_index])
        return default

    # Hourly data (already in Celsius, km/h)
    feels_like_c = _get_hourly("apparent_temperature")
    humidity = _get_hourly("relative_humidity_2m")
    wind_gust_kmh = _get_hourly("wind_gusts_10m")
    pressure_hpa = _get_hourly("pressure_msl", 1013.0)
    visibility_m = _get_hourly("visibility", 10000.0)
    dew_point_c = _get_hourly("dew_point_2m")
    precip_mm = _get_hourly("precipitation")
    
    # Convert to imperial units
    conditions = CurrentConditions(
        temperature_f=_c_to_f(temp_c),
        feels_like_f=_c_to_f(feels_like_c),
        humidity_pct=humidity,
        wind_speed_mph=_kmh_to_mph(windspeed_kmh),
        wind_direction_deg=wind_dir,
        wind_gusts_mph=_kmh_to_mph(wind_gust_kmh),
        pressure_inhg=_hpa_to_inhg(pressure_hpa),
        visibility_miles=_km_to_miles(visibility_m / 1000.0),
        dew_point_f=_c_to_f(dew_point_c),
        precipitation_in=_mm_to_in(precip_mm),
        weather_code=weather_code,
        weather_desc=_WMO_CODES.get(weather_code, "Unknown"),
    )
    
    # Log actual values for debugging

    indicators = SevereIndicators(
        cape_jkg=0,
        lifted_index=0,
        cin_jkg=0,
        precipitable_water_in=0,
        wind_shear_mph=0,
        risk_score=0,
        risk_label="N/A",
    )

    return conditions, indicators


async def fetch_forecast(
    lat: float,
    lon: float,
    client: httpx.AsyncClient,
) -> Forecast:
    """Fetch 24-hour hourly forecast."""
    
    # Request in Celsius/km/h, convert to imperial ourselves
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": [
            "temperature_2m", "wind_speed_10m", "wind_gusts_10m",
            "precipitation_probability", "precipitation", "weather_code"
        ],
        "timezone": "auto",
        "forecast_days": 1,
    }

    resp = await client.get(_BASE_URL, params=params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    
    # Find current hour to start forecast from
    now = datetime.now()
    start_index = 0
    for i, t_str in enumerate(times):
        t_dt = datetime.fromisoformat(t_str)
        if t_dt >= now:
            start_index = i
            break
    
    end_index = min(start_index + 24, len(times))
    
    slices: list[HourlySlice] = []
    for i in range(start_index, end_index):
        t_str = times[i]
        
        def _get(key: str, default: float = 0.0) -> float:
            vals = hourly.get(key, [])
            v = vals[i] if i < len(vals) else None
            return float(v) if v is not None else default

        # Convert from Celsius to Fahrenheit
        temp_c = _get("temperature_2m")
        wind_kmh = _get("wind_speed_10m")
        gust_kmh = _get("wind_gusts_10m")
        
        wcode = int(_get("weather_code"))
        try:
            dt = datetime.fromisoformat(t_str)
        except ValueError:
            continue

        slices.append(HourlySlice(
            time=dt,
            temperature_f=_c_to_f(temp_c),
            wind_speed_mph=_kmh_to_mph(wind_kmh),
            wind_gusts_mph=_kmh_to_mph(gust_kmh),
            precipitation_prob_pct=_get("precipitation_probability"),
            precipitation_in=_mm_to_in(_get("precipitation")),
            weather_code=wcode,
            weather_desc=_WMO_CODES.get(wcode, "Unknown"),
            cape_jkg=0,
        ))

    logger.info(f"Fetched {len(slices)} forecast slices")
    return Forecast(hourly=slices)
