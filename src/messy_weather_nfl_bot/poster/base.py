"""Abstraction over social media backends, so new platforms can be added later."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PostRef:
    """An opaque reference to a published post, usable as a `reply()` parent.

    `root_id` tracks the original root post of the thread (equal to `id` for a root
    post itself), since some backends (e.g. Bluesky) need the thread root, not just
    the immediate parent, to build a valid reply.
    """

    id: str
    root_id: str


class PartialThreadError(Exception):
    """Raised by `post_thread` when some, but not all, posts in the thread went out -
    e.g. the root published but a later reply failed. Carries the refs that did
    succeed, so callers can tell a partially-posted thread from a totally failed one."""

    def __init__(self, posted: list[PostRef], cause: BaseException) -> None:
        super().__init__(f"posted {len(posted)} of the thread before failing: {cause}")
        self.posted = posted


class SocialMediaPoster(ABC):
    @abstractmethod
    def post(self, text: str) -> PostRef:
        """Publish a new top-level post and return a reference to it."""

    @abstractmethod
    def reply(self, text: str, parent: PostRef) -> PostRef:
        """Publish a reply to `parent` and return a reference to it."""

    def post_thread(self, texts: list[str]) -> list[PostRef]:
        """Post `texts` as a thread: the first as a root post, the rest as chained replies.

        Raises `PartialThreadError` (wrapping whatever posted successfully) if a later
        post in the thread fails after an earlier one already went out.
        """
        if not texts:
            return []
        refs: list[PostRef] = []
        try:
            refs.append(self.post(texts[0]))
            for text in texts[1:]:
                refs.append(self.reply(text, refs[-1]))
        except Exception as exc:
            if refs:
                raise PartialThreadError(refs, exc) from exc
            raise
        return refs
