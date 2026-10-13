import json

import pytest

from jobscout.cli import main
from jobscout.rules import APPROVED, BLOCKED, MISSING, check_pay, evaluate, triage


def with_(job: dict, **changes) -> dict:
    return {**job, **changes}


def test_good_job_is_approved(good_job, profile):
    v = evaluate(good_job, profile)
    assert v.status == APPROVED, v
    assert v.score > 0


# ---------------------------------------------------------------- evidence against


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"open": False}, "closed"),
        ({"remote": "hybrid"}, "not fully remote"),
        ({"eligibility": ["us"]}, "region"),
        ({"seniority": "mid"}, "level"),
        ({"flags": ["us_work_authorization"]}, "blocker: us_work_authorization"),
        ({"required_stack": ["Swift", "XCUITest"]}, "required stack"),
        ({"salary": {"max": 3000, "currency": "USD", "period": "month"}}, "pay below floor"),
    ],
)
def test_evidence_against_blocks(good_job, profile, changes, reason):
    v = evaluate(with_(good_job, **changes), profile)
    assert v.status == BLOCKED
    assert any(r.startswith(reason) for r in v.reasons), v.reasons


def test_blocker_stack_only_counts_when_mandatory(good_job, profile):
    job = with_(good_job, stack=["kotlin", "playwright"], required_stack=["playwright"])
    assert evaluate(job, profile).status == APPROVED


def test_consultancy_without_pay_is_blocked_not_missing(good_job, profile):
    v = evaluate(with_(good_job, company_type="consultancy", salary=None), profile)
    assert v.status == BLOCKED
    assert "consultancy without pay" in v.reasons


def test_consultancy_with_pay_is_fine(good_job, profile):
    assert evaluate(with_(good_job, company_type="consultancy"), profile).status == APPROVED


# ---------------------------------------------------------------- absence of data


def test_no_pay_data_goes_to_missing(good_job, profile):
    v = evaluate(with_(good_job, salary=None), profile)
    assert v.status == MISSING
    assert v.missing == ["pay"]


def test_no_async_signal_goes_to_missing(good_job, profile):
    v = evaluate(with_(good_job, async_signals=[], flex_signals=[]), profile)
    assert v.status == MISSING
    assert v.missing == ["async"]


def test_overlap_without_flexibility_goes_to_missing(good_job, profile):
    job = with_(good_job, overlap_required="5h US Eastern", flex_signals=[])
    assert evaluate(job, profile).missing == ["async"]


def test_overlap_with_flexibility_is_fine(good_job, profile):
    job = with_(good_job, overlap_required="4h US Eastern", async_signals=[], flex_signals=["flexible schedule"])
    assert evaluate(job, profile).status == APPROVED


def test_blocking_evidence_wins_over_missing_data(good_job, profile):
    v = evaluate(with_(good_job, remote="onsite", salary=None), profile)
    assert v.status == BLOCKED


def test_async_check_can_be_disabled(good_job, profile):
    profile["require_async_evidence"] = False
    assert evaluate(with_(good_job, async_signals=[]), profile).status == APPROVED


# ------------------------------------------------------------------------- pay


@pytest.mark.parametrize(
    "salary, outcome",
    [
        ({"min": 40000, "max": 65000, "currency": "USD", "period": "year"}, "ok"),  # top of range reaches floor
        ({"max": 28, "currency": "USD", "period": "hour"}, "below"),
        ({"max": 22000, "currency": "BRL", "period": "month", "contract": "CLT"}, "ok"),
        ({"max": 18000, "currency": "BRL", "period": "month", "contract": "CLT"}, "below"),
        # BRL on a PJ contract converts to USD: 30000 * 0.18 = 5400 >= 5000
        ({"max": 30000, "currency": "BRL", "period": "month", "contract": "PJ"}, "ok"),
        ({"max": 9000, "currency": "EUR", "period": "month"}, "unknown"),  # no fx rate configured
        (None, "unknown"),
    ],
)
def test_check_pay(profile, salary, outcome):
    assert check_pay(salary, profile["pay"])[0] == outcome


# --------------------------------------------------------------------- ranking


def test_ranking_prefers_published_pay_and_fit_signals(good_job, profile):
    plain = with_(good_job, title="Senior QA Engineer", stack=[], company="Plain")
    estimated = with_(plain, salary={**good_job["salary"], "source": "estimated"}, company="Estimated")
    strong = with_(good_job, title="Staff Quality Engineer, LLM evaluation", seniority="staff", company="Strong")
    result = triage([estimated, plain, strong], profile)
    assert [j["company"] for j in result["top"]] == ["Strong", "Plain", "Estimated"]


def test_triage_caps_top_and_keeps_runner_ups(good_job, profile):
    profile["max_per_run"] = 2
    jobs = [with_(good_job, company=f"Co{i}", link=f"https://x.example/{i}") for i in range(4)]
    result = triage(jobs, profile)
    assert len(result["top"]) == 2
    assert len(result["runner_up"]) == 2


# ------------------------------------------------------------------------- CLI


def test_cli_evaluate_markdown(tmp_path, capsys, good_job):
    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps([good_job, with_(good_job, company="NoPay", salary=None), with_(good_job, remote="hybrid")]))
    main(["evaluate", "--profile", "config/profile.example.yaml", "--jobs", str(jobs), "--markdown"])
    out = capsys.readouterr().out
    assert "## Top this run" in out
    assert "NoPay" in out and "missing pay" in out
    assert "not fully remote: 1" in out


def test_cli_dedupe(tmp_path, capsys):
    tracker = tmp_path / "tracker.json"
    tracker.write_text(json.dumps({"results": [{"link": "https://a.example/1"}]}))
    found = tmp_path / "found.json"
    found.write_text(json.dumps([{"link": "https://a.example/1/"}, {"link": "https://b.example/2"}]))
    main(["dedupe", "--tracker", str(tracker), "--candidates", str(found)])
    out = json.loads(capsys.readouterr().out)
    assert len(out["new"]) == 1 and len(out["duplicates"]) == 1
