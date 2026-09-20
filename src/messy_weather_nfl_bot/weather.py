"""Fetch game-day forecasts from the (free, keyless) US National Weather Service API."""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"

# NWS asks API consumers to identify themselves in the User-Agent.
USER_AGENT = "messy-weather-nfl-bot (https://github.com/azezpz1/messy-weather-nfl-bot)"

_WIND_SPEED_RE = re.compile(r"(\d+)(?:\s*to\s*(\d+))?\s*mph", re.IGNORECASE)


@dataclass(frozen=True)
class WeatherReport:
    short_forecast: str
    temperature_f: int
    wind_speed_mph: float
    precipitation_probability: int | None
    """Percent chance of precipitation (0-100), or None if NWS didn't report one."""


def _parse_wind_speed_mph(wind_speed: str) -> float:
    """Parse an NWS windSpeed string (e.g. "10 mph" or "10 to 20 mph") into mph.

    Uses the upper bound of a range, since the worse case is what matters for messiness.
    """
    match = _WIND_SPEED_RE.search(wind_speed)
    if not match:
        return 0.0
    low, high = match.groups()
    return float(high or low)


def _pick_period(periods: list[dict]) -> dict:
    """Pick the forecast period the bot should report: the soonest daytime period."""
    for period in periods:
        if period.get("isDaytime"):
            return period
    return periods[0]


def get_forecast(
    latitude: float, longitude: float, client: httpx.Client | None = None
) -> WeatherReport:
    """Fetch the forecast for the given coordinates for the nearest upcoming daytime period."""
    owns_client = client is None
    http_client = client or httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT})
    try:
        points_response = http_client.get(POINTS_URL.format(lat=latitude, lon=longitude))
        points_response.raise_for_status()
        forecast_url = points_response.json()["properties"]["forecast"]

        forecast_response = http_client.get(forecast_url)
        forecast_response.raise_for_status()
        periods = forecast_response.json()["properties"]["periods"]
    finally:
        if owns_client:
            http_client.close()

    period = _pick_period(periods)
    precip = period.get("probabilityOfPrecipitation", {}) or {}

    return WeatherReport(
        short_forecast=period.get("shortForecast", ""),
        temperature_f=int(period.get("temperature", 0)),
        wind_speed_mph=_parse_wind_speed_mph(period.get("windSpeed", "")),
        precipitation_probability=precip.get("value"),
    )
