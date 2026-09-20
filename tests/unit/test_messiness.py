import datetime as dt

import pytest

from messy_weather_nfl_bot.messiness import (
    Condition,
    classify_condition,
    evaluate_game,
    messiness_score,
    sort_by_messiness,
)
from messy_weather_nfl_bot.schedule import Game
from messy_weather_nfl_bot.stadiums import stadium_for_team
from messy_weather_nfl_bot.weather import WeatherReport


def make_game(home: str = "BUF", away: str = "MIA") -> Game:
    return Game(
        home_team=home,
        away_team=away,
        kickoff=dt.datetime(2026, 1, 18, 18, 0, tzinfo=dt.UTC),
        stadium=stadium_for_team(home),
    )


def make_weather(
    short_forecast: str = "Sunny",
    temperature_f: int = 65,
    wind_speed_mph: float = 5.0,
    precipitation_probability: int | None = 0,
) -> WeatherReport:
    return WeatherReport(
        short_forecast=short_forecast,
        temperature_f=temperature_f,
        wind_speed_mph=wind_speed_mph,
        precipitation_probability=precipitation_probability,
    )


@pytest.mark.parametrize(
    ("short_forecast", "expected"),
    [
        ("Snow likely", Condition.SNOW),
        ("Chance of Flurries", Condition.SNOW),
        ("Wintry Mix", Condition.SNOW),
        ("Thunderstorms Likely", Condition.THUNDERSTORM),
        ("Chance Rain Showers", Condition.RAIN),
        ("Patchy Fog", Condition.FOG),
        ("Sunny", Condition.CLEAR),
    ],
)
def test_classify_condition_from_text(short_forecast: str, expected: Condition) -> None:
    weather = make_weather(short_forecast=short_forecast)
    assert classify_condition(weather) == expected


def test_classify_condition_high_wind_without_precip_text() -> None:
    weather = make_weather(short_forecast="Sunny", wind_speed_mph=30.0)
    assert classify_condition(weather) == Condition.WIND


def test_classify_condition_extreme_cold() -> None:
    weather = make_weather(short_forecast="Sunny", temperature_f=10)
    assert classify_condition(weather) == Condition.EXTREME_COLD


def test_classify_condition_extreme_heat() -> None:
    weather = make_weather(short_forecast="Sunny", temperature_f=100)
    assert classify_condition(weather) == Condition.EXTREME_HEAT


def test_snow_keyword_takes_priority_over_wind_and_temperature() -> None:
    weather = make_weather(short_forecast="Snow", wind_speed_mph=40.0, temperature_f=5)
    assert classify_condition(weather) == Condition.SNOW


def test_messiness_score_increases_with_precip_wind_and_temp_extremity() -> None:
    calm = make_weather(wind_speed_mph=0, temperature_f=65, precipitation_probability=0)
    messy = make_weather(wind_speed_mph=30, temperature_f=20, precipitation_probability=80)
    assert messiness_score(messy, classify_condition(messy)) > messiness_score(
        calm, classify_condition(calm)
    )


def test_sort_by_messiness_snow_always_first_even_with_lower_score() -> None:
    # A mild snow game should still rank above a severe (but snow-less) storm.
    snow = evaluate_game(
        make_game("GB"),
        make_weather(short_forecast="Light Snow", temperature_f=30, wind_speed_mph=2),
    )
    storm = evaluate_game(
        make_game("KC"),
        make_weather(
            short_forecast="Thunderstorms",
            wind_speed_mph=45,
            temperature_f=95,
            precipitation_probability=100,
        ),
    )
    assert storm.score > snow.score

    ranked = sort_by_messiness([storm, snow])
    assert ranked[0].condition == Condition.SNOW
    assert ranked[1].condition == Condition.THUNDERSTORM


def test_sort_by_messiness_orders_non_snow_games_by_score_descending() -> None:
    mild = evaluate_game(make_game("GB"), make_weather(short_forecast="Sunny"))
    windy = evaluate_game(make_game("KC"), make_weather(short_forecast="Windy", wind_speed_mph=35))

    ranked = sort_by_messiness([mild, windy])
    assert [gw.condition for gw in ranked] == [Condition.WIND, Condition.CLEAR]
