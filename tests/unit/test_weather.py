import httpx
import pytest
import respx

from messy_weather_nfl_bot.weather import _parse_wind_speed_mph, get_forecast

LAT, LON = 44.5013, -88.0622


@pytest.mark.parametrize(
    ("wind_speed", "expected"),
    [
        ("10 mph", 10.0),
        ("5 to 10 mph", 10.0),
        ("0 mph", 0.0),
        ("", 0.0),
    ],
)
def test_parse_wind_speed_mph(wind_speed: str, expected: float) -> None:
    assert _parse_wind_speed_mph(wind_speed) == expected


@respx.mock
def test_get_forecast_parses_daytime_period() -> None:
    points_payload = {
        "properties": {"forecast": "https://api.weather.gov/gridpoints/GRB/1,1/forecast"}
    }
    forecast_payload = {
        "properties": {
            "periods": [
                {
                    "isDaytime": False,
                    "shortForecast": "Clear",
                    "temperature": 20,
                    "windSpeed": "5 mph",
                    "probabilityOfPrecipitation": {"value": 0},
                },
                {
                    "isDaytime": True,
                    "shortForecast": "Snow",
                    "temperature": 25,
                    "windSpeed": "10 to 15 mph",
                    "probabilityOfPrecipitation": {"value": 80},
                },
            ]
        }
    }
    respx.get(f"https://api.weather.gov/points/{LAT},{LON}").mock(
        return_value=httpx.Response(200, json=points_payload)
    )
    respx.get("https://api.weather.gov/gridpoints/GRB/1,1/forecast").mock(
        return_value=httpx.Response(200, json=forecast_payload)
    )

    report = get_forecast(LAT, LON)

    assert report.short_forecast == "Snow"
    assert report.temperature_f == 25
    assert report.wind_speed_mph == 15.0
    assert report.precipitation_probability == 80


@respx.mock
def test_get_forecast_falls_back_to_first_period_if_none_are_daytime() -> None:
    points_payload = {
        "properties": {"forecast": "https://api.weather.gov/gridpoints/GRB/1,1/forecast"}
    }
    forecast_payload = {
        "properties": {
            "periods": [
                {
                    "isDaytime": False,
                    "shortForecast": "Overnight Clear",
                    "temperature": 15,
                    "windSpeed": "0 mph",
                    "probabilityOfPrecipitation": {"value": None},
                },
            ]
        }
    }
    respx.get(f"https://api.weather.gov/points/{LAT},{LON}").mock(
        return_value=httpx.Response(200, json=points_payload)
    )
    respx.get("https://api.weather.gov/gridpoints/GRB/1,1/forecast").mock(
        return_value=httpx.Response(200, json=forecast_payload)
    )

    report = get_forecast(LAT, LON)

    assert report.short_forecast == "Overnight Clear"
    assert report.precipitation_probability is None
