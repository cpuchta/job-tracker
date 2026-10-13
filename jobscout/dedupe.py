"""Deduplicate freshly found postings against everything already in the tracker.

The tracker export is a JSON list of rows. Only these keys are read, all optional:
``link``, ``company``, ``role``, ``notes``. Rows of every status count, including
ones marked invalid or rejected, so a dead posting never comes back as "new".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .normalize import company_role_key, normalize_url, urls_in_text


@dataclass
class DedupeBase:
    urls: set[str] = field(default_factory=set)
    pairs: set[str] = field(default_factory=set)

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "DedupeBase":
        base = cls()
        for row in rows:
            for url in [row.get("link"), *urls_in_text(row.get("notes"))]:
                norm = normalize_url(url)
                if norm:
                    base.urls.add(norm)
            if row.get("company") and row.get("role"):
                base.pairs.add(company_role_key(row["company"], row["role"]))
        return base

    def match(self, candidate: dict) -> str | None:
        """Return why the candidate is a duplicate, or ``None`` if it is new."""
        for key in ("link", "company_link", "aggregator_link"):
            norm = normalize_url(candidate.get(key))
            if norm and norm in self.urls:
                return f"url already tracked: {norm}"
        if candidate.get("company") and candidate.get("role"):
            pair = company_role_key(candidate["company"], candidate["role"])
            if pair in self.pairs:
                return f"company+role already tracked: {pair}"
        return None


def split_new(candidates: list[dict], base: DedupeBase) -> tuple[list[dict], list[dict]]:
    """Split candidates into (new, duplicates).

    Duplicates inside the candidate batch itself are also caught, so two search
    queries returning the same posting yield one row.
    """
    new: list[dict] = []
    dupes: list[dict] = []
    seen = DedupeBase(urls=set(base.urls), pairs=set(base.pairs))
    for cand in candidates:
        reason = seen.match(cand)
        if reason:
            dupes.append({**cand, "duplicate_reason": reason})
            continue
        new.append(cand)
        seen.urls.update(
            n for n in (normalize_url(cand.get(k)) for k in ("link", "company_link", "aggregator_link")) if n
        )
        if cand.get("company") and cand.get("role"):
            seen.pairs.add(company_role_key(cand["company"], cand["role"]))
    return new, dupes
