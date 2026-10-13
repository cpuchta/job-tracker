"""Normalization helpers used for deduplication.

Two postings are considered the same when either their normalized URL or their
normalized company + role pair matches. Both checks are needed: the same job is
often published under several URLs (ATS, aggregator, LinkedIn), and the same URL
is sometimes re-posted with tracking parameters.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_URL_IN_TEXT = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_url(url: str | None) -> str:
    """Return a comparable form of a job URL.

    Drops protocol, ``www.``, query string, fragment and trailing slash, and
    lowercases the host. The path keeps its case because some ATS ids are
    case sensitive.

    >>> normalize_url("https://www.Boards.example.com/acme/jobs/123/?utm_source=x")
    'boards.example.com/acme/jobs/123'
    """
    if not url:
        return ""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    return f"{host}{path}"


def company_role_key(company: str | None, role: str | None) -> str:
    """Return a lowercase, punctuation free ``company|role`` key.

    >>> company_role_key("Acme, Inc.", "Senior QA  Engineer")
    'acme inc|senior qa engineer'
    """

    def clean(value: str | None) -> str:
        return _NON_WORD.sub(" ", (value or "").lower()).strip()

    return f"{clean(company)}|{clean(role)}"


def urls_in_text(text: str | None) -> list[str]:
    """Extract every URL from free text, for trackers that keep extra links in a notes field."""
    if not text:
        return []
    return [m.rstrip(".,;") for m in _URL_IN_TEXT.findall(text)]
