from __future__ import annotations

import html
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .models import BountyLink


BOUNTY_LINK_RE = re.compile(
    r'<a[^>]+href="(https://github\.com/([^/]+/[^/]+)/issues/(\d+))"[^>]*>'
    r"\s*<span[^>]*>\$(\d+)</span>\s*<span[^>]*>(.*?)</span>",
    re.DOTALL,
)
GITHUB_ISSUE_RE = re.compile(r"https://github\.com/([^/\"'<>\s]+/[^/\"'<>\s]+)/issues/(\d+)")
OPIRE_BOUNTY_LINE_RE = re.compile(
    r"^#?\s*(?P<currency>[$])\s*(?P<amount>[0-9][0-9,]*(?:\.\d+)?)\s*(?:USD\s*)?bounty\s+for\s+(?P<title>.+)$",
    re.IGNORECASE,
)
OPIRE_META_TITLE_RE = re.compile(r'<meta[^>]+(?:property|name)="(?:og:title|twitter:title)"[^>]+content="([^"]+)"', re.IGNORECASE)
OPIRE_META_BOUNTY_RE = re.compile(r"^\$+\s*(?P<amount>[0-9][0-9,]*(?:\.\d+)?)\s+bounty:\s+(?P<title>.+)$", re.IGNORECASE)
SOURCE_CROWD_RE = re.compile(r"\b(?P<count>\d+)\s+(?P<label>solvers?|claims?|claimed)\b", re.IGNORECASE)
NEXT_FLIGHT_PUSH_RE = re.compile(r"self\.__next_f\.push\(\[1,\"(.*?)\"\]\)</script>", re.DOTALL)
OPIRE_CARD_RE = re.compile(
    r'{\"id\":\"(?P<id>01[A-Z0-9]+)\",\"title\":\"(?P<title>.*?)\",'
    r'\"url\":\"(?P<url>https://github\.com/[^\"]+/issues/\d+)\",\"platform\":\"GitHub\".*?'
    r'\"claimerUsers\":\[(?P<claimers>.*?)\],\"tryingUsers\":\[(?P<tryers>.*?)\],'
    r'\"programmingLanguages\":\[(?P<languages>.*?)\],\"createdAt\":\d+,'
    r'\"pendingPrice\":{\"value\":(?P<price>\d+),\"unit\":\"USD_CENT\"}',
    re.DOTALL,
)


def read_source(source: str) -> str:
    if source.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(source, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError:
            return subprocess.check_output(["curl", "--fail", "--location", "--silent", source], text=True, timeout=30)
    return Path(source).read_text(encoding="utf-8")


def visible_lines(source_html: str) -> list[str]:
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "\n", source_html)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html.unescape(text)
    return [" ".join(line.split()) for line in text.splitlines() if line.split()]


def decode_next_flight_text(source_html: str) -> str:
    chunks: list[str] = []
    for raw_chunk in NEXT_FLIGHT_PUSH_RE.findall(source_html):
        try:
            chunks.append(json.loads(f'"{raw_chunk}"'))
        except json.JSONDecodeError:
            continue
    return "".join(chunks)


def parse_opire_amount_title(source_html: str, lines: list[str]) -> tuple[int, str]:
    for line in lines:
        bounty_match = OPIRE_BOUNTY_LINE_RE.match(line)
        if not bounty_match:
            continue
        amount = round(float(bounty_match.group("amount").replace(",", "")))
        title = " ".join(bounty_match.group("title").split())
        return amount, title

    for meta_title in OPIRE_META_TITLE_RE.findall(source_html):
        value = html.unescape(meta_title).strip()
        bounty_match = OPIRE_META_BOUNTY_RE.match(value)
        if not bounty_match:
            continue
        amount = round(float(bounty_match.group("amount").replace(",", "")))
        title = " ".join(bounty_match.group("title").split())
        return amount, title

    return 0, ""


def opire_selected_issue_section(source_html: str) -> str:
    start = source_html.find("initialSelectedIssue")
    if start < 0:
        start = source_html.find('\\"initialSelectedIssue\\"')
    if start < 0:
        return ""
    end_positions = [pos for pos in (source_html.find("filters", start), source_html.find("homeKPIs", start)) if pos > start]
    end = min(end_positions) if end_positions else start + 50000
    return source_html[start:end]


