"""Open-Meteo live weather plugin provider auto-discovered from `plugins/weather/`."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException

from server.plugins.base import HudPluginProvider, PluginRuntimeStatus

CACHE_TTL_SECONDS = 900.0  # 15 minutes
ERROR_BACKOFF_SECONDS = 30.0
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

WMO_CODE_MAP: dict[int, tuple[str, str, bool]] = {
    0: ("CLEAR", "clear", False),
    1: ("PARTLY CLOUDY", "partly-cloudy", False),
    2: ("PARTLY CLOUDY", "partly-cloudy", False),
    3: ("OVERCAST", "overcast", False),
    45: ("FOG", "fog", False),
    48: ("FOG", "fog", False),
    51: ("DRIZZLE", "drizzle", False),
    53: ("DRIZZLE", "drizzle", False),
    55: ("DRIZZLE", "drizzle", False),
    56: ("DRIZZLE", "drizzle", False),
    57: ("DRIZZLE", "drizzle", False),
    61: ("RAIN", "rain", True),
    63: ("RAIN", "rain", True),
    65: ("RAIN", "rain", True),
    66: ("RAIN", "rain", True),
    67: ("RAIN", "rain", True),
    71: ("SNOW", "snow", True),
    73: ("SNOW", "snow", True),
    75: ("SNOW", "snow", True),
    77: ("SNOW", "snow", True),
    80: ("RAIN", "rain", True),
    81: ("RAIN", "rain", True),
    82: ("RAIN", "rain", True),
    85: ("SNOW", "snow", True),
    86: ("SNOW", "snow", True),
    95: ("STORM", "storm", True),
    96: ("STORM", "storm", True),
    99: ("STORM", "storm", True),
}


def map_wmo_code(code: Optional[int]) -> tuple[str, str, bool]:
    """Map a WMO weather code to `(condition_label, icon_id, is_severe)`."""
    if code is None:
        return ("OFFLINE", "unknown", False)
    return WMO_CODE_MAP.get(code, ("OVERCAST", "overcast", False))


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round_optional(value: Any, digits: int = 1) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


class WeatherPluginProvider(HudPluginProvider):
    """Open-Meteo live weather telemetry and severe-weather priority provider."""

    id = "weather"
    name = "Weather"
    description = "Live temperature, forecast conditions, wind, and severe weather alerts."
    base_priority = 8
    default_dynamic_mode = "on_event"
    supports_on_event = True
    default_settings: dict[str, Any] = {
        "dynamicMode": "on_event",
        "userPriority": 8,
        "accentColor": "#00f0ff",
        "cityName": "Bucharest",
        "latitude": 44.4268,
        "longitude": 26.1025,
        "showCondition": True,
        "showHighLow": True,
        "showHumidity": True,
        "showWind": True,
        "showCornerBrackets": True,
        "alertOnSevereWeather": True,
        "triggerOnRain": True,
        "triggerOnStorm": True,
        "triggerOnSnow": True,
        "triggerOnFog": False,
        "triggerOnDrizzle": False,
        "triggerOnHighWind": True,
        "windThresholdKmh": 30,
        "triggerOnExtremeTemp": False,
        "tempLowThresholdC": 0,
        "tempHighThresholdC": 35,
    }

    def __init__(self) -> None:
        self._cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}
        self._error_until: dict[tuple[float, float], tuple[float, str]] = {}
        self._lock = threading.Lock()

    def _fetch_open_meteo(self, latitude: float, longitude: float) -> dict[str, Any]:
        params = urlencode(
            {
                "latitude": f"{latitude:.4f}",
                "longitude": f"{longitude:.4f}",
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
                "forecast_days": 1,
            }
        )
        req = Request(
            f"{OPEN_METEO_FORECAST_URL}?{params}",
            headers={"User-Agent": "STANCE-HRZN-LINK/1.0"},
        )
        with urlopen(req, timeout=5.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        current = payload.get("current") or {}
        daily = payload.get("daily") or {}

        raw_code = current.get("weather_code")
        weather_code = int(raw_code) if raw_code is not None else None
        condition, icon, severe = map_wmo_code(weather_code)

        max_list = daily.get("temperature_2m_max") or []
        min_list = daily.get("temperature_2m_min") or []

        return {
            "temperature_c": _round_optional(current.get("temperature_2m"), 1),
            "humidity_pct": _round_optional(current.get("relative_humidity_2m"), 0),
            "wind_kmh": _round_optional(current.get("wind_speed_10m"), 1),
            "weather_code": weather_code,
            "condition": condition,
            "icon": icon,
            "temp_max_c": _round_optional(max_list[0], 1) if max_list else None,
            "temp_min_c": _round_optional(min_list[0], 1) if min_list else None,
            "severe": severe,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
            "error": None,
        }

    def _get_weather_for_coords(self, latitude: float, longitude: float) -> dict[str, Any]:
        key = (round(latitude, 4), round(longitude, 4))
        now_mono = time.monotonic()

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and (now_mono - cached[0]) < CACHE_TTL_SECONDS:
                return dict(cached[1])

            err_entry = self._error_until.get(key)
            if err_entry is not None and now_mono < err_entry[0]:
                if cached is not None:
                    return {**cached[1], "stale": True, "error": err_entry[1]}
                return {
                    "temperature_c": None,
                    "humidity_pct": None,
                    "wind_kmh": None,
                    "weather_code": None,
                    "condition": "OFFLINE",
                    "icon": "unknown",
                    "temp_max_c": None,
                    "temp_min_c": None,
                    "severe": False,
                    "fetched_at": None,
                    "stale": True,
                    "error": err_entry[1],
                }

        try:
            fresh = self._fetch_open_meteo(key[0], key[1])
            with self._lock:
                self._cache[key] = (time.monotonic(), fresh)
                self._error_until.pop(key, None)
            return dict(fresh)
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            err_msg = str(exc)
            with self._lock:
                self._error_until[key] = (time.monotonic() + ERROR_BACKOFF_SECONDS, err_msg)
                stale_entry = self._cache.get(key)
            if stale_entry is not None:
                return {**stale_entry[1], "stale": True, "error": err_msg}
            return {
                "temperature_c": None,
                "humidity_pct": None,
                "wind_kmh": None,
                "weather_code": None,
                "condition": "OFFLINE",
                "icon": "unknown",
                "temp_max_c": None,
                "temp_min_c": None,
                "severe": False,
                "fetched_at": None,
                "stale": True,
                "error": err_msg,
            }

    def evaluate(
        self,
        settings: dict[str, Any],
        now: Optional[datetime] = None,
    ) -> PluginRuntimeStatus:
        _ = now
        merged = self.merge_settings(settings)
        city_name = str(merged.get("cityName") or "Bucharest").strip() or "Bucharest"
        latitude = _coerce_float(merged.get("latitude"), 44.4268)
        longitude = _coerce_float(merged.get("longitude"), 26.1025)

        weather = self._get_weather_for_coords(latitude, longitude)
        weather["city_name"] = city_name
        weather["latitude"] = latitude
        weather["longitude"] = longitude

        icon = str(weather.get("icon") or "unknown")
        wind_kmh = weather.get("wind_kmh")
        temp_c = weather.get("temperature_c")
        wind_thresh = _coerce_float(merged.get("windThresholdKmh"), 30.0)
        temp_low = _coerce_float(merged.get("tempLowThresholdC"), 0.0)
        temp_high = _coerce_float(merged.get("tempHighThresholdC"), 35.0)

        active_triggers: list[str] = []
        if bool(merged.get("triggerOnStorm", True)) and icon == "storm":
            active_triggers.append("Storm alert")
        if bool(merged.get("triggerOnRain", True)) and icon == "rain":
            active_triggers.append("Rain detected")
        if bool(merged.get("triggerOnSnow", True)) and icon == "snow":
            active_triggers.append("Snow detected")
        if bool(merged.get("triggerOnFog", False)) and icon == "fog":
            active_triggers.append("Fog detected")
        if bool(merged.get("triggerOnDrizzle", False)) and icon == "drizzle":
            active_triggers.append("Drizzle detected")
        if (
            bool(merged.get("triggerOnHighWind", True))
            and isinstance(wind_kmh, (int, float))
            and wind_kmh >= wind_thresh
        ):
            active_triggers.append(f"Wind {wind_kmh:.0f} km/h (>= {wind_thresh:.0f})")
        if (
            bool(merged.get("triggerOnExtremeTemp", False))
            and isinstance(temp_c, (int, float))
            and (temp_c <= temp_low or temp_c >= temp_high)
        ):
            active_triggers.append(f"Extreme temp {temp_c:.0f}°C")

        event_triggered = len(active_triggers) > 0
        weather["event_triggered"] = event_triggered
        condition = weather.get("condition") or "LIVE"
        reason = (
            f"{city_name}: {', '.join(active_triggers)}"
            if event_triggered
            else f"{city_name}: {condition}"
        )

        return PluginRuntimeStatus(
            id=self.id,
            name=self.name,
            event_triggered=event_triggered,
            reason=reason,
            data=weather,
        )

    def get_router(self) -> APIRouter:
        """Expose `/api/plugins/weather/search` for Open-Meteo city geocoding."""
        router = APIRouter()

        @router.get("/search")
        async def search_cities(q: str = "") -> dict[str, Any]:
            query = q.strip()
            if len(query) < 2:
                return {"results": []}

            def _fetch_geocoding() -> list[dict[str, Any]]:
                params = urlencode(
                    {
                        "name": query,
                        "count": 6,
                        "language": "en",
                        "format": "json",
                    }
                )
                req = Request(
                    f"{OPEN_METEO_GEOCODING_URL}?{params}",
                    headers={"User-Agent": "STANCE-HRZN-LINK/1.0"},
                )
                with urlopen(req, timeout=5.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                raw_results = payload.get("results") or []
                return [
                    {
                        "name": item.get("name", ""),
                        "country": item.get("country", ""),
                        "admin1": item.get("admin1", ""),
                        "latitude": item.get("latitude"),
                        "longitude": item.get("longitude"),
                    }
                    for item in raw_results
                    if item.get("latitude") is not None and item.get("longitude") is not None
                ]

            try:
                results = await asyncio.to_thread(_fetch_geocoding)
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Geocoding lookup failed: {exc}",
                ) from exc

            return {"results": results}

        return router
