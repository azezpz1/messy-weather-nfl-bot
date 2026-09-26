import httpx
import pytest

from messy_weather_nfl_bot import retry
from messy_weather_nfl_bot.retry import request_with_retry

URL = "https://example.test/thing"


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the test suite fast - backoff timing itself isn't under test here.
    monkeypatch.setattr(retry.time, "sleep", lambda seconds: None)


def _responses(*statuses: int) -> list[httpx.Response]:
    return [httpx.Response(status, request=httpx.Request("GET", URL)) for status in statuses]


def test_returns_immediately_on_success() -> None:
    calls = iter(_responses(200))
    response = request_with_retry(lambda: next(calls))
    assert response.status_code == 200


def test_returns_immediately_on_non_retryable_status() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404, request=httpx.Request("GET", URL))

    response = request_with_retry(request)
    assert response.status_code == 404
    assert attempts == 1


def test_retries_a_5xx_response_then_succeeds() -> None:
    calls = iter(_responses(503, 200))
    response = request_with_retry(lambda: next(calls))
    assert response.status_code == 200


def test_retries_transient_connection_errors_then_succeeds() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.ConnectTimeout("timed out", request=httpx.Request("GET", URL))
        return httpx.Response(200, request=httpx.Request("GET", URL))

    response = request_with_retry(request)
    assert response.status_code == 200
    assert attempts == 2


def test_gives_up_and_returns_last_response_after_exhausting_retries() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, request=httpx.Request("GET", URL))

    response = request_with_retry(request, max_attempts=3)
    assert response.status_code == 500
    assert attempts == 3


def test_reraises_the_last_connection_error_after_exhausting_retries() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", URL))

    with pytest.raises(httpx.ConnectError):
        request_with_retry(request, max_attempts=3)
    assert attempts == 3
