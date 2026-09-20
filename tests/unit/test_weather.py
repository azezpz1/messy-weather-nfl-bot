import datetime as dt

import httpx
import pytest
import respx

from messy_weather_nfl_bot.weather import _parse_wind_speed_mph, get_forecast

LAT, LON = 44.5013, -88.0622
EASTERN = dt.timezone(dt.timedelta(hours=-5))  # EST, matches the fixture period offsets below


@pytest.mark.parametrize(
    ("wind_speed", "expected"),
    [
        ("10 mph", 10.0),
        ("5 to 10 mph", 10.0),
        ("0 mph", 0.0),
        ("", 0.0),
    ],
)
def test_parse_wind_speed_mph(wind_speed: str, expected: float) -> None:
    assert _parse_wind_speed_mph(wind_speed) == expected


def _mock_forecast(periods: list[dict]) -> None:
    points_payload = {
        "properties": {"forecast": "https://api.weather.gov/gridpoints/GRB/1,1/forecast"}
    }
    respx.get(f"https://api.weather.gov/points/{LAT},{LON}").mock(
        return_value=httpx.Response(200, json=points_payload)
    )
    respx.get("https://api.weather.gov/gridpoints/GRB/1,1/forecast").mock(
        return_value=httpx.Response(200, json={"properties": {"periods": periods}})
    )


@respx.mock
def test_get_forecast_selects_the_period_covering_kickoff_not_just_the_first_daytime_one() -> None:
    # An afternoon "Sunny" period comes first, but this evening kickoff actually falls
    # within the later "Snow" period - the bot must report that one, not the first daytime hit.
    periods = [
        {
            "startTime": "2026-01-18T06:00:00-05:00",
            "endTime": "2026-01-18T12:00:00-05:00",
            "isDaytime": False,
            "shortForecast": "Clear",
            "temperature": 20,
            "windSpeed": "5 mph",
            "probabilityOfPrecipitation": {"value": 0},
        },
        {
            "startTime": "2026-01-18T12:00:00-05:00",
            "endTime": "2026-01-18T18:00:00-05:00",
            "isDaytime": True,
            "shortForecast": "Sunny",
            "temperature": 35,
            "windSpeed": "5 mph",
            "probabilityOfPrecipitation": {"value": 0},
        },
        {
            "startTime": "2026-01-18T18:00:00-05:00",
            "endTime": "2026-01-19T00:00:00-05:00",
            "isDaytime": False,
            "shortForecast": "Snow",
            "temperature": 25,
            "windSpeed": "10 to 15 mph",
            "probabilityOfPrecipitation": {"value": 80},
        },
    ]
    _mock_forecast(periods)
    kickoff = dt.datetime(2026, 1, 18, 20, 20, tzinfo=EASTERN)  # 8:20pm ET

    report = get_forecast(LAT, LON, kickoff)

    assert report.short_forecast == "Snow"
    assert report.temperature_f == 25
    assert report.wind_speed_mph == 15.0
    assert report.precipitation_probability == 80


@respx.mock
def test_get_forecast_falls_back_to_first_daytime_period_if_none_cover_kickoff() -> None:
    periods = [
        {
            "startTime": "2026-01-18T06:00:00-05:00",
            "endTime": "2026-01-18T12:00:00-05:00",
            "isDaytime": False,
            "shortForecast": "Overnight Clear",
            "temperature": 15,
            "windSpeed": "0 mph",
            "probabilityOfPrecipitation": {"value": None},
        },
        {
            "startTime": "2026-01-18T12:00:00-05:00",
            "endTime": "2026-01-18T18:00:00-05:00",
            "isDaytime": True,
            "shortForecast": "Sunny",
            "temperature": 30,
            "windSpeed": "5 mph",
            "probabilityOfPrecipitation": {"value": 0},
        },
    ]
    _mock_forecast(periods)
    # Kickoff is outside the returned forecast window entirely.
    kickoff = dt.datetime(2026, 1, 25, 13, 0, tzinfo=EASTERN)

    report = get_forecast(LAT, LON, kickoff)

    assert report.short_forecast == "Sunny"


@respx.mock
def test_get_forecast_falls_back_to_first_period_if_none_are_daytime_or_cover_kickoff() -> None:
    periods = [
        {
            "startTime": "2026-01-18T06:00:00-05:00",
            "endTime": "2026-01-18T12:00:00-05:00",
            "isDaytime": False,
            "shortForecast": "Overnight Clear",
            "temperature": 15,
            "windSpeed": "0 mph",
            "probabilityOfPrecipitation": {"value": None},
        },
    ]
    _mock_forecast(periods)
    kickoff = dt.datetime(2026, 1, 25, 13, 0, tzinfo=EASTERN)

    report = get_forecast(LAT, LON, kickoff)

    assert report.short_forecast == "Overnight Clear"
    assert report.precipitation_probability is None
