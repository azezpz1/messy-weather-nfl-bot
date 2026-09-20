"""End-to-end run against real ESPN + NWS APIs, using ConsolePoster so nothing is ever
actually posted (Bluesky is never exercised in CI)."""

import pytest

from messy_weather_nfl_bot.main import run


@pytest.mark.integration
def test_full_pipeline_runs_against_real_apis_without_posting_anywhere() -> None:
    # Regardless of whether today happens to have outdoor NFL games, the pipeline should
    # run end-to-end against the real schedule/weather APIs and exit cleanly.
    exit_code = run(platform_names=[], dry_run=True)
    assert exit_code == 0
