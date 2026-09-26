import typing as t

import pytest
from atproto import Client
from atproto.exceptions import InvokeTimeoutError, NetworkError

from messy_weather_nfl_bot.poster.base import PartialThreadError, PostRef
from messy_weather_nfl_bot.poster.bluesky import BlueskyPoster


class _DummyClient:
    """Stands in for atproto's Client - BlueskyPoster only calls login() when no
    client is injected, so passing one skips that entirely."""


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def _poster() -> BlueskyPoster:
    return BlueskyPoster(client=t.cast(Client, _DummyClient()))


def test_invoke_timeout_error_is_not_retryable() -> None:
    poster = _poster()
    assert poster._is_retryable(InvokeTimeoutError()) is False


def test_other_atproto_errors_are_retryable() -> None:
    poster = _poster()
    assert poster._is_retryable(NetworkError()) is True
    assert poster._is_retryable(RuntimeError("unrelated")) is True


class _TimesOutOnReply(BlueskyPoster):
    """A root post that succeeds, but every reply times out with no response - the
    ambiguous case where the reply may have actually gone through."""

    def __init__(self) -> None:
        super().__init__(client=t.cast(Client, _DummyClient()))
        self.reply_attempts = 0

    def post(self, text: str) -> PostRef:
        return PostRef(id="root", root_id="root")

    def reply(self, text: str, parent: PostRef) -> PostRef:
        self.reply_attempts += 1
        raise InvokeTimeoutError()


def test_post_thread_does_not_retry_a_reply_that_timed_out() -> None:
    # A timeout means no response ever arrived - the reply may have already gone
    # through server-side, so retrying it risks posting it twice. It should fail
    # immediately (stalling the thread as partial) rather than being retried.
    poster = _TimesOutOnReply()

    with pytest.raises(PartialThreadError):
        poster.post_thread(["root post", "reply"])

    assert poster.reply_attempts == 1
