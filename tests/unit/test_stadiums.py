import pytest

from messy_weather_nfl_bot.stadiums import STADIUMS, stadium_for_team


def test_all_32_teams_present() -> None:
    assert len(STADIUMS) == 32


@pytest.mark.parametrize("team", ["XYZ", "FOO", ""])
def test_unknown_team_raises(team: str) -> None:
    with pytest.raises(KeyError):
        stadium_for_team(team)


@pytest.mark.parametrize(
    "team", ["NO", "DET", "MIN", "LV", "LAC", "LAR", "DAL", "ARI", "HOU", "IND", "ATL"]
)
def test_known_covered_stadiums(team: str) -> None:
    assert stadium_for_team(team).is_covered is True


@pytest.mark.parametrize("team", ["GB", "CHI", "KC", "DEN", "BUF", "NE", "SEA", "PIT"])
def test_known_outdoor_stadiums(team: str) -> None:
    assert stadium_for_team(team).is_covered is False
