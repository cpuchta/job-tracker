import pytest

from jobscout.dedupe import DedupeBase, split_new
from jobscout.normalize import company_role_key, normalize_url, urls_in_text


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://www.example.com/jobs/1/", "example.com/jobs/1"),
        ("http://example.com/jobs/1?utm_source=linkedin#apply", "example.com/jobs/1"),
        ("EXAMPLE.com/jobs/AbC", "example.com/jobs/AbC"),  # path case is preserved
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_company_role_key_ignores_punctuation_and_spacing():
    assert company_role_key("Acme, Inc.", "Senior  QA Engineer") == company_role_key("acme inc", "senior qa engineer")


def test_urls_in_text_strips_trailing_punctuation():
    assert urls_in_text("Aggregator: https://agg.example/offer/9. Apply soon") == ["https://agg.example/offer/9"]


@pytest.fixture
def base():
    return DedupeBase.from_rows(
        [
            {"link": "https://boards.example/acme/jobs/1", "company": "Acme", "role": "SDET"},
            {"link": None, "company": "Old Co", "role": "QA Lead", "notes": "seen at https://agg.example/x/2"},
        ]
    )


def test_duplicate_by_url_with_tracking_params(base):
    assert base.match({"link": "https://www.boards.example/acme/jobs/1/?ref=x"})


def test_duplicate_by_url_found_in_notes(base):
    assert base.match({"aggregator_link": "https://agg.example/x/2"})


def test_duplicate_by_company_and_role(base):
    assert "company+role" in base.match({"company": "OLD CO", "role": "qa lead", "link": "https://new.example/1"})


def test_new_candidate_is_kept(base):
    assert base.match({"company": "Acme", "role": "Staff SDET", "link": "https://boards.example/acme/jobs/2"}) is None


def test_split_new_removes_duplicates_within_the_batch(base):
    batch = [
        {"company": "Fresh", "role": "QA", "link": "https://a.example/1"},
        {"company": "Fresh", "role": "QA", "link": "https://b.example/other-url"},
        {"company": "Acme", "role": "SDET", "link": "https://elsewhere.example"},
    ]
    new, dupes = split_new(batch, base)
    assert [c["link"] for c in new] == ["https://a.example/1"]
    assert len(dupes) == 2
