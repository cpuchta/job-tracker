"""Fit rules: turn one verified posting into a verdict.

A verdict is one of three outcomes:

* ``approved``     passes every rule; becomes a tracker row (ranked, capped per run).
* ``missing_data`` fails only because something is *absent* (no async signal, no pay
                   data). Shown in the digest for a human decision, never auto added.
* ``blocked``      fails with evidence *against* it (hybrid, wrong region, pay below
                   the floor, a hard blocker). Listed by reason only.

The split between "missing" and "blocked" is the most important design decision in
this module. Treating absent data as a block silently drops exactly the postings
that are hardest to evaluate, which are often the interesting ones.

The verified posting is a dict with these keys (all optional, unknown means absent):

    title, company, link
    open:              bool
    remote:            "fully" | "hybrid" | "onsite"
    eligibility:       list of region codes, e.g. ["brazil"], ["latam"], ["us"]
    seniority:         "junior" | "mid" | "senior" | "staff" | "principal" | "lead" |
                       "manager" | "head" | "director"
    async_signals:     list of literal quotes
    flex_signals:      list of literal quotes
    overlap_required:  str, e.g. "5h US Eastern"
    salary:            {"min", "max", "currency", "period": month|year|hour,
                        "source": "published"|"estimated", "contract": ...}
    company_type:      "product" | "consultancy"
    flags:             list of hard-blocker flags found, e.g. ["us_work_authorization"]
    required_stack:    list of technologies listed as mandatory
    stack:             list of technologies mentioned anywhere
"""

from __future__ import annotations

from dataclasses import dataclass, field

APPROVED = "approved"
MISSING = "missing_data"
BLOCKED = "blocked"

_SENIOR_PLUS_BONUS = {"staff", "principal", "lead", "manager", "head", "director"}


@dataclass
class Verdict:
    status: str
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    score: float = 0.0
    pay_note: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "reasons": self.reasons,
            "missing": self.missing,
            "score": round(self.score, 2),
            "pay_note": self.pay_note,
        }


# --------------------------------------------------------------------------- pay


def _to_usd(amount: float, currency: str, fx: dict) -> float | None:
    if currency.upper() == "USD":
        return amount
    rate = fx.get(currency.upper())
    return amount * rate if rate else None


def check_pay(salary: dict | None, pay_cfg: dict) -> tuple[str, str]:
    """Return (outcome, note) where outcome is "ok", "below" or "unknown".

    The top of a published range is compared with the floor, so a wide range that
    reaches the floor passes. Local currency salaries on the local contract type
    (for example BRL on CLT) use the local floor, everything else converts to USD.
    """
    if not salary or salary.get("max") is None and salary.get("min") is None:
        return "unknown", "no pay data"

    top = salary.get("max") if salary.get("max") is not None else salary["min"]
    currency = (salary.get("currency") or "USD").upper()
    period = salary.get("period", "year")
    source = salary.get("source", "published")
    local = pay_cfg.get("local") or {}

    if (
        local
        and currency == local.get("currency", "").upper()
        and (salary.get("contract") or "").upper() == local.get("contract", "").upper()
    ):
        floor = local.get(period)
        if floor is None:
            return "unknown", f"no local floor for period '{period}'"
        outcome = "ok" if top >= floor else "below"
        return outcome, f"{currency} {top:,.0f}/{period} vs local floor {floor:,.0f} ({source})"

    usd = _to_usd(top, currency, pay_cfg.get("fx", {}))
    if usd is None:
        return "unknown", f"no fx rate for {currency}"
    floor = (pay_cfg.get("usd") or {}).get(period)
    if floor is None:
        return "unknown", f"no USD floor for period '{period}'"
    outcome = "ok" if usd >= floor else "below"
    return outcome, f"USD {usd:,.0f}/{period} vs floor {floor:,.0f} ({source})"


# ------------------------------------------------------------------------- rules


