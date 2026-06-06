import datetime
import json
import logging

import psycopg

logger = logging.getLogger("feedbot.posts")

_INSERT_SQL = """
INSERT INTO posts (
    feed_url, feed_name, feed_short_name, feed_country, feed_ignore_links,
    article_title, formatted_title, article_link, article_published_at,
    md5_hash, user_agent, referer, hn_outcome, hn_http_status,
    hn_response_body, hn_response_headers, hn_submit_url, error_message
) VALUES (
    %(feed_url)s, %(feed_name)s, %(feed_short_name)s, %(feed_country)s, %(feed_ignore_links)s,
    %(article_title)s, %(formatted_title)s, %(article_link)s, %(article_published_at)s,
    %(md5_hash)s, %(user_agent)s, %(referer)s, %(hn_outcome)s, %(hn_http_status)s,
    %(hn_response_body)s, %(hn_response_headers)s, %(hn_submit_url)s, %(error_message)s
)
"""


def _epoch_to_utc(epoch):
    if epoch is None:
        return None
    return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)


class PostsStore:
    def __init__(self, database_url):
        self._database_url = database_url

    def record(self, record):
        headers = record.get("hn_response_headers")
        params = {
            "feed_url": record["feed_url"],
            "feed_name": record["feed_name"],
            "feed_short_name": record["feed_short_name"],
            "feed_country": record["feed_country"],
            "feed_ignore_links": record["feed_ignore_links"],
            "article_title": record["article_title"],
            "formatted_title": record["formatted_title"],
            "article_link": record["article_link"],
            "article_published_at": _epoch_to_utc(record.get("article_published_epoch")),
            "md5_hash": record["md5_hash"],
            "user_agent": record["user_agent"],
            "referer": record["referer"],
            "hn_outcome": record["hn_outcome"],
            "hn_http_status": record.get("hn_http_status"),
            "hn_response_body": record.get("hn_response_body"),
            "hn_response_headers": json.dumps(headers) if headers is not None else None,
            "hn_submit_url": record.get("hn_submit_url"),
            "error_message": record.get("error_message"),
        }
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_INSERT_SQL, params)
            connection.commit()
        logger.debug("recorded post row for %s", record["article_link"])