def count_opire_user_array(section: str, field_name: str) -> int:
    match = re.search(rf'{field_name}\\":\[(.*?)\]', section, re.DOTALL)
    if not match:
        return 0
    return len(re.findall(r'\\"01[A-Z0-9]+\\"', match.group(1)))


def count_opire_user_objects(section: str) -> int:
    return section.count('"id":"01')


def parse_opire_issue_cards(source_html: str) -> list[BountyLink]:
    flight_text = decode_next_flight_text(source_html)
    if not flight_text:
        return []

    links: list[BountyLink] = []
    seen: set[tuple[str, int]] = set()
    for card_match in OPIRE_CARD_RE.finditer(flight_text):
        issue_match = GITHUB_ISSUE_RE.search(card_match.group("url"))
        if not issue_match:
            continue
        repo = issue_match.group(1)
        number = int(issue_match.group(2))
        key = (repo, number)
        if key in seen:
            continue
        seen.add(key)

        trying_count = count_opire_user_objects(card_match.group("tryers"))
        claiming_count = count_opire_user_objects(card_match.group("claimers"))
        source_notes = []
        if trying_count:
            source_notes.append(f"{trying_count} trying")
        if claiming_count:
            source_notes.append(f"{claiming_count} claiming")
        languages = tuple(re.findall(r'"([^"]+)"', card_match.group("languages")))
        if languages:
            source_notes.append(f"languages: {', '.join(languages)}")

        links.append(
            BountyLink(
                amount_usd=round(int(card_match.group("price")) / 100),
                title=html.unescape(card_match.group("title")),
                repo=repo,
                number=number,
                url=card_match.group("url"),
                source_notes=tuple(source_notes),
                source_crowd_count=trying_count + claiming_count,
            )
        )
    return links


def parse_opire_issue_page(source_html: str) -> list[BountyLink]:
    issue_match = GITHUB_ISSUE_RE.search(source_html)
    if not issue_match:
        return []

    lines = visible_lines(source_html)
    amount, title = parse_opire_amount_title(source_html, lines)

    if not title or amount <= 0:
        return []

    source_notes: list[str] = []
    source_crowd_count = 0
    selected_issue_section = opire_selected_issue_section(source_html)
    trying_count = count_opire_user_array(selected_issue_section, "usersTrying")
    claiming_count = count_opire_user_array(selected_issue_section, "usersClaiming")
    if trying_count:
        source_notes.append(f"{trying_count} trying")
        source_crowd_count += trying_count
    if claiming_count:
        source_notes.append(f"{claiming_count} claiming")
        source_crowd_count += claiming_count
    for line in lines:
        for crowd_match in SOURCE_CROWD_RE.finditer(line):
            count = int(crowd_match.group("count"))
            label = crowd_match.group("label").lower()
            source_crowd_count += count
            source_notes.append(f"{count} {label}")

    repo = issue_match.group(1)
    number = int(issue_match.group(2))
    return [
        BountyLink(
            amount_usd=amount,
            title=title,
            repo=repo,
            number=number,
            url=issue_match.group(0),
            source_notes=tuple(source_notes),
            source_crowd_count=source_crowd_count,
        )
    ]


def parse_bounty_links(source_html: str) -> list[BountyLink]:
    links: list[BountyLink] = []
    seen: set[tuple[str, int]] = set()
    for url, repo, number, amount, title_html in BOUNTY_LINK_RE.findall(source_html):
        title = html.unescape(re.sub("<[^<]+?>", "", title_html).strip())
        key = (repo, int(number))
        if key in seen:
            continue
        seen.add(key)
        links.append(
            BountyLink(
                amount_usd=int(amount),
                title=" ".join(title.split()),
                repo=repo,
                number=int(number),
                url=url,
            )
        )
    if links:
        return links
    links = parse_opire_issue_cards(source_html)
    if links:
        return links
    return parse_opire_issue_page(source_html)
