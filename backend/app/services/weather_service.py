from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Any

import httpx

from app.core.config import (
    GOOGLE_MAPS_API_KEY,
    GOOGLE_MAPS_TIMEOUT_SECONDS,
    GOOGLE_WEATHER_BASE_URL,
    REDIS_WEATHER_TTL_SECONDS,
)
from app.services.cache_service import get_cached_json, set_cached_json
from app.services.map_service import geocode_address


logger = logging.getLogger(__name__)

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO_WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _build_client() -> httpx.Client:
    return httpx.Client(timeout=GOOGLE_MAPS_TIMEOUT_SECONDS)


def _normalize_cache_text(value: str | None) -> str:
    """Standardize text used in cache keys."""
    if value is None:
        return ""
    return value.strip().lower()


def _weekday_name(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str).strftime("%A")
    except ValueError:
        return None


def _degrees_to_cardinal(degrees: float | int | None) -> str | None:
    if degrees is None:
        return None
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = round(float(degrees) / 45) % 8
    return directions[idx]


def _fetch_google_weather(city: str, latitude: float, longitude: float, province: str | None) -> dict[str, Any]:
    """Fetch daily forecast from Google Maps Platform Weather API."""
    base_url = GOOGLE_WEATHER_BASE_URL.rstrip("/")
    with _build_client() as client:
        response = client.get(
            f"{base_url}/forecast/days:lookup",
            params={
                "key": GOOGLE_MAPS_API_KEY,
                "location.latitude": latitude,
                "location.longitude": longitude,
                "days": 7,
            },
        )
        response.raise_for_status()
        payload = response.json()

    forecast_days = payload.get("forecastDays", [])
    if not forecast_days:
        raise RuntimeError("Google Weather API returned no forecast days.")

    days: list[dict[str, Any]] = []
    for item in forecast_days:
        display_date = item.get("displayDate") or {}
        if all(k in display_date for k in ("year", "month", "day")):
            date_str = f"{display_date['year']:04d}-{display_date['month']:02d}-{display_date['day']:02d}"
        else:
            date_str = None

        daytime = item.get("daytimeForecast") or {}
        nighttime = item.get("nighttimeForecast") or {}

        day_cond = (daytime.get("weatherCondition") or {}).get("description") or {}
        night_cond = (nighttime.get("weatherCondition") or {}).get("description") or {}

        max_temp = (item.get("maxTemperature") or {}).get("degrees")
        min_temp = (item.get("minTemperature") or {}).get("degrees")

        day_wind_cardinal = ((daytime.get("wind") or {}).get("direction") or {}).get("cardinal")
        night_wind_cardinal = ((nighttime.get("wind") or {}).get("direction") or {}).get("cardinal")

        days.append(
            {
                "date": date_str,
                "week": _weekday_name(date_str),
                "day_weather": day_cond.get("text") if isinstance(day_cond, dict) else day_cond,
                "night_weather": night_cond.get("text") if isinstance(night_cond, dict) else night_cond,
                "day_temp": str(round(max_temp)) if max_temp is not None else None,
                "night_temp": str(round(min_temp)) if min_temp is not None else None,
                "day_wind": day_wind_cardinal,
                "night_wind": night_wind_cardinal,
            }
        )

    return {
        "city": city,
        "province": province,
        "adcode": None,
        "report_time": datetime.now(timezone.utc).isoformat(),
        "days": days,
    }


def _fetch_open_meteo_weather(city: str) -> dict[str, Any]:
    """Fallback free global forecast via Open-Meteo (no API key required)."""
    with _build_client() as client:
        geo_resp = client.get(
            OPEN_METEO_GEOCODING_URL,
            params={"name": city, "count": 1, "language": "en", "format": "json"},
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()

        results = geo_data.get("results") or []
        if not results:
            raise RuntimeError(f"Could not resolve coordinates for city: {city}")

        place = results[0]
        latitude = place["latitude"]
        longitude = place["longitude"]

        weather_resp = client.get(
            OPEN_METEO_FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,wind_direction_10m_dominant",
                "timezone": "auto",
                "forecast_days": 7,
            },
        )
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()

    daily = weather_data.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    t_max = daily.get("temperature_2m_max") or []
    t_min = daily.get("temperature_2m_min") or []
    wind_dirs = daily.get("wind_direction_10m_dominant") or []

    days: list[dict[str, Any]] = []
    for i, date_str in enumerate(dates):
        code = codes[i] if i < len(codes) else None
        description = WMO_WEATHER_CODES.get(code, "Unknown") if code is not None else None
        wind_cardinal = _degrees_to_cardinal(wind_dirs[i]) if i < len(wind_dirs) else None

        days.append(
            {
                "date": date_str,
                "week": _weekday_name(date_str),
                "day_weather": description,
                "night_weather": description,
                "day_temp": str(round(t_max[i])) if i < len(t_max) and t_max[i] is not None else None,
                "night_temp": str(round(t_min[i])) if i < len(t_min) and t_min[i] is not None else None,
                "day_wind": wind_cardinal,
                "night_wind": wind_cardinal,
            }
        )

    return {
        "city": place.get("name") or city,
        "province": place.get("admin1") or place.get("country"),
        "adcode": None,
        "report_time": datetime.now(timezone.utc).isoformat(),
        "days": days,
    }


def get_weather_forecast(city: str) -> dict[str, Any]:
    """Get the weather forecast for a specified city."""
    cache_key = f"weather:forecast:{_normalize_cache_text(city)}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("weather cache hit: city=%s", city)
        return cached_value
    logger.info("weather cache miss: city=%s", city)

    result: dict[str, Any] | None = None

    if GOOGLE_MAPS_API_KEY:
        try:
            geocode = geocode_address(city, city=city)
            if geocode and geocode.get("latitude") is not None and geocode.get("longitude") is not None:
                result = _fetch_google_weather(
                    city=geocode.get("city") or city,
                    latitude=geocode["latitude"],
                    longitude=geocode["longitude"],
                    province=geocode.get("province") or geocode.get("country"),
                )
        except Exception as exc:
            logger.warning("Google Weather lookup failed for '%s', falling back to Open-Meteo: %s", city, exc)

    if result is None:
        result = _fetch_open_meteo_weather(city)

    set_cached_json(cache_key, result, expire_seconds=REDIS_WEATHER_TTL_SECONDS)
    return result