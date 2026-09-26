import datetime as dt
import logging

import httpx
import pytest
import respx

from messy_weather_nfl_bot.main import (
    EXIT_NOTHING_POSTED,
    EXIT_OK,
    EXIT_PARTIAL,
    configure_logging,
    logger,
    main,
    parse_args,
    run,
)
from messy_weather_nfl_bot.schedule import SCOREBOARD_URL

LOGGER_NAME = "messy_weather_nfl_bot"

GB_LAT, GB_LON = 44.5013, -88.0622
BUF_LAT, BUF_LON = 42.7738, -78.7870
TARGET_DATE = dt.date(2026, 1, 18)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the test suite fast - backoff timing is covered by tests/unit/test_retry.py.
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


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


def _covered_and_international_schedule() -> dict:
    return {
        "events": [
            _event("MIN", "DET", "U.S. Bank Stadium"),
            _event("JAX", "PHI", "Tottenham Hotspur Stadium"),
        ]
    }


def _mock_hourly_forecast(lat: float, lon: float, *, response: httpx.Response) -> None:
    hourly_url = f"https://api.weather.gov/gridpoints/MOCK-{lat}-{lon}/forecast/hourly"
    respx.get(f"https://api.weather.gov/points/{lat},{lon}").mock(
        return_value=httpx.Response(200, json={"properties": {"forecastHourly": hourly_url}})
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
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
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
    assert "platform is down" in caplog.text


@respx.mock
def test_a_partially_posted_thread_is_partial_not_nothing_posted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # If the root of a thread published before a later reply failed, the poster did
    # publish something - that must not be reported as EXIT_NOTHING_POSTED.
    from messy_weather_nfl_bot.poster.base import PostRef, SocialMediaPoster

    class FailsAfterRootPost(SocialMediaPoster):
        def post(self, text: str) -> PostRef:
            return PostRef(id="root", root_id="root")

        def reply(self, text: str, parent: PostRef) -> PostRef:
            raise RuntimeError("platform outage")

    monkeypatch.setattr(
        "messy_weather_nfl_bot.main.build_posters",
        lambda platform_names, dry_run: [FailsAfterRootPost()],
    )
    # Force a multi-post thread (root + reply) regardless of formatting specifics -
    # what's under test here is the poster/exit-code interaction, not chunking.
    monkeypatch.setattr(
        "messy_weather_nfl_bot.main.build_post_texts",
        lambda ranked, date: ["root post", "reply post"],
    )
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=_clear_period_response())

    exit_code = run(platform_names=["bluesky"], dry_run=False)

    assert exit_code == EXIT_PARTIAL
    assert "Partially posted" in caplog.text


@respx.mock
def test_skipped_games_log_their_reason(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(
        return_value=httpx.Response(200, json=_covered_and_international_schedule())
    )

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_OK  # no outdoor games today at all
    assert "DET @ MIN — skipped: covered stadium (U.S. Bank Stadium)" in caplog.text
    assert (
        'PHI @ JAX — skipped: international/neutral-site venue "Tottenham Hotspur Stadium"'
        in caplog.text
    )


@respx.mock
def test_forecast_unavailable_is_logged_as_a_skip_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=httpx.Response(500))

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_PARTIAL
    assert "NE @ BUF — skipped: forecast unavailable" in caplog.text


@respx.mock
def test_included_game_logs_score_and_weather_detail(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=_clear_period_response())

    run(platform_names=[], dry_run=True)

    assert "CHI @ GB" in caplog.text
    assert "included: score" in caplog.text
    assert "Sunny, 40°F, 5mph" in caplog.text
    assert "1 hourly period" in caplog.text


@respx.mock
def test_run_summary_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=_clear_period_response())
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=_clear_period_response())

    run(platform_names=[], dry_run=True)

    assert "Run summary: 2 game(s) found, 2 outdoor, 2 evaluated" in caplog.text


@respx.mock
def test_run_summary_is_logged_even_when_no_outdoor_games(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json={"events": []}))

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_OK
    assert "Run summary: 0 game(s) found, 0 outdoor, 0 evaluated" in caplog.text


