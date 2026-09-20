"""Render messiness-sorted games into post text, threaded across Bluesky's char limit."""

from __future__ import annotations

import datetime as dt

from messy_weather_nfl_bot.messiness import EMOJI, GameWeather

# Bluesky's real limit is 300 graphemes; stay conservative since multi-codepoint emoji
# can count as more than one grapheme and Python's len() undercounts that.
MAX_POST_LENGTH = 280


def format_game_line(gw: GameWeather) -> str:
    emoji = EMOJI[gw.condition]
    weather = gw.weather
    parts = [f"{weather.short_forecast}", f"{weather.temperature_f}°F"]
    if weather.wind_speed_mph > 0:
        parts.append(f"{weather.wind_speed_mph:g}mph wind")
    return f"\U0001f3c8 {gw.game.away_team} @ {gw.game.home_team}: {emoji} {', '.join(parts)}"


def format_header(date: dt.date) -> str:
    return f"\U0001f329️ NFL Weather Report — {date:%a %b} {date.day}"


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def build_post_texts(
    games: list[GameWeather], date: dt.date, max_length: int = MAX_POST_LENGTH
) -> list[str]:
    """Build one or more post texts (a thread) covering every game, each within max_length."""
    if not games:
        return []

    header = format_header(date)
    # Reserve room for the header so it always fits alongside at least one game line -
    # otherwise a single oversized line could force a header-only first post.
    line_budget = max_length - len(header) - 1
    lines = [_truncate(format_game_line(gw), line_budget) for gw in games]

    chunks: list[str] = []
    current: list[str] = [header]
    current_length = len(header)

    for line in lines:
        addition = len(line) + 1  # + newline joining it to the chunk
        if current_length + addition > max_length:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += addition

    chunks.append("\n".join(current))

    return chunks
