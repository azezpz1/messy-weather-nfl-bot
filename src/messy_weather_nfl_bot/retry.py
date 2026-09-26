"""Retry transient httpx failures (timeouts, connection errors, 429s, and 5xx responses)
with exponential backoff and jitter, via tenacity.

`httpx.HTTPTransport(retries=...)` only retries connection failures, not bad status
codes, and api.weather.gov/ESPN both return intermittent 500s/503s - hence this wrapper.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.25

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    return exc.response.status_code in RETRYABLE_STATUS_CODES


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning("Retrying request after %s (attempt %d)", exc, retry_state.attempt_number)


def request_with_retry(
    request: Callable[[], httpx.Response],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> httpx.Response:
    """Call `request()` - which must itself call `raise_for_status()` on its response -
    retrying on timeouts, connection errors, 429s, and 5xx responses. Re-raises the last
    `httpx.HTTPError` once every attempt is exhausted, so callers see one consistent
    failure mode.
    """
    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=base_delay),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_log_retry,
        reraise=True,
    )
    return retryer(request)
