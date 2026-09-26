import httpx
import pytest

from messy_weather_nfl_bot.retry import request_with_retry

URL = "https://example.test/thing"


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the test suite fast - backoff timing itself isn't under test here.
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("GET", URL))


def _get_and_raise(response: httpx.Response) -> httpx.Response:
    response.raise_for_status()
    return response


def test_returns_immediately_on_success() -> None:
    response = request_with_retry(lambda: _get_and_raise(_response(200)))
    assert response.status_code == 200


def test_does_not_retry_a_non_retryable_status() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _get_and_raise(_response(404))

    with pytest.raises(httpx.HTTPStatusError):
        request_with_retry(request)
    assert attempts == 1


def test_retries_a_5xx_response_then_succeeds() -> None:
    responses = iter([_response(503), _response(200)])

    def request() -> httpx.Response:
        return _get_and_raise(next(responses))

    response = request_with_retry(request)
    assert response.status_code == 200


def test_retries_transient_connection_errors_then_succeeds() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.ConnectTimeout("timed out", request=httpx.Request("GET", URL))
        return _get_and_raise(_response(200))

    response = request_with_retry(request)
    assert response.status_code == 200
    assert attempts == 2


def test_reraises_the_last_5xx_after_exhausting_retries() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _get_and_raise(_response(500))

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        request_with_retry(request, max_attempts=3)
    assert attempts == 3
    assert exc_info.value.response.status_code == 500


def test_does_not_retry_an_unrelated_exception() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise ValueError("not a transient failure")

    with pytest.raises(ValueError, match="not a transient failure"):
        request_with_retry(request)
    assert attempts == 1


def test_reraises_the_last_connection_error_after_exhausting_retries() -> None:
    attempts = 0

    def request() -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", URL))

    with pytest.raises(httpx.ConnectError):
        request_with_retry(request, max_attempts=3)
    assert attempts == 3
