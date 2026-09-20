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


class SocialMediaPoster(ABC):
    @abstractmethod
    def post(self, text: str) -> PostRef:
        """Publish a new top-level post and return a reference to it."""

    @abstractmethod
    def reply(self, text: str, parent: PostRef) -> PostRef:
        """Publish a reply to `parent` and return a reference to it."""

    def post_thread(self, texts: list[str]) -> list[PostRef]:
        """Post `texts` as a thread: the first as a root post, the rest as chained replies."""
        if not texts:
            return []
        refs = [self.post(texts[0])]
        for text in texts[1:]:
            refs.append(self.reply(text, refs[-1]))
        return refs
