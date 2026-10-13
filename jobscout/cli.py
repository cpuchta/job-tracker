"""Command line entry point.

    python -m jobscout dedupe   --tracker tracker.json --candidates found.json
    python -m jobscout evaluate --profile config/profile.yaml --jobs verified.json [--markdown]

Both commands print JSON to stdout so the agent running the collector can read the
result back without parsing prose. ``--markdown`` prints a digest-ready table instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .dedupe import DedupeBase, split_new
from .rules import BLOCKED, MISSING, triage


def _load_json(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # Accept {"results": [...]} or {"rows": [...]} shaped exports.
        data = data.get("results") or data.get("rows") or []
    return data


def _link(job: dict) -> str:
    return job.get("company_link") or job.get("link") or ""


def to_markdown(result: dict) -> str:
    lines: list[str] = []

    def section(title: str, rows: list[dict], fmt) -> None:
        if not rows:
            return
        lines.append(f"## {title}\n")
        lines.extend(fmt(r) for r in rows)
        lines.append("")

    section(
        "Top this run",
        result["top"],
        lambda j: f"- **{j.get('company')}**, {j.get('title')}: {j['verdict']['pay_note']}. {_link(j)}",
    )
    section(
        "Almost made it",
        result["runner_up"],
        lambda j: f"- {j.get('company')}, {j.get('title')}. {_link(j)}",
    )
    section(
        "Missing data (your call)",
        result[MISSING],
        lambda j: f"- {j.get('company')}, {j.get('title')}: missing {', '.join(j['verdict']['missing'])}. {_link(j)}",
    )

    counts: dict[str, int] = {}
    for job in result[BLOCKED]:
        for reason in job["verdict"]["reasons"]:
            key = reason.split(" (")[0].split(":")[0]
            counts[key] = counts.get(key, 0) + 1
    if counts:
        lines.append("## Blocked\n")
        lines.extend(f"- {k}: {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
        lines.append("")

    return "\n".join(lines) if lines else "Nothing new passed the filter this run."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobscout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dedupe", help="drop candidates already in the tracker")
    d.add_argument("--tracker", required=True, help="tracker export, JSON list of rows")
    d.add_argument("--candidates", required=True, help="search results, JSON list")

    e = sub.add_parser("evaluate", help="apply fit rules and rank")
    e.add_argument("--profile", required=True, help="profile YAML")
    e.add_argument("--jobs", required=True, help="verified postings, JSON list")
    e.add_argument("--markdown", action="store_true", help="print a digest instead of JSON")

    args = parser.parse_args(argv)

    if args.cmd == "dedupe":
        base = DedupeBase.from_rows(_load_json(args.tracker))
        new, dupes = split_new(_load_json(args.candidates), base)
        json.dump({"new": new, "duplicates": dupes}, sys.stdout, indent=2, ensure_ascii=False)
    else:
        profile = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))
        result = triage(_load_json(args.jobs), profile)
        if args.markdown:
            print(to_markdown(result))
        else:
            json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
