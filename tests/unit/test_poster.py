import pytest

from messy_weather_nfl_bot.poster.base import PartialThreadError, PostRef, SocialMediaPoster
from messy_weather_nfl_bot.poster.console import ConsolePoster


def test_post_thread_empty_returns_no_refs() -> None:
    poster = ConsolePoster()
    assert poster.post_thread([]) == []


def test_post_thread_single_text_posts_once() -> None:
    poster = ConsolePoster()
    refs = poster.post_thread(["hello"])
    assert len(refs) == 1
    assert refs[0].root_id == refs[0].id
    assert poster.posted == ["hello"]


def test_post_thread_multiple_texts_chain_replies_to_same_root() -> None:
    poster = ConsolePoster()
    refs = poster.post_thread(["root", "reply 1", "reply 2"])

    assert len(refs) == 3
    assert poster.posted == ["root", "reply 1", "reply 2"]

    root_id = refs[0].id
    # Every post in the thread traces back to the same root, not just its immediate parent.
    assert all(ref.root_id == root_id for ref in refs)
    assert refs[0].id != refs[1].id != refs[2].id


class _FailsAfterFirstPost(SocialMediaPoster):
    """A poster whose root post succeeds but every reply fails."""

    def post(self, text: str) -> PostRef:
        return PostRef(id="root", root_id="root")

    def reply(self, text: str, parent: PostRef) -> PostRef:
        raise RuntimeError("platform outage")


class _FailsOnFirstPost(SocialMediaPoster):
    def post(self, text: str) -> PostRef:
        raise RuntimeError("platform outage")

    def reply(self, text: str, parent: PostRef) -> PostRef:
        raise AssertionError("unreachable")


def test_post_thread_raises_partial_thread_error_if_a_reply_fails_after_the_root_posted() -> None:
    poster = _FailsAfterFirstPost()

    with pytest.raises(PartialThreadError) as exc_info:
        poster.post_thread(["root", "reply"])

    # The root did publish - callers need that to avoid reporting "nothing posted".
    assert len(exc_info.value.posted) == 1
    assert exc_info.value.posted[0].id == "root"


def test_post_thread_reraises_plainly_if_nothing_posted_at_all() -> None:
    poster = _FailsOnFirstPost()

    with pytest.raises(RuntimeError, match="platform outage"):
        poster.post_thread(["root", "reply"])
