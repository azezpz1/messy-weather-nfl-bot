import datetime as dt

from messy_weather_nfl_bot.formatting import build_post_texts, format_game_line
from messy_weather_nfl_bot.messiness import evaluate_game
from messy_weather_nfl_bot.schedule import Game
from messy_weather_nfl_bot.stadiums import stadium_for_team
from messy_weather_nfl_bot.weather import WeatherReport

GAME_DATE = dt.date(2026, 1, 18)


def make_game_weather(home: str, away: str, short_forecast: str, wind_speed_mph: float = 5.0):
    game = Game(
        home_team=home,
        away_team=away,
        kickoff=dt.datetime(2026, 1, 18, 18, 0, tzinfo=dt.UTC),
        stadium=stadium_for_team(home),
    )
    weather = WeatherReport(
        short_forecast=short_forecast,
        temperature_f=28,
        wind_speed_mph=wind_speed_mph,
        precipitation_probability=60,
    )
    return evaluate_game(game, weather)


def test_format_game_line_includes_teams_emoji_and_temperature() -> None:
    gw = make_game_weather("GB", "CHI", "Snow")
    line = format_game_line(gw)
    assert "CHI @ GB" in line
    assert "28°F" in line
    assert "❄️" in line  # snowflake emoji


def test_format_game_line_omits_wind_when_calm() -> None:
    gw = make_game_weather("GB", "CHI", "Sunny", wind_speed_mph=0)
    assert "mph wind" not in format_game_line(gw)


def test_build_post_texts_empty_games_returns_no_posts() -> None:
    assert build_post_texts([], GAME_DATE) == []


def test_build_post_texts_single_game_fits_in_one_post() -> None:
    games = [make_game_weather("GB", "CHI", "Snow")]
    texts = build_post_texts(games, GAME_DATE)
    assert len(texts) == 1
    assert "GB" in texts[0] and "CHI" in texts[0]
    assert len(texts[0]) <= 280


def test_build_post_texts_splits_into_thread_when_too_long() -> None:
    games = [
        make_game_weather(home, "MIA", "Heavy Thunderstorms with Damaging Wind Gusts Expected")
        for home in ["GB", "CHI", "KC", "DEN", "BUF", "NE", "SEA", "TB", "CAR", "PIT", "CIN", "BAL"]
    ]
    texts = build_post_texts(games, GAME_DATE)
    assert len(texts) > 1
    for text in texts:
        assert len(text) <= 280

    # every game's line shows up somewhere across the thread
    combined = "\n".join(texts)
    for gw in games:
        assert gw.game.home_team in combined


def test_build_post_texts_truncates_an_oversized_single_line_and_keeps_header() -> None:
    absurdly_long_forecast = "Chance Of Rain " * 40  # far longer than the post limit alone
    games = [make_game_weather("GB", "CHI", absurdly_long_forecast)]

    texts = build_post_texts(games, GAME_DATE)

    assert len(texts) == 1
    assert len(texts[0]) <= 280
    # the header (not just the truncated game line) is still present - never a header-only post
    assert "NFL Weather Report" in texts[0]
    assert "GB" in texts[0]
