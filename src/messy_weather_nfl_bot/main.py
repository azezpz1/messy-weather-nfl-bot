"""CLI entry point: fetch today's outdoor NFL games, check the weather, and post."""

from __future__ import annotations

import argparse
import sys

import httpx

from messy_weather_nfl_bot.formatting import build_post_texts
from messy_weather_nfl_bot.messiness import evaluate_game, sort_by_messiness
from messy_weather_nfl_bot.poster import POSTERS
from messy_weather_nfl_bot.poster.base import PartialThreadError, SocialMediaPoster
from messy_weather_nfl_bot.poster.console import ConsolePoster
from messy_weather_nfl_bot.schedule import Game, get_todays_games, outdoor_games, todays_local_date
from messy_weather_nfl_bot.weather import WeatherReport, get_forecast

# So cron wrappers and health checks can tell "nothing posted" from "posted, but
# degraded" from a clean run.
EXIT_OK = 0
EXIT_NOTHING_POSTED = 1
EXIT_PARTIAL = 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platforms",
        default="bluesky",
        help="Comma-separated list of platforms to post to (default: bluesky).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be posted instead of posting to any real platform.",
    )
    return parser.parse_args(argv)


def build_posters(platform_names: list[str], dry_run: bool) -> list[SocialMediaPoster]:
    if dry_run:
        return [ConsolePoster()]

    posters = []
    for name in platform_names:
        try:
            poster_cls = POSTERS[name]
        except KeyError:
            known = sorted(POSTERS)
            raise SystemExit(f"Unknown platform: {name!r}. Known platforms: {known}") from None
        posters.append(poster_cls())
    return posters


def _fetch_forecast_or_none(game: Game) -> list[WeatherReport] | None:
    """Fetch `game`'s forecast, or None (after logging why) if it still can't be fetched
    once `get_forecast`'s own retries are exhausted - one bad stadium shouldn't sink the
    whole run."""
    assert game.stadium is not None  # guaranteed by outdoor_games()
    try:
        return get_forecast(game.stadium.latitude, game.stadium.longitude, game.kickoff)
    except (httpx.HTTPError, ValueError) as exc:
        print(
            f"Skipping {game.away_team} @ {game.home_team}: forecast unavailable ({exc})",
            file=sys.stderr,
        )
        return None


def run(platform_names: list[str], dry_run: bool) -> int:
    date = todays_local_date()
    try:
        games = get_todays_games(date)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Could not fetch today's NFL schedule: {exc}", file=sys.stderr)
        return EXIT_NOTHING_POSTED

    candidates = outdoor_games(games)
    if not candidates:
        print(f"No outdoor NFL games on {date.isoformat()}; nothing to post.")
        return EXIT_OK

    evaluated = []
    games_missing = 0
    for game in candidates:
        forecasts = _fetch_forecast_or_none(game)
        if forecasts is None:
            games_missing += 1
            continue
        evaluated.append(evaluate_game(game, forecasts))

    if not evaluated:
        print(
            "Forecast unavailable for every outdoor game today; nothing to post.",
            file=sys.stderr,
        )
        return EXIT_NOTHING_POSTED

    ranked = sort_by_messiness(evaluated)
    post_texts = build_post_texts(ranked, date)
    posters = build_posters(platform_names, dry_run)

    platforms_failed = 0
    platforms_degraded = 0
    for poster in posters:
        try:
            poster.post_thread(post_texts)
        except PartialThreadError as exc:
            # Some posts in the thread went out before it failed - not "nothing
            # posted", but still worth flagging as degraded.
            platforms_degraded += 1
            print(
                f"Partially posted to {type(poster).__name__} "
                f"({len(exc.posted)}/{len(post_texts)} posts before failing): {exc}",
                file=sys.stderr,
            )
        except Exception as exc:  # isolate one platform's outage from the rest
            platforms_failed += 1
            print(f"Failed to post to {type(poster).__name__}: {exc}", file=sys.stderr)

    if platforms_failed == len(posters):
        return EXIT_NOTHING_POSTED
    if games_missing or platforms_failed or platforms_degraded:
        return EXIT_PARTIAL
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    platform_names = [p.strip() for p in args.platforms.split(",") if p.strip()]
    return run(platform_names, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
