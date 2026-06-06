import logging
import re

import psycopg
from psycopg.rows import tuple_row

logger = logging.getLogger("feedbot.store")

_SHORT_NAME_PATTERN = re.compile(r"^[A-Z]{2,3}$")


def _parse_ignore_links(raw):
    if raw is None:
        return ()
    parts = []
    for chunk in str(raw).split(","):
        cleaned = chunk.strip()
        if cleaned:
            parts.append(cleaned)
    return tuple(parts)


class Feed:
    __slots__ = ("url", "name", "short_name", "ignore_links", "country")

    def __init__(self, url, name, short_name, ignore_links, country):
        self.url = url
        self.name = name
        self.short_name = short_name
        self.ignore_links = ignore_links
        self.country = country

    def link_is_ignored(self, link):
        for needle in self.ignore_links:
            if needle in link:
                return True
        return False


class FeedStore:
    def __init__(self, database_url):
        self._database_url = database_url

    def load_feeds(self, feeds_query):
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(feeds_query)
                rows = cursor.fetchall()
        feeds = []
        seen_urls = set()
        for row in rows:
            feed = self._build_feed(row)
            if feed is None:
                continue
            if feed.url in seen_urls:
                continue
            seen_urls.add(feed.url)
            feeds.append(feed)
        logger.info("loaded %d valid feeds from postgres", len(feeds))
        return feeds

    def _build_feed(self, row):
        if not row or len(row) < 5:
            logger.warning("skipping feed row with unexpected shape: %r", row)
            return None
        url = None if row[0] is None else str(row[0]).strip()
        name = None if row[1] is None else str(row[1]).strip()
        short_name = None if row[2] is None else str(row[2]).strip()
        ignore_links = _parse_ignore_links(row[3])
        country = None if row[4] is None else str(row[4]).strip()

        if not url:
            logger.warning("skipping feed row with empty url")
            return None
        if not name:
            logger.warning("skipping feed %s: empty name", url)
            return None
        if not short_name or not _SHORT_NAME_PATTERN.match(short_name):
            logger.warning(
                "skipping feed %s: shortName must be 2-3 uppercase letters, got %r",
                url,
                short_name,
            )
            return None
        if not country or not country[0].isupper():
            logger.warning(
                "skipping feed %s: country must start with a capital letter, got %r",
                url,
                country,
            )
            return None
        return Feed(url, name, short_name, ignore_links, country)
