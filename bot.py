import hashlib
import logging
import signal
import threading
import time

from config import SECRET_REFRESH_SECONDS, load_database_url
from feed_fetcher import FeedFetcher
from feed_store import FeedStore
from hackernews import HackerNewsClient, HackerNewsError
from posts_store import PostsStore
from secret_store import SecretStore
from seen_store import SeenStore
from title_formatter import format_title

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("feedbot")


def _article_digest(link):
    return hashlib.md5(link.encode("utf-8")).hexdigest()


class _Runtime:
    def __init__(self, secrets, seen, hackernews, fetcher):
        self.secrets = secrets
        self.seen = seen
        self.hackernews = hackernews
        self.fetcher = fetcher


def _build_runtime(secrets):
    seen = SeenStore(
        secrets.upstash_url,
        secrets.upstash_token,
        secrets.request_timeout_seconds,
    )
    hackernews = HackerNewsClient(
        secrets.hn_username,
        secrets.hn_password,
        secrets.user_agent,
        secrets.referer,
        secrets.request_timeout_seconds,
    )
    fetcher = FeedFetcher(
        secrets.user_agent,
        secrets.referer,
        secrets.request_timeout_seconds,
    )
    return _Runtime(secrets, seen, hackernews, fetcher)


class FeedBot:
    def __init__(self, database_url):
        self._started_epoch = time.time()
        self._secret_store = SecretStore(database_url)
        self._feed_store = FeedStore(database_url)
        self._posts_store = PostsStore(database_url)
        self._runtime = _build_runtime(self._secret_store.load())
        self._runtime_lock = threading.Lock()
        self._feeds = []
        self._feeds_lock = threading.Lock()
        self._last_feed_refresh = 0.0
        self._stop_event = threading.Event()

    def _current_runtime(self):
        with self._runtime_lock:
            return self._runtime

    def _refresh_secrets(self):
        try:
            new_secrets = self._secret_store.load()
        except Exception as error:
            logger.error("failed to refresh secrets: %s", error)
            return
        with self._runtime_lock:
            current = self._runtime
            if new_secrets.connection_fingerprint() != current.secrets.connection_fingerprint():
                logger.info("connection secrets changed, rebuilding clients")
                self._runtime = _build_runtime(new_secrets)
            else:
                current.secrets = new_secrets

    def _secret_refresh_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(SECRET_REFRESH_SECONDS)
            if self._stop_event.is_set():
                return
            self._refresh_secrets()

    def _refresh_feeds_if_due(self, secrets):
        now = time.time()
        if self._feeds and now - self._last_feed_refresh < secrets.feed_refresh_seconds:
            return
        try:
            feeds = self._feed_store.load_feeds(secrets.feeds_query)
        except Exception as error:
            logger.error("failed to refresh feed list: %s", error)
            return
        with self._feeds_lock:
            self._feeds = feeds
        self._last_feed_refresh = now

    def _current_feeds(self):
        with self._feeds_lock:
            return list(self._feeds)

    def _is_eligible(self, entry, secrets, now):
        if entry.published_epoch is None:
            return False
        if entry.published_epoch < self._started_epoch:
            return False
        if now - entry.published_epoch > secrets.max_article_age_seconds:
            return False
        return True

    def _process_entry(self, runtime, feed, entry):
        if feed.link_is_ignored(entry.link):
            logger.info("ignoring link by feed rule for %s: %s", feed.short_name, entry.link)
            return

        digest = _article_digest(entry.link)
        try:
            if runtime.seen.is_seen(digest):
                return
        except Exception as error:
            logger.error("failed to check seen store for %s: %s", entry.link, error)
            return

        title = format_title(entry.title)
        record = {
            "feed_url": feed.url,
            "feed_name": feed.name,
            "feed_short_name": feed.short_name,
            "feed_country": feed.country,
            "feed_ignore_links": ",".join(feed.ignore_links),
            "article_title": entry.title,
            "formatted_title": title,
            "article_link": entry.link,
            "article_published_epoch": entry.published_epoch,
            "md5_hash": digest,
            "user_agent": runtime.secrets.user_agent,
            "referer": runtime.secrets.referer,
            "hn_outcome": "unknown",
            "hn_http_status": None,
            "hn_response_body": None,
            "hn_response_headers": None,
            "hn_submit_url": None,
            "error_message": None,
        }

        try:
            result = runtime.hackernews.submit(title, entry.link)
        except HackerNewsError as error:
            logger.error("hackernews submit failed for %s: %s", entry.link, error)
            record["hn_outcome"] = "hn_error"
            record["hn_http_status"] = error.http_status
            record["hn_response_body"] = error.response_body
            record["hn_response_headers"] = error.response_headers
            record["error_message"] = str(error)
            self._finalize(runtime, digest, entry.link, record)
            return
        except Exception as error:
            logger.error("unexpected hackernews error for %s: %s", entry.link, error)
            record["hn_outcome"] = "unexpected_error"
            record["error_message"] = str(error)
            self._finalize(runtime, digest, entry.link, record)
            return

        record["hn_outcome"] = result.outcome
        record["hn_http_status"] = result.http_status
        record["hn_response_body"] = result.response_body
        record["hn_response_headers"] = result.response_headers
        record["hn_submit_url"] = result.submit_url
        self._finalize(runtime, digest, entry.link, record)

    def _finalize(self, runtime, digest, link, record):
        self._record_post(record)
        self._mark_seen(runtime, digest, link)

    def _record_post(self, record):
        try:
            self._posts_store.record(record)
        except Exception as error:
            logger.error("failed to record post row for %s: %s", record["article_link"], error)

    def _mark_seen(self, runtime, digest, link):
        try:
            runtime.seen.mark_seen(digest, runtime.secrets.seen_ttl_seconds)
        except Exception as error:
            logger.error("failed to mark %s as seen: %s", link, error)

    def _scan_once(self):
        runtime = self._current_runtime()
        secrets = runtime.secrets
        self._refresh_feeds_if_due(secrets)
        feeds = self._current_feeds()
        now = time.time()
        for feed in feeds:
            if self._stop_event.is_set():
                return
            try:
                entries = runtime.fetcher.fetch(feed.url)
            except Exception as error:
                logger.error("failed to fetch feed %s: %s", feed.url, error)
                continue
            for entry in entries:
                if self._stop_event.is_set():
                    return
                if not self._is_eligible(entry, secrets, now):
                    continue
                self._process_entry(runtime, feed, entry)

    def request_stop(self):
        self._stop_event.set()

    def run(self):
        logger.info(
            "feedbot started at epoch %.0f, refreshing secrets every %ds",
            self._started_epoch,
            SECRET_REFRESH_SECONDS,
        )
        refresher = threading.Thread(
            target=self._secret_refresh_loop, name="secret-refresh", daemon=True
        )
        refresher.start()
        while not self._stop_event.is_set():
            cycle_start = time.time()
            try:
                self._scan_once()
            except Exception as error:
                logger.error("scan cycle failed: %s", error)
            scan_interval = self._current_runtime().secrets.scan_interval_seconds
            wait_seconds = scan_interval - (time.time() - cycle_start)
            if wait_seconds > 0:
                self._stop_event.wait(wait_seconds)
        refresher.join(timeout=SECRET_REFRESH_SECONDS + 1)
        logger.info("feedbot stopped")


def main():
    database_url = load_database_url()
    bot = FeedBot(database_url)

    def _handle_signal(signum, frame):
        logger.info("received signal %s, shutting down", signum)
        bot.request_stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    bot.run()


if __name__ == "__main__":
    main()