def evaluate(job: dict, profile: dict) -> Verdict:
    blocked: list[str] = []
    missing: list[str] = []

    # Evidence against: each one blocks.
    if job.get("open") is False:
        blocked.append("closed")
    if job.get("remote") and job["remote"] != "fully":
        blocked.append(f"not fully remote ({job['remote']})")

    eligible = [r.lower() for r in profile.get("eligibility", [])]
    job_regions = [r.lower() for r in job.get("eligibility", [])]
    if eligible and job_regions and not set(job_regions) & set(eligible):
        blocked.append(f"region ({', '.join(job_regions)})")
    elif eligible and not job_regions:
        missing.append("eligibility")

    accepted = [s.lower() for s in profile.get("seniority", [])]
    level = (job.get("seniority") or "").lower()
    if accepted and level and level not in accepted:
        blocked.append(f"level ({level})")

    blockers = profile.get("blockers", {})
    for flag in job.get("flags", []):
        if flag in blockers.get("flags", []):
            blocked.append(f"blocker: {flag}")

    stack_block = {s.lower() for s in blockers.get("required_stack", [])}
    hits = sorted({s for s in (x.lower() for x in job.get("required_stack", [])) if s in stack_block})
    if hits:
        blocked.append(f"required stack: {', '.join(hits)}")

    pay_outcome, pay_note = check_pay(job.get("salary"), profile.get("pay", {}))
    is_consultancy = job.get("company_type") == "consultancy"
    if pay_outcome == "below":
        blocked.append("pay below floor")
    elif pay_outcome == "unknown":
        if is_consultancy and profile.get("consultancy_requires_pay", True):
            blocked.append("consultancy without pay")
        else:
            missing.append("pay")

    # Absence of evidence: never blocks on its own.
    if profile.get("require_async_evidence", True):
        has_async = bool(job.get("async_signals"))
        has_flex = bool(job.get("flex_signals"))
        # Required overlap is fine only when flexibility is also mentioned.
        if not (has_async or has_flex) or (job.get("overlap_required") and not has_flex):
            missing.append("async")

    if blocked:
        return Verdict(BLOCKED, reasons=blocked, missing=missing, pay_note=pay_note)
    if missing:
        return Verdict(MISSING, missing=missing, pay_note=pay_note, score=score(job, profile))
    return Verdict(APPROVED, pay_note=pay_note, score=score(job, profile))


# ----------------------------------------------------------------------- ranking


def score(job: dict, profile: dict) -> float:
    """Rank approved postings. Weights come from ``profile['ranking']``."""
    w = {
        "published_pay": 3.0,
        "estimated_pay": 1.0,
        "senior_plus": 2.0,
        "explicit_async": 2.0,
        "flex_only": 1.0,
        "eligibility_first": 2.0,
        "eligibility_second": 1.0,
        **profile.get("ranking", {}).get("weights", {}),
    }
    total = 0.0

    salary = job.get("salary") or {}
    if salary:
        total += w["published_pay"] if salary.get("source", "published") == "published" else w["estimated_pay"]

    if (job.get("seniority") or "").lower() in _SENIOR_PLUS_BONUS:
        total += w["senior_plus"]

    if job.get("async_signals"):
        total += w["explicit_async"]
    elif job.get("flex_signals"):
        total += w["flex_only"]

    eligible = [r.lower() for r in profile.get("eligibility", [])]
    regions = {r.lower() for r in job.get("eligibility", [])}
    if eligible and eligible[0] in regions:
        total += w["eligibility_first"]
    elif len(eligible) > 1 and eligible[1] in regions:
        total += w["eligibility_second"]

    haystack = " ".join(
        [job.get("title", ""), " ".join(job.get("stack", [])), job.get("summary", "")]
    ).lower()
    for signal, weight in profile.get("ranking", {}).get("fit_signals", {}).items():
        if signal.lower() in haystack:
            total += float(weight)

    return total


def triage(jobs: list[dict], profile: dict) -> dict:
    """Evaluate a batch and apply the per-run cap to approved postings."""
    cap = int(profile.get("max_per_run", 5))
    results = {APPROVED: [], MISSING: [], BLOCKED: []}
    for job in jobs:
        verdict = evaluate(job, profile)
        results[verdict.status].append({**job, "verdict": verdict.as_dict()})
    results[APPROVED].sort(key=lambda j: j["verdict"]["score"], reverse=True)
    results[MISSING].sort(key=lambda j: j["verdict"]["score"], reverse=True)
    results["top"] = results[APPROVED][:cap]
    results["runner_up"] = results[APPROVED][cap:]
    return results
