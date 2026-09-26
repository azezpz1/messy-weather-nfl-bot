"""Classify, score, and sort game-day weather by how "messy" it is."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from messy_weather_nfl_bot.schedule import Game
from messy_weather_nfl_bot.weather import WeatherReport

HIGH_WIND_MPH = 20.0
EXTREME_COLD_F = 32
EXTREME_HEAT_F = 95
COMFORTABLE_LOW_F = 40
COMFORTABLE_HIGH_F = 80


class Condition(Enum):
    SNOW = "snow"
    THUNDERSTORM = "thunderstorm"
    RAIN = "rain"
    FOG = "fog"
    WIND = "wind"
    EXTREME_COLD = "extreme_cold"
    EXTREME_HEAT = "extreme_heat"
    CLEAR = "clear"


EMOJI: dict[Condition, str] = {
    Condition.SNOW: "❄️",
    Condition.THUNDERSTORM: "⛈️",
    Condition.RAIN: "🌧️",
    Condition.FOG: "🌫️",
    Condition.WIND: "💨",
    Condition.EXTREME_COLD: "🥶",
    Condition.EXTREME_HEAT: "🥵",
    Condition.CLEAR: "☀️",
}

_CONDITION_SCORE_BONUS: dict[Condition, float] = {
    Condition.SNOW: 50.0,
    Condition.THUNDERSTORM: 30.0,
    Condition.RAIN: 15.0,
    Condition.FOG: 10.0,
    Condition.WIND: 10.0,
    Condition.EXTREME_COLD: 20.0,
    Condition.EXTREME_HEAT: 15.0,
    Condition.CLEAR: 0.0,
}

_SNOW_KEYWORDS = ("snow", "blizzard", "flurries", "sleet", "wintry mix")
_THUNDERSTORM_KEYWORDS = ("thunderstorm",)
_RAIN_KEYWORDS = ("rain", "showers", "drizzle")
_FOG_KEYWORDS = ("fog", "mist", "haze")


@dataclass(frozen=True)
class GameWeather:
    game: Game
    weather: WeatherReport
    condition: Condition
    score: float


def classify_condition(weather: WeatherReport) -> Condition:
    forecast = weather.short_forecast.lower()

    if any(keyword in forecast for keyword in _SNOW_KEYWORDS):
        return Condition.SNOW
    if any(keyword in forecast for keyword in _THUNDERSTORM_KEYWORDS):
        return Condition.THUNDERSTORM
    if any(keyword in forecast for keyword in _RAIN_KEYWORDS):
        return Condition.RAIN
    if any(keyword in forecast for keyword in _FOG_KEYWORDS):
        return Condition.FOG
    if weather.wind_speed_mph >= HIGH_WIND_MPH:
        return Condition.WIND
    if weather.temperature_f <= EXTREME_COLD_F:
        return Condition.EXTREME_COLD
    if weather.temperature_f >= EXTREME_HEAT_F:
        return Condition.EXTREME_HEAT
    return Condition.CLEAR


def messiness_score(weather: WeatherReport, condition: Condition) -> float:
    """Higher is messier. Combines precipitation odds, wind, temperature extremity,
    and a bonus for the classified condition."""
    precip_component = weather.precipitation_probability or 0
    wind_component = weather.wind_speed_mph * 1.5
    temp_extremity = max(0, COMFORTABLE_LOW_F - weather.temperature_f) + max(
        0, weather.temperature_f - COMFORTABLE_HIGH_F
    )
    return precip_component + wind_component + temp_extremity + _CONDITION_SCORE_BONUS[condition]


def evaluate_game(game: Game, weather_reports: list[WeatherReport]) -> GameWeather:
    """Evaluate every forecast period spanning the game and report the messiest one -
    weather can turn ugly well after kickoff, so the worst point in the game is what
    matters, not just the conditions at the opening whistle."""
    worst: GameWeather | None = None
    for weather in weather_reports:
        condition = classify_condition(weather)
        score = messiness_score(weather, condition)
        if worst is None or score > worst.score:
            worst = GameWeather(game=game, weather=weather, condition=condition, score=score)
    assert worst is not None  # weather_reports is always non-empty (see get_forecast)
    return worst


def sort_by_messiness(games: list[GameWeather]) -> list[GameWeather]:
    """Snow games always sort first, then everything else by messiness score descending."""
    return sorted(
        games, key=lambda gw: (gw.condition is not Condition.SNOW, -gw.score)
    )
