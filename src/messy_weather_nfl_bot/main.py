"""CLI entry point: fetch today's outdoor NFL games, check the weather, and post."""

from __future__ import annotations

import argparse
import sys

from messy_weather_nfl_bot.formatting import build_post_texts
from messy_weather_nfl_bot.messiness import evaluate_game, sort_by_messiness
from messy_weather_nfl_bot.poster import POSTERS
from messy_weather_nfl_bot.poster.base import SocialMediaPoster
from messy_weather_nfl_bot.poster.console import ConsolePoster
from messy_weather_nfl_bot.schedule import get_todays_games, outdoor_games, todays_local_date
from messy_weather_nfl_bot.weather import get_forecast


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


def run(platform_names: list[str], dry_run: bool) -> int:
    date = todays_local_date()
    games = get_todays_games(date)
    candidates = outdoor_games(games)

    if not candidates:
        print(f"No outdoor NFL games on {date.isoformat()}; nothing to post.")
        return 0

    evaluated = []
    for game in candidates:
        assert game.stadium is not None  # guaranteed by outdoor_games()
        forecast = get_forecast(game.stadium.latitude, game.stadium.longitude)
        evaluated.append(evaluate_game(game, forecast))
    ranked = sort_by_messiness(evaluated)

    post_texts = build_post_texts(ranked, date)
    posters = build_posters(platform_names, dry_run)
    for poster in posters:
        poster.post_thread(post_texts)

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    platform_names = [p.strip() for p in args.platforms.split(",") if p.strip()]
    return run(platform_names, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
