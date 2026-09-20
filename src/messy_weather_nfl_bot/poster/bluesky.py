"""Bluesky backend for the SocialMediaPoster abstraction, via the atproto SDK."""

from __future__ import annotations

import os

from atproto import Client, models

from messy_weather_nfl_bot.poster.base import PostRef, SocialMediaPoster

HANDLE_ENV_VAR = "BLUESKY_HANDLE"
APP_PASSWORD_ENV_VAR = "BLUESKY_APP_PASSWORD"


class BlueskyPoster(SocialMediaPoster):
    def __init__(self, client: Client | None = None) -> None:
        self._client = client or Client()
        self._strong_refs: dict[str, models.ComAtprotoRepoStrongRef.Main] = {}
        if client is None:
            handle = os.environ[HANDLE_ENV_VAR]
            app_password = os.environ[APP_PASSWORD_ENV_VAR]
            self._client.login(handle, app_password)

    def _remember(self, uri: str, cid: str) -> None:
        self._strong_refs[uri] = models.ComAtprotoRepoStrongRef.Main(cid=cid, uri=uri)

    def post(self, text: str) -> PostRef:
        response = self._client.send_post(text)
        self._remember(response.uri, response.cid)
        return PostRef(id=response.uri, root_id=response.uri)

    def reply(self, text: str, parent: PostRef) -> PostRef:
        parent_ref = self._strong_refs[parent.id]
        root_ref = self._strong_refs[parent.root_id]
        reply_to = models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref)
        response = self._client.send_post(text, reply_to=reply_to)
        self._remember(response.uri, response.cid)
        return PostRef(id=response.uri, root_id=parent.root_id)
