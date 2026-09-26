import datetime as dt

import httpx
import pytest
import respx

from messy_weather_nfl_bot import retry
from messy_weather_nfl_bot.main import EXIT_NOTHING_POSTED, EXIT_OK, EXIT_PARTIAL, run
from messy_weather_nfl_bot.schedule import SCOREBOARD_URL

GB_LAT, GB_LON = 44.5013, -88.0622
BUF_LAT, BUF_LON = 42.7738, -78.7870
TARGET_DATE = dt.date(2026, 1, 18)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the test suite fast - backoff timing is covered by tests/unit/test_retry.py.
    monkeypatch.setattr(retry.time, "sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("messy_weather_nfl_bot.main.todays_local_date", lambda: TARGET_DATE)


def _event(home: str, away: str, venue_name: str) -> dict:
    kickoff = "2026-01-18T18:00Z"
    return {
        "date": kickoff,
        "competitions": [
            {
                "date": kickoff,
                "venue": {"fullName": venue_name, "indoor": False},
                "competitors": [
                    {"homeAway": "home", "team": {"abbreviation": home}},
                    {"homeAway": "away", "team": {"abbreviation": away}},
                ],
            }
        ],
    }


def _two_game_schedule() -> dict:
    return {
        "events": [
            _event("GB", "CHI", "Lambeau Field"),
            _event("BUF", "NE", "Highmark Stadium"),
        ]
    }


def _mock_hourly_forecast(lat: float, lon: float, *, response: httpx.Response) -> None:
    hourly_url = f"https://api.weather.gov/gridpoints/MOCK-{lat}-{lon}/forecast/hourly"
    respx.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(
            200, json={"properties": {"forecastHourly": hourly_url}}
        )
    )
    respx.get(hourly_url).mock(return_value=response)


def _clear_period_response() -> httpx.Response:
    period = {
        "startTime": "2026-01-18T13:00:00-05:00",
        "endTime": "2026-01-18T18:30:00-05:00",
        "isDaytime": True,
        "shortForecast": "Sunny",
        "temperature": 40,
        "windSpeed": "5 mph",
        "probabilityOfPrecipitation": {"value": 0},
    }
    return httpx.Response(200, json={"properties": {"periods": [period]}})


@respx.mock
def test_one_failing_stadium_still_posts_the_other_games(capsys: pytest.CaptureFixture) -> None:
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    # BUF's forecast is persistently broken - api.weather.gov's real-world 500s.
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=httpx.Response(500))

    exit_code = run(platform_names=[], dry_run=True)

    out = capsys.readouterr().out
    assert exit_code == EXIT_PARTIAL
    assert "CHI @ GB" in out
    assert "NE @ BUF" not in out


@respx.mock
def test_nws_failure_on_every_game_returns_nothing_posted() -> None:
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=httpx.Response(500))
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=httpx.Response(500))

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_NOTHING_POSTED


@respx.mock
def test_espn_failure_returns_nothing_posted() -> None:
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(500))

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_NOTHING_POSTED


@respx.mock
def test_all_games_succeed_returns_ok() -> None:
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=_clear_period_response())

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_OK


@respx.mock
def test_one_poster_failing_still_lets_the_others_post(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from messy_weather_nfl_bot.poster.base import PostRef, SocialMediaPoster

    class BrokenPoster(SocialMediaPoster):
        def post(self, text: str) -> PostRef:
            raise RuntimeError("platform is down")

        def reply(self, text: str, parent: PostRef) -> PostRef:
            raise RuntimeError("platform is down")

    posted_texts: list[str] = []

    class RecordingPoster(SocialMediaPoster):
        def post(self, text: str) -> PostRef:
            posted_texts.append(text)
            return PostRef(id="1", root_id="1")

        def reply(self, text: str, parent: PostRef) -> PostRef:
            posted_texts.append(text)
            return PostRef(id="2", root_id=parent.root_id)

    monkeypatch.setattr(
        "messy_weather_nfl_bot.main.build_posters",
        lambda platform_names, dry_run: [BrokenPoster(), RecordingPoster()],
    )
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=_clear_period_response())

    exit_code = run(platform_names=["bluesky"], dry_run=False)

    assert exit_code == EXIT_PARTIAL
    assert posted_texts  # the working poster still ran, despite the broken one raising
    assert "platform is down" in capsys.readouterr().err
