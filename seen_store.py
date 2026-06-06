import logging
from urllib.parse import quote

import requests

logger = logging.getLogger("feedbot.seen")

_KEY_PREFIX = "feedbot:seen:"


class SeenStore:
    def __init__(self, base_url, token, timeout_seconds):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({"Authorization": "Bearer " + token})

    def _key(self, digest):
        return quote(_KEY_PREFIX + digest, safe="")

    def is_seen(self, digest):
        path = "/exists/" + self._key(digest)
        response = self._session.get(
            self._base_url + path, timeout=self._timeout_seconds
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError("upstash exists error: " + str(payload["error"]))
        return payload.get("result") == 1

    def mark_seen(self, digest, ttl_seconds):
        path = "/set/" + self._key(digest) + "/1/EX/" + str(ttl_seconds)
        response = self._session.get(
            self._base_url + path, timeout=self._timeout_seconds
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError("upstash set error: " + str(payload["error"]))
        logger.debug("marked digest as seen: %s", digest)
