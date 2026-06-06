import html
import re
import unicodedata

MAX_LENGTH = 80
ELLIPSIS_TOTAL = 79
SENTENCE_DELIMITERS = frozenset(".!?")

_TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_html(value):
    decoded = value
    for _ in range(3):
        nxt = html.unescape(decoded)
        if nxt == decoded:
            break
        decoded = nxt
    return _TAG_PATTERN.sub(" ", decoded)


def _collapse_whitespace(value):
    return " ".join(value.split())


def normalize_title(raw_title):
    if raw_title is None:
        return ""
    stripped = _strip_html(raw_title)
    decoded = unicodedata.normalize("NFC", stripped)
    collapsed = _collapse_whitespace(decoded)
    return collapsed.upper()


def format_title(raw_title):
    normalized = normalize_title(raw_title)
    if len(normalized) <= MAX_LENGTH:
        return normalized
    window = normalized[:MAX_LENGTH]
    for index in range(len(window) - 1, -1, -1):
        if window[index] in SENTENCE_DELIMITERS:
            return window[: index + 1]
    truncated_length = ELLIPSIS_TOTAL - 3
    return normalized[:truncated_length] + "..."
