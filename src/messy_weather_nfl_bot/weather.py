"""Fetch game-day forecasts from the (free, keyless) US National Weather Service API."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

import httpx

POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"

# NWS asks API consumers to identify themselves in the User-Agent.
USER_AGENT = "messy-weather-nfl-bot (https://github.com/azezpz1/messy-weather-nfl-bot)"

# Roughly how long an NFL broadcast runs, kickoff to final whistle. Used to build the
# window we check for messy weather, since conditions can turn ugly well after kickoff.
GAME_DURATION = dt.timedelta(hours=3, minutes=30)

_WIND_SPEED_RE = re.compile(r"(\d+)(?:\s*to\s*(\d+))?\s*mph", re.IGNORECASE)


@dataclass(frozen=True)
class WeatherReport:
    short_forecast: str
    temperature_f: int | None
    """None if NWS didn't report a temperature for this period - distinct from a measured
    0°F, which would otherwise be scored as extreme cold."""
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


def _periods_in_window(periods: list[dict], start: dt.datetime, end: dt.datetime) -> list[dict]:
    """Return every forecast period overlapping [start, end), falling back to the soonest
    daytime period (then the first period) if none overlap at all."""
    covering = [
        period
        for period in periods
        if dt.datetime.fromisoformat(period["startTime"]) < end
        and dt.datetime.fromisoformat(period["endTime"]) > start
    ]
    if covering:
        return covering
    for period in periods:
        if period.get("isDaytime"):
            return [period]
    return [periods[0]]


def _period_to_report(period: dict) -> WeatherReport:
    # NWS can report a null temperature/windSpeed for a period with missing data. A null
    # temperature stays None rather than becoming a fabricated 0°F extreme-cold reading;
    # windSpeed falls back to calm, which doesn't skew scoring the same way.
    precip = period.get("probabilityOfPrecipitation", {}) or {}
    temperature = period.get("temperature")
    return WeatherReport(
        short_forecast=period.get("shortForecast", ""),
        temperature_f=int(temperature) if temperature is not None else None,
        wind_speed_mph=_parse_wind_speed_mph(period.get("windSpeed") or ""),
        precipitation_probability=precip.get("value"),
    )


def get_forecast(
    latitude: float,
    longitude: float,
    kickoff: dt.datetime,
    client: httpx.Client | None = None,
    *,
    game_duration: dt.timedelta = GAME_DURATION,
) -> list[WeatherReport]:
    """Fetch hourly forecasts for every period spanning the game, from kickoff through the
    estimated final whistle - so messiness can be judged over the whole game, not just the
    conditions at the moment it starts."""
    owns_client = client is None
    http_client = client or httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT})
    try:
        points_response = http_client.get(POINTS_URL.format(lat=latitude, lon=longitude))
        points_response.raise_for_status()
        forecast_url = points_response.json()["properties"]["forecastHourly"]

        forecast_response = http_client.get(forecast_url)
        forecast_response.raise_for_status()
        periods = forecast_response.json()["properties"]["periods"]
    finally:
        if owns_client:
            http_client.close()

    game_periods = _periods_in_window(periods, kickoff, kickoff + game_duration)
    return [_period_to_report(period) for period in game_periods]
