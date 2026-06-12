from __future__ import annotations

import argparse
from pathlib import Path

from .parser import parse_bounty_links, read_source
from .report import markdown_report, write_json_report, write_markdown_report
from .screen import screen_bounties


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Filter bounty pages against live GitHub state")
    parser.add_argument("--source", default="https://unitaryhack.dev/bounties/", help="Bounty page URL or local HTML file")
    parser.add_argument("--max-items", type=int, default=None, help="Optional cap for live GitHub checks")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent GitHub checks")
    parser.add_argument("--top", type=int, default=20, help="Rows to print in the terminal Markdown report")
    parser.add_argument(
        "--status",
        action="append",
        choices=["candidate", "crowded", "stale", "unknown", "unsafe"],
        help="Only include matching status; repeatable",
    )
    parser.add_argument("--json-out", default=None, help="Optional JSON report path")
    parser.add_argument("--markdown-out", default=None, help="Optional Markdown report path")
    return parser


def summary_line(parsed_count: int, screened_count: int, displayed_count: int, candidate_count: int) -> str:
    return (
        f"parsed={parsed_count} screened={screened_count} "
        f"displayed={displayed_count} candidates={candidate_count}"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    html = read_source(args.source)
    bounties = parse_bounty_links(html)
    screened = screen_bounties(bounties, max_items=args.max_items, workers=args.workers)
    if args.status:
        allowed = set(args.status)
        screened = [item for item in screened if item.status in allowed]

    if args.json_out:
        write_json_report(screened, Path(args.json_out))
    if args.markdown_out:
        write_markdown_report(screened, Path(args.markdown_out))

    displayed = screened[: max(args.top, 0)]
    print(markdown_report(displayed))
    print(
        summary_line(
            len(bounties),
            len(screened),
            len(displayed),
            sum(item.status == "candidate" for item in screened),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
