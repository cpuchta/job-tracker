from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def profile() -> dict:
    return yaml.safe_load((ROOT / "config" / "profile.example.yaml").read_text())


@pytest.fixture
def good_job() -> dict:
    """A posting that passes every rule in the example profile."""
    return {
        "title": "Senior QA Engineer, Playwright",
        "company": "Example Product Co",
        "link": "https://job-boards.greenhouse.io/example/jobs/1",
        "open": True,
        "remote": "fully",
        "eligibility": ["latam"],
        "seniority": "senior",
        "async_signals": ["We are async-first and document everything"],
        "flex_signals": [],
        "salary": {"min": 70000, "max": 90000, "currency": "USD", "period": "year", "source": "published"},
        "company_type": "product",
        "flags": [],
        "required_stack": ["typescript", "playwright"],
        "stack": ["typescript", "playwright", "github actions"],
    }
