import logging

import psycopg
from psycopg.rows import tuple_row

logger = logging.getLogger("feedbot.secrets")

USER_AGENT = "OdinGlynn-Martin_feedFetch/1.0.0 +odinglynn.com)"
REFERER = "www.odinglynn.com"

_REQUIRED_STRING_KEYS = (
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "HN_USERNAME",
    "HN_PASSWORD",
)

_INT_DEFAULTS = {
    "SCAN_INTERVAL_SECONDS": 30,
    "FEED_REFRESH_SECONDS": 300,
    "MAX_ARTICLE_AGE_SECONDS": 86400,
    "SEEN_TTL_SECONDS": 172800,
    "REQUEST_TIMEOUT_SECONDS": 30,
}

_DEFAULT_FEEDS_QUERY = "SELECT url, name, shortname, ignorelinks, country FROM feeds"


def _require_string(raw, key):
    value = raw.get(key)
    if value is None or value.strip() == "":
        raise RuntimeError("missing required secret: " + key)
    return value.strip()


def _parse_int(raw, key, default):
    value = raw.get(key)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value.strip())
    except ValueError as error:
        raise RuntimeError("secret " + key + " must be an integer") from error
    if parsed <= 0:
        raise RuntimeError("secret " + key + " must be positive")
    return parsed


class Secrets:
    __slots__ = (
        "upstash_url",
        "upstash_token",
        "hn_username",
        "hn_password",
        "scan_interval_seconds",
        "feed_refresh_seconds",
        "max_article_age_seconds",
        "seen_ttl_seconds",
        "request_timeout_seconds",
        "feeds_query",
        "user_agent",
        "referer",
    )

    def __init__(self, raw):
        self.upstash_url = _require_string(raw, "UPSTASH_REDIS_REST_URL").rstrip("/")
        self.upstash_token = _require_string(raw, "UPSTASH_REDIS_REST_TOKEN")
        self.hn_username = _require_string(raw, "HN_USERNAME")
        self.hn_password = _require_string(raw, "HN_PASSWORD")
        self.scan_interval_seconds = _parse_int(
            raw, "SCAN_INTERVAL_SECONDS", _INT_DEFAULTS["SCAN_INTERVAL_SECONDS"]
        )
        self.feed_refresh_seconds = _parse_int(
            raw, "FEED_REFRESH_SECONDS", _INT_DEFAULTS["FEED_REFRESH_SECONDS"]
        )
        self.max_article_age_seconds = _parse_int(
            raw, "MAX_ARTICLE_AGE_SECONDS", _INT_DEFAULTS["MAX_ARTICLE_AGE_SECONDS"]
        )
        self.seen_ttl_seconds = _parse_int(
            raw, "SEEN_TTL_SECONDS", _INT_DEFAULTS["SEEN_TTL_SECONDS"]
        )
        self.request_timeout_seconds = _parse_int(
            raw, "REQUEST_TIMEOUT_SECONDS", _INT_DEFAULTS["REQUEST_TIMEOUT_SECONDS"]
        )
        feeds_query = raw.get("FEEDS_QUERY")
        if feeds_query is None or feeds_query.strip() == "":
            self.feeds_query = _DEFAULT_FEEDS_QUERY
        else:
            self.feeds_query = feeds_query.strip()
        self.user_agent = USER_AGENT
        self.referer = REFERER

    def connection_fingerprint(self):
        return (
            self.upstash_url,
            self.upstash_token,
            self.hn_username,
            self.hn_password,
            self.request_timeout_seconds,
        )


class SecretStore:
    def __init__(self, database_url, query="SELECT key, value FROM secrets"):
        self._database_url = database_url
        self._query = query

    def load(self):
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(self._query)
                rows = cursor.fetchall()
        raw = {}
        for row in rows:
            if not row or row[0] is None:
                continue
            key = str(row[0]).strip()
            value = row[1]
            raw[key] = "" if value is None else str(value)
        missing = [key for key in _REQUIRED_STRING_KEYS if not raw.get(key, "").strip()]
        if missing:
            raise RuntimeError("secrets table is missing keys: " + ", ".join(missing))
        secrets = Secrets(raw)
        logger.info("loaded %d secrets from postgres", len(raw))
        return secrets
