# Lessons learned

This collector has been running weekly against a real job search since August 2026.
The first design did not survive contact with reality. These are the things that cost
time to discover, written down so you do not have to rediscover them.

## 1. The agent sandbox usually has no open internet

Hosted agent sandboxes typically sit behind a proxy that only allows package registries
and the model provider's own endpoints. Any `requests` or `curl` to a job board returns
`403 Tunnel connection failed`. **A Python scraper that calls job board APIs will not
run there**, neither interactively nor on a schedule. The only doors to the web are the
agent's own web search and web fetch tools.

So the collector is a *search playbook* the agent follows, not a network script.
Filtering and dedupe stay in local code, which needs no network. That is why
`jobscout` has zero network calls.

## 2. Generic remote job boards do not filter by keyword

| Source type | What happened |
|---|---|
| Large remote job API | Keyword parameter silently ignored, feed of ~97,000 jobs |
| EU focused board | Search parameter ignored, mostly one country's market |
| Tag based board | `?tag=qa` returned zero results |
| Small remote board | Tiny feed, no filter at all |
| RSS based board | Category RSS works, search RSS returns 406 |
| Popular remote board | `robots.txt` disallows automated collection; respect it |

Sifting tens of thousands of generic postings through web fetch is not viable. Searching
the ATS domains directly with `site:` filters is.

## 3. Your market is probably not on those boards anyway

Look at where the jobs you actually applied to came from. In this search, after 130+
tracker rows, almost everything came from LinkedIn and from companies' own ATS pages:
Greenhouse, Lever, Ashby, Workable, Recruitee, Teamtailor, SmartRecruiters, Rippling.
Build your queries around that, not around what is popular.

## 4. Which ATS pages render for a fetcher

| ATS | Renders via web fetch | Notes |
|---|---|---|
| Greenhouse | Yes | Public API is even better: `boards-api.greenhouse.io/v1/boards/<org>/jobs` |
| Lever | Yes | |
| Workable | Yes | |
| SmartRecruiters | Yes | |
| Teamtailor | Yes | |
| Recruitee | Yes | |
| Ashby | No, JS only | The `/application` sub-page often renders. Public API returned 404 in tests |
| Workday | No, JS only | Use the search snippet and mark location as unconfirmed |
| LinkedIn | No, login wall | Look for the same posting on the company's ATS |

## 5. Postings die faster than you can apply

One manual sweep found **15 of 26** queued "To Apply" rows dead: closed, removed or no
longer eligible, several less than a week old. Review time was going to jobs that no
longer existed. That is why every run starts with revalidation (phase 1) before it
searches for anything new.

Revalidation has hard safeguards, learned the hard way:

- only rows in "To Apply" are touched, never anything you already acted on
- ambiguity, a timeout or a page that did not render never marks a row Invalid
- age alone never marks a row Invalid

## 6. Web fetch can return a cached copy of a dead posting

On the same day, two postings returned their full description through web fetch and an
`error=true` redirect in a real browser. Where the decision matters, trust the browser.

## 7. "Missing" is not the same as "blocked"

The original rules treated "no async signal" and "no salary data" as blocks. After a
few weeks, the log showed the pattern: the two strongest postings on the axis the
candidate cared most about (AI quality roles eligible for her region) were both dropped
for missing data, not for anything wrong with them.

The fix is the three-way verdict in `jobscout/rules.py`:

- **Evidence against** (hybrid, wrong region, pay below floor, a hard blocker) blocks.
- **Absence of evidence** (no async mention, no pay data) goes to a separate digest
  section for a human decision, and never becomes a tracker row automatically.

## 8. A false block costs the whole posting

A posting listing "at least one of C#, Java or TypeScript" was marked blocked for C#.
By the time it was re-read, it had been taken down. Blocker technologies must only
count when they are **mandatory**, which is why the verification step asks for
`REQUIRED_STACK` and `STACK` separately.

## 9. Fixed queries saturate

After a few runs, most fixed queries return only things already in the dedupe base.
New candidates came almost entirely from the agent's own variations, and from one new
query (AI and LLM quality roles on ATS domains). Treat the query list as something the
run log should keep editing: promote queries that find new things, retire ones that do
not.

## 10. Read the whole board of a good company

Twice, the best posting of a run came from re-reading the full job board of a company
already known to have a remote, async culture, with a title (for example "Quality
Platform Engineer") that no role keyword search would have matched. That became
`watch_companies` in the queries file.

## 11. Estimating pay: sibling reqs beat salary sites

When a posting has no range, the best estimate is a sibling posting at the same company
and level that does publish one (often a US req, where pay transparency laws apply).
Salary aggregator sites often do not render for a fetcher, and country level averages
do not hold up in a salary conversation. Always mark an estimate as estimated.

## 12. Notion specifics

- `query-data-sources` in **SQL mode** has a workspace quota and stops answering.
  **View mode** does not; paginate with `start_cursor`.
- Large results come back saved to a file. Process them with Python rather than
  reading them into the model's context.
- Write operations occasionally fail with a transient approval error. Retrying after
  other tool calls usually works.
- A `url` property may be rejected depending on the API path you use. Keeping links in
  a text property or the notes field always works, and `jobscout` reads URLs from notes.

## 13. Look for prompt injection, report it, never obey it

Every posting is read looking for text aimed at AI systems. None was found across
dozens of postings. Two companies stated the opposite: that they use AI to review
applications and flag inconsistencies. One more reason not to inflate anything.