@respx.mock
def test_run_summary_is_logged_even_when_every_forecast_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=_two_game_schedule()))
    _mock_hourly_forecast(GB_LAT, GB_LON, response=httpx.Response(500))
    _mock_hourly_forecast(BUF_LAT, BUF_LON, response=httpx.Response(500))

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_NOTHING_POSTED
    assert "Run summary: 2 game(s) found, 2 outdoor, 0 evaluated" in caplog.text


@respx.mock
def test_healthcheck_pings_start_and_end_with_matching_rid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/test-uuid")
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json={"events": []}))
    start_route = respx.get("https://hc-ping.com/test-uuid/start").mock(
        return_value=httpx.Response(200)
    )
    end_route = respx.post("https://hc-ping.com/test-uuid/0").mock(return_value=httpx.Response(200))

    exit_code = main(["--dry-run"])

    assert exit_code == EXIT_OK
    assert start_route.called
    assert end_route.called
    start_rid = start_route.calls.last.request.url.params["rid"]
    end_rid = end_route.calls.last.request.url.params["rid"]
    assert start_rid == end_rid
    assert end_route.calls.last.request.content  # the summary/log-tail body


@respx.mock
def test_no_healthcheck_url_means_no_pings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json={"events": []}))

    exit_code = main(["--dry-run"])

    assert exit_code == EXIT_OK
    assert not any(call.request.url.host == "hc-ping.com" for call in respx.calls)


@respx.mock
def test_a_failed_healthcheck_ping_never_changes_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/test-uuid")
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json={"events": []}))
    respx.get("https://hc-ping.com/test-uuid/start").mock(return_value=httpx.Response(500))
    respx.post("https://hc-ping.com/test-uuid/0").mock(return_value=httpx.Response(500))

    exit_code = main(["--dry-run"])

    assert exit_code == EXIT_OK


@respx.mock
def test_an_unhandled_exception_still_sends_a_failure_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/test-uuid")
    respx.get("https://hc-ping.com/test-uuid/start").mock(return_value=httpx.Response(200))
    end_route = respx.post(f"https://hc-ping.com/test-uuid/{EXIT_NOTHING_POSTED}").mock(
        return_value=httpx.Response(200)
    )
    monkeypatch.setattr(
        "messy_weather_nfl_bot.main.run",
        lambda platform_names, dry_run: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        main(["--dry-run"])

    assert end_route.called


def test_verbose_and_quiet_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--verbose", "--quiet"])


@pytest.mark.parametrize(
    ("flags", "expected_logger_level", "expected_console_level"),
    [
        ([], logging.INFO, logging.NOTSET),
        (["--verbose"], logging.DEBUG, logging.NOTSET),
        # --quiet only raises the console handler's threshold - the logger itself stays
        # at INFO, so a healthcheck ping body isn't missing the summary just because
        # the console stayed quiet (see test_quiet_mode_still_captures_the_run_summary).
        (["--quiet"], logging.INFO, logging.WARNING),
    ],
)
def test_configure_logging_sets_the_level_from_cli_flags(
    flags: list[str], expected_logger_level: int, expected_console_level: int
) -> None:
    args = parse_args(flags)
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    assert logger.level == expected_logger_level
    assert logger.handlers[0].level == expected_console_level


@respx.mock
def test_run_summary_is_logged_even_when_the_schedule_fetch_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(500))

    exit_code = run(platform_names=[], dry_run=True)

    assert exit_code == EXIT_NOTHING_POSTED
    assert "Run summary: unavailable game(s) found, 0 outdoor, 0 evaluated" in caplog.text


@respx.mock
def test_quiet_mode_still_captures_the_run_summary_for_the_healthcheck_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --quiet silences the console, but the healthcheck ping body must still carry the
    # run summary - it's captured by a separate handler on the same (INFO-level) logger.
    monkeypatch.setenv("HEALTHCHECK_URL", "https://hc-ping.com/test-uuid")
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json={"events": []}))
    respx.get("https://hc-ping.com/test-uuid/start").mock(return_value=httpx.Response(200))
    end_route = respx.post(f"https://hc-ping.com/test-uuid/{EXIT_OK}").mock(
        return_value=httpx.Response(200)
    )

    exit_code = main(["--dry-run", "--quiet"])

    assert exit_code == EXIT_OK
    assert b"Run summary" in end_route.calls.last.request.content
