"""Report run start/end to a Healthchecks.io-compatible dead-man's-switch endpoint,
configured via the HEALTHCHECK_URL environment variable (see the README). A missed
check-in - the whole point of the service - catches failures the bot can't report
itself, like the Pi being off or a broken cron environment.

A failed ping is logged but never raises, so a flaky healthcheck endpoint can never
change the run's outcome.
"""

from __future__ import annotations

import logging
import uuid

import httpx

from messy_weather_nfl_bot.retry import request_with_retry

logger = logging.getLogger(__name__)

ENV_VAR = "HEALTHCHECK_URL"

PING_TIMEOUT = 10.0
PING_MAX_ATTEMPTS = 2


def new_run_id() -> str:
    """A fresh id pairing a run's start and end pings (the `rid` query param)."""
    return str(uuid.uuid4())


def _ping(url: str, run_id: str, *, method: str = "GET", body: str | None = None) -> None:
    try:
        with httpx.Client(timeout=PING_TIMEOUT) as client:

            def _send() -> httpx.Response:
                response = client.request(
                    method, url, params={"rid": run_id}, content=body
                )
                response.raise_for_status()
                return response

            request_with_retry(_send, max_attempts=PING_MAX_ATTEMPTS)
    except httpx.HTTPError as exc:
        logger.warning("Healthcheck ping to %s failed: %s", url, exc)


def ping_start(base_url: str, run_id: str) -> None:
    """Ping that a run has started. Call this before doing any other work."""
    _ping(f"{base_url.rstrip('/')}/start", run_id)


def ping_end(base_url: str, run_id: str, exit_code: int, body: str) -> None:
    """Ping that a run has finished with `exit_code` (0 is success, anything else is a
    failure), carrying `body` (a run summary plus log tail) as the ping's payload."""
    _ping(f"{base_url.rstrip('/')}/{exit_code}", run_id, method="POST", body=body)
