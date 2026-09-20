import datetime as dt

import httpx
import respx

from messy_weather_nfl_bot.schedule import SCOREBOARD_URL, get_todays_games, outdoor_games

TARGET_DATE = dt.date(2026, 1, 18)


def _event(
    home: str,
    away: str,
    kickoff: str,
    venue_name: str,
    venue_indoor: bool = False,
) -> dict:
    return {
        "date": kickoff,
        "competitions": [
            {
                "date": kickoff,
                "venue": {"fullName": venue_name, "indoor": venue_indoor},
                "competitors": [
                    {"homeAway": "home", "team": {"abbreviation": home}},
                    {"homeAway": "away", "team": {"abbreviation": away}},
                ],
            }
        ],
    }


@respx.mock
def test_parses_basic_outdoor_game() -> None:
    payload = {
        "events": [
            _event("GB", "CHI", "2026-01-18T18:00Z", "Lambeau Field"),
        ]
    }
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=payload))

    games = get_todays_games(TARGET_DATE)

    assert len(games) == 1
    game = games[0]
    assert game.home_team == "GB"
    assert game.away_team == "CHI"
    assert game.stadium is not None
    assert game.stadium.is_covered is False


@respx.mock
def test_known_covered_stadium_is_resolved_as_covered() -> None:
    payload = {"events": [_event("NO", "TB", "2026-01-18T18:00Z", "Caesars Superdome")]}
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=payload))

    games = get_todays_games(TARGET_DATE)

    assert games[0].stadium is not None
    assert games[0].stadium.is_covered is True
    assert outdoor_games(games) == []


@respx.mock
def test_neutral_site_game_has_no_resolvable_stadium() -> None:
    payload = {
        "events": [_event("JAX", "NE", "2026-01-18T18:00Z", "Wembley Stadium")],
    }
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=payload))

    games = get_todays_games(TARGET_DATE)

    assert games[0].stadium is None
    assert outdoor_games(games) == []


@respx.mock
def test_espn_indoor_override_treats_normally_open_stadium_as_covered() -> None:
    payload = {
        "events": [
            _event("GB", "CHI", "2026-01-18T18:00Z", "Lambeau Field", venue_indoor=True),
        ]
    }
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=payload))

    games = get_todays_games(TARGET_DATE)

    assert games[0].stadium is not None
    assert games[0].stadium.is_covered is True


@respx.mock
def test_events_outside_target_date_are_excluded() -> None:
    payload = {
        "events": [
            # 9:30pm ET Jan 18 -> still Jan 18 in the game-day timezone.
            _event("GB", "CHI", "2026-01-19T02:30Z", "Lambeau Field"),
            # 1pm ET Jan 19 -> Jan 19, should be excluded.
            _event("KC", "DEN", "2026-01-19T18:00Z", "GEHA Field at Arrowhead Stadium"),
        ]
    }
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=payload))

    games = get_todays_games(TARGET_DATE)

    assert len(games) == 1
    assert games[0].home_team == "GB"


@respx.mock
def test_no_games_returns_empty_list() -> None:
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json={"events": []}))
    assert get_todays_games(TARGET_DATE) == []
