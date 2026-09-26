"""Retry transient httpx failures (timeouts, connection errors, 429s, and 5xx responses)
with exponential backoff and jitter.

`httpx.HTTPTransport(retries=...)` only retries connection failures, not bad status
codes, and api.weather.gov/ESPN both return intermittent 500s/503s - hence this wrapper.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.25

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _backoff_delay(attempt: int, base_delay: float) -> float:
    """Exponential backoff (base * 2**attempt) plus up to base_delay of jitter, so
    simultaneous stadium lookups don't all hammer the API in lockstep."""
    return base_delay * (2**attempt) + random.uniform(0, base_delay)


def request_with_retry(
    request: Callable[[], httpx.Response],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> httpx.Response:
    """Call `request()`, retrying on timeouts, connection errors, 429s, and 5xx responses.

    A response with a non-retryable status (including other 4xxs) is returned
    immediately, for the caller to handle via `raise_for_status()`. If every attempt is
    exhausted, the last response is returned the same way - or the last exception is
    re-raised if the final attempt failed to connect at all - so callers see one
    consistent failure mode (an `httpx.HTTPError`) either way.
    """
    for attempt in range(max_attempts):
        is_last_attempt = attempt == max_attempts - 1
        try:
            response = request()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if is_last_attempt:
                raise
            logger.warning(
                "Retrying request after %s (attempt %d/%d)", exc, attempt + 1, max_attempts
            )
            time.sleep(_backoff_delay(attempt, base_delay))
            continue

        if is_last_attempt or response.status_code not in RETRYABLE_STATUS_CODES:
            return response

        logger.warning(
            "Retrying request after HTTP %d from %s (attempt %d/%d)",
            response.status_code,
            response.request.url,
            attempt + 1,
            max_attempts,
        )
        time.sleep(_backoff_delay(attempt, base_delay))

    raise AssertionError("unreachable")  # pragma: no cover
