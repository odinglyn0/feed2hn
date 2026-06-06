import calendar
import logging

import feedparser
import requests

logger = logging.getLogger("feedbot.fetcher")


class FeedEntry:
    def __init__(self, title, link, published_epoch):
        self.title = title
        self.link = link
        self.published_epoch = published_epoch


def _entry_epoch(entry):
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed is not None:
            return calendar.timegm(parsed)
    return None


class FeedFetcher:
    def __init__(self, user_agent, referer, timeout_seconds):
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": user_agent, "Referer": referer}
        )

    def fetch(self, feed_url):
        response = self._session.get(feed_url, timeout=self._timeout_seconds)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise RuntimeError(
                "failed to parse feed " + feed_url + ": " + str(parsed.bozo_exception)
            )
        entries = []
        for raw in parsed.entries:
            link = raw.get("link")
            title = raw.get("title")
            if not link or not title:
                continue
            entries.append(FeedEntry(title, link.strip(), _entry_epoch(raw)))
        return entries
