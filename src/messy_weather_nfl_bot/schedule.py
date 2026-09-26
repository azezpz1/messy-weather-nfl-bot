"""Fetch today's NFL games from ESPN's public scoreboard endpoint."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import httpx

from messy_weather_nfl_bot.retry import request_with_retry
from messy_weather_nfl_bot.stadiums import StadiumInfo, stadium_for_team

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# NFL scheduling (and this bot's cron) revolves around US Eastern game days.
GAME_DAY_TIMEZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Game:
    home_team: str
    away_team: str
    kickoff: dt.datetime
    stadium: StadiumInfo | None
    """None when the venue isn't a recognized, fixed home stadium (e.g. a neutral-site
    or international game) and weather can't be looked up for it."""


def todays_local_date(now: dt.datetime | None = None) -> dt.date:
    """Today's calendar date in the NFL's Eastern game-day timezone."""
    current = now or dt.datetime.now(tz=GAME_DAY_TIMEZONE)
    return current.astimezone(GAME_DAY_TIMEZONE).date()


def _resolve_stadium(home_team: str, venue_name: str, venue_indoor: bool) -> StadiumInfo | None:
    try:
        stadium = stadium_for_team(home_team)
    except KeyError:
        return None
    if venue_indoor and not stadium.is_covered:
        # ESPN says this particular game is indoors even though the team's usual home
        # stadium is open-air (e.g. relocated to a covered neutral site) - treat as covered.
        return StadiumInfo(venue_name, stadium.latitude, stadium.longitude, is_covered=True)
    if venue_name and venue_name != stadium.name:
        # Neutral-site or international game (e.g. London/Mexico City/Germany) - we don't
        # have coordinates for arbitrary venues, so weather can't be looked up.
        return None
    return stadium


def get_todays_games(
    date: dt.date | None = None, client: httpx.Client | None = None
) -> list[Game]:
    """Fetch NFL games scheduled for `date` (default: today, Eastern time)."""
    target_date = date or todays_local_date()
    owns_client = client is None
    http_client = client or httpx.Client(timeout=10.0)

    def _get() -> httpx.Response:
        response = http_client.get(SCOREBOARD_URL, params={"dates": target_date.strftime("%Y%m%d")})
        response.raise_for_status()
        return response

    try:
        response = request_with_retry(_get)
        payload = response.json()
    finally:
        if owns_client:
            http_client.close()

    if not isinstance(payload, dict):
        kind = type(payload).__name__
        raise ValueError(f"Unexpected ESPN scoreboard response shape: expected object, got {kind}")
    events = payload.get("events", [])
    if not isinstance(events, list):
        kind = type(events).__name__
        raise ValueError(f"Unexpected ESPN scoreboard 'events' shape: expected a list, got {kind}")

    games: list[Game] = []
    for event in events:
        if not isinstance(event, dict):
            kind = type(event).__name__
            raise ValueError(f"Unexpected ESPN scoreboard event shape: expected object, got {kind}")
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]

        kickoff = dt.datetime.fromisoformat(competition["date"].replace("Z", "+00:00"))
        if kickoff.astimezone(GAME_DAY_TIMEZONE).date() != target_date:
            continue

        competitors = competition.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if home is None or away is None:
            continue

        home_team = home["team"]["abbreviation"]
        away_team = away["team"]["abbreviation"]

        venue = competition.get("venue") or {}
        stadium = _resolve_stadium(
            home_team,
            venue.get("fullName", ""),
            bool(venue.get("indoor", False)),
        )

        games.append(
            Game(home_team=home_team, away_team=away_team, kickoff=kickoff, stadium=stadium)
        )

    return games


def outdoor_games(games: list[Game]) -> list[Game]:
    """Games with a known, uncovered stadium - the only ones weather applies to."""
    return [g for g in games if g.stadium is not None and not g.stadium.is_covered]
