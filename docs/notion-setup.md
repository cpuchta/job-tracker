# Tracker setup (Notion)

The collector writes to one Notion database. Any tracker your agent can read and write
works, but the prompt assumes Notion.

## Properties

| Property | Type | Values |
|---|---|---|
| Company | Title | |
| Role | Text | |
| Status | Select | To Apply, Applied, Interviewing, Offer, Rejected, On Hold, Invalid |
| Link | URL or Text | The company's own posting when it exists |
| Source | Select | ATS, LinkedIn, Aggregator, Referral, Other |
| Rounds | Number | Interview rounds so far |
| Last Update | Date | Date only |
| Notes | Text | Pay, eligibility, async signal, other links, caveats |

## Views

Create two views and copy their URLs into the prompt:

- **Review**: filter `Status is To Apply`. Phase 1 revalidates this view.
- **Full**: no filter. Phase 2 uses it as the dedupe base, so dead and rejected postings
  never come back as new.

## Connecting

1. Connect the Notion connector to your agent (in Claude: Settings, Connectors).
2. Share the database with the connection.
3. Get the data source id from the database URL or by asking the agent to search for it.

## Exporting for local dedupe

Ask the agent to save the full view as JSON with the keys `link`, `company`, `role`,
`notes`. That file is the `--tracker` input of `python -m jobscout dedupe`.
