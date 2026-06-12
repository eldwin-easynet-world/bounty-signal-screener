from __future__ import annotations

import json
from pathlib import Path

from .models import ScreenedBounty


def write_json_report(items: list[ScreenedBounty], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([item.to_jsonable() for item in items], indent=2, sort_keys=True) + "\n", encoding="utf-8")


def markdown_report(items: list[ScreenedBounty]) -> str:
    lines = [
        "# Bounty Signal Report",
        "",
        "| Status | Score | Amount | Repo | Issue | Title | Reason |",
        "| --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for item in items:
        title = item.bounty.title.replace("|", "\\|")
        reason = item.reason.replace("|", "\\|")
        lines.append(
            f"| {item.status} | {item.score} | ${item.bounty.amount_usd} | "
            f"{item.bounty.repo} | [#{item.bounty.number}]({item.bounty.url}) | {title} | {reason} |"
        )
    return "\n".join(lines) + "\n"


def write_markdown_report(items: list[ScreenedBounty], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_report(items), encoding="utf-8")
