import logging
from html.parser import HTMLParser

import requests

logger = logging.getLogger("feedbot.hackernews")

_BASE = "https://news.ycombinator.com"
_SUBMIT_URL = _BASE + "/r"
_MAX_RESPONSE_CAPTURE = 65536


class HackerNewsError(Exception):
    def __init__(self, message, http_status=None, response_body=None, response_headers=None):
        super().__init__(message)
        self.http_status = http_status
        self.response_body = response_body
        self.response_headers = response_headers


class SubmitResult:
    __slots__ = ("outcome", "http_status", "response_body", "response_headers", "submit_url")

    def __init__(self, outcome, http_status, response_body, response_headers, submit_url):
        self.outcome = outcome
        self.http_status = http_status
        self.response_body = response_body
        self.response_headers = response_headers
        self.submit_url = submit_url


class _FnidExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fnid = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "input":
            return
        attr_map = dict(attrs)
        if attr_map.get("name") == "fnid":
            value = attr_map.get("value")
            if value:
                self.fnid = value


def _truncate(text):
    if text is None:
        return None
    if len(text) <= _MAX_RESPONSE_CAPTURE:
        return text
    return text[:_MAX_RESPONSE_CAPTURE]


class HackerNewsClient:
    def __init__(self, username, password, user_agent, referer, timeout_seconds):
        self._username = username
        self._password = password
        self._timeout_seconds = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": user_agent, "Referer": referer}
        )
        self._logged_in = False

    def _login(self):
        response = self._session.post(
            _BASE + "/login",
            data={
                "acct": self._username,
                "pw": self._password,
                "goto": "news",
            },
            timeout=self._timeout_seconds,
            allow_redirects=True,
        )
        if response.status_code != 200:
            raise HackerNewsError(
                "login failed with status " + str(response.status_code),
                http_status=response.status_code,
                response_body=_truncate(response.text),
                response_headers=dict(response.headers),
            )
        if "Bad login" in response.text:
            raise HackerNewsError(
                "login failed: bad credentials",
                http_status=response.status_code,
                response_body=_truncate(response.text),
                response_headers=dict(response.headers),
            )
        self._logged_in = True

    def _fetch_fnid(self):
        response = self._session.get(
            _BASE + "/submit", timeout=self._timeout_seconds
        )
        if response.status_code != 200:
            raise HackerNewsError(
                "submit page failed with status " + str(response.status_code),
                http_status=response.status_code,
                response_body=_truncate(response.text),
                response_headers=dict(response.headers),
            )
        if "login" in response.url:
            raise HackerNewsError(
                "not authenticated when fetching submit form",
                http_status=response.status_code,
                response_body=_truncate(response.text),
                response_headers=dict(response.headers),
            )
        extractor = _FnidExtractor()
        extractor.feed(response.text)
        if not extractor.fnid:
            raise HackerNewsError(
                "could not locate fnid on submit form",
                http_status=response.status_code,
                response_body=_truncate(response.text),
                response_headers=dict(response.headers),
            )
        return extractor.fnid

    def submit(self, title, url):
        if not self._logged_in:
            self._login()
        fnid = self._fetch_fnid()
        response = self._session.post(
            _SUBMIT_URL,
            data={
                "fnid": fnid,
                "fnop": "submit-page",
                "title": title,
                "url": url,
            },
            timeout=self._timeout_seconds,
            allow_redirects=True,
        )
        http_status = response.status_code
        response_body = _truncate(response.text)
        response_headers = dict(response.headers)
        if http_status != 200:
            raise HackerNewsError(
                "submit failed with status " + str(http_status),
                http_status=http_status,
                response_body=response_body,
                response_headers=response_headers,
            )
        lowered = response.text.lower()
        if "validation required" in lowered:
            raise HackerNewsError(
                "submit rejected: validation required",
                http_status=http_status,
                response_body=response_body,
                response_headers=response_headers,
            )
        if "you're posting too fast" in lowered:
            raise HackerNewsError(
                "submit rejected: rate limited",
                http_status=http_status,
                response_body=response_body,
                response_headers=response_headers,
            )
        if "that link has already been submitted" in lowered:
            logger.info("link already submitted on hackernews: %s", url)
            return SubmitResult(
                "already_submitted",
                http_status,
                response_body,
                response_headers,
                _SUBMIT_URL,
            )
        logger.info("submitted to hackernews: %s", title)
        return SubmitResult(
            "submitted", http_status, response_body, response_headers, _SUBMIT_URL
        )
