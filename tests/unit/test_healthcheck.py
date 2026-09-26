import logging

import httpx
import pytest
import respx

from messy_weather_nfl_bot import healthcheck

BASE_URL = "https://hc-ping.com/test-uuid"


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the test suite fast - backoff timing is covered by tests/unit/test_retry.py.
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def test_new_run_id_returns_a_unique_string() -> None:
    assert healthcheck.new_run_id() != healthcheck.new_run_id()


@respx.mock
def test_ping_start_gets_the_start_endpoint_with_the_run_id() -> None:
    route = respx.get(f"{BASE_URL}/start").mock(return_value=httpx.Response(200))

    healthcheck.ping_start(BASE_URL, "abc-123")

    assert route.called
    assert route.calls.last.request.url.params["rid"] == "abc-123"


@respx.mock
def test_ping_end_posts_the_exit_code_endpoint_with_the_body() -> None:
    route = respx.post(f"{BASE_URL}/2").mock(return_value=httpx.Response(200))

    healthcheck.ping_end(BASE_URL, "abc-123", 2, "run summary\nlog tail")

    assert route.called
    request = route.calls.last.request
    assert request.url.params["rid"] == "abc-123"
    assert request.content == b"run summary\nlog tail"


@respx.mock
def test_ping_strips_a_trailing_slash_from_the_base_url() -> None:
    route = respx.get(f"{BASE_URL}/start").mock(return_value=httpx.Response(200))

    healthcheck.ping_start(f"{BASE_URL}/", "abc-123")

    assert route.called


@respx.mock
def test_a_failed_ping_is_logged_but_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    respx.get(f"{BASE_URL}/start").mock(return_value=httpx.Response(500))

    healthcheck.ping_start(BASE_URL, "abc-123")  # must not raise

    assert "Healthcheck ping" in caplog.text


@respx.mock
def test_a_connection_error_is_logged_but_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    respx.get(f"{BASE_URL}/start").mock(side_effect=httpx.ConnectError("refused"))

    healthcheck.ping_start(BASE_URL, "abc-123")  # must not raise

    assert "Healthcheck ping" in caplog.text
