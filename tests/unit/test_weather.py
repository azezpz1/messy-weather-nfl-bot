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
        "properties": {
            "forecastHourly": "https://api.weather.gov/gridpoints/GRB/1,1/forecast/hourly"
        }
    }
    respx.get(f"https://api.weather.gov/points/{LAT},{LON}").mock(
        return_value=httpx.Response(200, json=points_payload)
    )
    respx.get("https://api.weather.gov/gridpoints/GRB/1,1/forecast/hourly").mock(
        return_value=httpx.Response(200, json={"properties": {"periods": periods}})
    )


def _hourly_period(
    hour_start: str,
    short_forecast: str,
    temperature: int,
    wind: str,
    precip: int | None,
    is_daytime: bool = True,
) -> dict:
    start = dt.datetime.fromisoformat(hour_start)
    end = start + dt.timedelta(hours=1)
    return {
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
        "isDaytime": is_daytime,
        "shortForecast": short_forecast,
        "temperature": temperature,
        "windSpeed": wind,
        "probabilityOfPrecipitation": {"value": precip},
    }


@respx.mock
def test_get_forecast_covers_the_whole_game_not_just_kickoff() -> None:
    # Kickoff is clear, but snow rolls in an hour later - well within the game's length.
    # The bot must catch that, not just report conditions at the opening whistle.
    periods = [
        _hourly_period("2026-01-18T17:00:00-05:00", "Sunny", 35, "5 mph", 0),
        _hourly_period("2026-01-18T18:00:00-05:00", "Sunny", 34, "5 mph", 0),
        _hourly_period("2026-01-18T19:00:00-05:00", "Snow", 28, "10 to 15 mph", 80),
        _hourly_period("2026-01-18T20:00:00-05:00", "Snow", 26, "15 mph", 90),
        _hourly_period("2026-01-18T21:00:00-05:00", "Snow", 25, "15 mph", 90),
        _hourly_period("2026-01-18T22:00:00-05:00", "Clear", 24, "5 mph", 0),
    ]
    _mock_forecast(periods)
    kickoff = dt.datetime(2026, 1, 18, 18, 0, tzinfo=EASTERN)  # 6:00pm ET

    reports = get_forecast(LAT, LON, kickoff, game_duration=dt.timedelta(hours=3, minutes=30))

    # Covers 18:00 through 21:30 -> the 18:00, 19:00, 20:00, and 21:00 periods.
    assert [r.short_forecast for r in reports] == ["Sunny", "Snow", "Snow", "Snow"]
    assert any(r.precipitation_probability == 90 for r in reports)


@respx.mock
def test_get_forecast_falls_back_to_first_daytime_period_if_none_cover_the_game_window() -> None:
    periods = [
        _hourly_period(
            "2026-01-18T06:00:00-05:00", "Overnight Clear", 15, "0 mph", None, is_daytime=False
        ),
        _hourly_period("2026-01-18T12:00:00-05:00", "Sunny", 30, "5 mph", 0, is_daytime=True),
    ]
    _mock_forecast(periods)
    # Kickoff is outside the returned forecast window entirely.
    kickoff = dt.datetime(2026, 1, 25, 13, 0, tzinfo=EASTERN)

    reports = get_forecast(LAT, LON, kickoff)

    assert len(reports) == 1
    assert reports[0].short_forecast == "Sunny"


@respx.mock
def test_get_forecast_falls_back_to_first_period_if_none_are_daytime_or_cover_the_window() -> None:
    periods = [
        _hourly_period(
            "2026-01-18T06:00:00-05:00", "Overnight Clear", 15, "0 mph", None, is_daytime=False
        ),
    ]
    _mock_forecast(periods)
    kickoff = dt.datetime(2026, 1, 25, 13, 0, tzinfo=EASTERN)

    reports = get_forecast(LAT, LON, kickoff)

    assert len(reports) == 1
    assert reports[0].short_forecast == "Overnight Clear"
    assert reports[0].precipitation_probability is None
