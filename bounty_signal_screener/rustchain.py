from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RTC_REWARD_RE = re.compile(r"(?:(?P<low>\d+(?:\.\d+)?)\s*[–-]\s*(?P<high>\d+(?:\.\d+)?)|(?P<single>\d+(?:\.\d+)?))\s*RTC\b", re.IGNORECASE)
CLAIM_TITLE_RE = re.compile(r"(\[CLAIM\]|\[Bounty Claim\]|\[TOOL CLAIM\]|^RTC Claim|claim:|claim\b)", re.IGNORECASE)
NON_OPPORTUNITY_TITLE_RE = re.compile(r"(^\[WALLET\]|^Suggestion:|^Feature:)", re.IGNORECASE)
SELF_CLAIM_BODY_RE = re.compile(
    r"\b("
    r"I have (?:developed|created|implemented|built|open-sourced)|"
    r"I am requesting (?:a )?reward|"
    r"Claiming onboarding bounty|"
    r"RTC Wallet:|"
    r"Wallet:"
    r")\b",
    re.IGNORECASE,
)
PAID_RE = re.compile(r"\bpaid\b", re.IGNORECASE)
RECIPIENT_RE = re.compile(r"@([A-Za-z0-9-]+)")


@dataclass(frozen=True)
class RustChainIssue:
    number: int
    title: str
    url: str
    author: str
    updated_at: str
    reward_low_rtc: float | None
    reward_high_rtc: float | None
    is_claim: bool
    actor_comment_count: int
    maintainer_paid: bool
    tx_ids: tuple[str, ...]
    body_self_claim: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RustChainDashboard:
    repo: str
    actor: str
    scanned_count: int
    opportunities: list[RustChainIssue]
    actor_claims: list[RustChainIssue]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "actor": self.actor,
            "scanned_count": self.scanned_count,
            "potential_pending_rtc": sum(issue.reward_high_rtc or issue.reward_low_rtc or 0 for issue in self.actor_claims if not issue.maintainer_paid),
            "opportunities": [issue.to_jsonable() for issue in self.opportunities],
            "actor_claims": [issue.to_jsonable() for issue in self.actor_claims],
        }


@dataclass(frozen=True)
class RustChainPayout:
    issue_number: int
    issue_title: str
    issue_url: str
    recipient: str
    amount_rtc: float | None
    tx_ids: tuple[str, ...]
    paid_at: str
    comment_url: str

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RustChainPayoutSummary:
    repo: str
    hours: int
    scanned_count: int
    payouts: list[RustChainPayout]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "hours": self.hours,
            "scanned_count": self.scanned_count,
            "total_rtc": sum(payout.amount_rtc or 0 for payout in self.payouts),
            "payout_count": len(self.payouts),
            "payouts": [payout.to_jsonable() for payout in self.payouts],
        }


def _run_gh(args: list[str]) -> tuple[bool, Any]:
    env = os.environ.copy()
    env.setdefault("GH_CONFIG_DIR", "/Users/boqiang.liang/.config/gh-eldwin")
    try:
        output = subprocess.check_output(["gh", *args], text=True, stderr=subprocess.DEVNULL, env=env, timeout=30)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, {"error": exc.__class__.__name__}
    try:
        return True, json.loads(output)
    except json.JSONDecodeError:
        return False, {"error": "JSONDecodeError"}


def current_github_actor(default: str = "boqiang") -> str:
    ok, data = _run_gh(["api", "user"])
    if ok and isinstance(data, dict) and data.get("login"):
        return str(data["login"])
    return default


def parse_rtc_reward(text: str) -> tuple[float | None, float | None]:
    match = RTC_REWARD_RE.search(text)
    if not match:
        return None, None
    if match.group("single"):
        value = float(match.group("single"))
        return value, value
    low = float(match.group("low"))
    high = float(match.group("high"))
    return low, high


def is_claim_title(title: str) -> bool:
    return bool(CLAIM_TITLE_RE.search(title))


def is_non_opportunity_title(title: str) -> bool:
    return bool(NON_OPPORTUNITY_TITLE_RE.search(title))


def is_self_claim_body(body: str) -> bool:
    return bool(SELF_CLAIM_BODY_RE.search(body))


def extract_tx_ids(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(re.findall(r"\btx\s*`?([0-9a-f]{6,12})`?", text, re.IGNORECASE))))


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_paid_recipient(text: str) -> str:
    match = RECIPIENT_RE.search(text)
    return match.group(1) if match else "-"


def payout_from_comment(issue: dict[str, Any], comment: dict[str, Any], since: datetime) -> RustChainPayout | None:
    author = ((comment.get("author") or {}).get("login")) if isinstance(comment.get("author"), dict) else None
    body = str(comment.get("body") or "")
    if author != "Scottcjn" or not PAID_RE.search(body):
        return None
    tx_ids = extract_tx_ids(body)
    if not tx_ids:
        return None
    created_at = str(comment.get("createdAt") or "")
    paid_at = parse_iso_datetime(created_at)
    if paid_at is None or paid_at < since:
        return None
    amount_low, amount_high = parse_rtc_reward(body)
    amount = amount_high if amount_high is not None else amount_low
    return RustChainPayout(
        issue_number=int(issue["number"]),
        issue_title=str(issue.get("title") or ""),
        issue_url=str(issue.get("url") or ""),
        recipient=extract_paid_recipient(body),
        amount_rtc=amount,
        tx_ids=tx_ids,
        paid_at=created_at,
        comment_url=str(comment.get("url") or ""),
    )


def issue_from_gh(data: dict[str, Any], actor: str) -> RustChainIssue:
    title = str(data.get("title") or "")
    body = str(data.get("body") or "")
    comments = data.get("comments") or []
    reward_low, reward_high = parse_rtc_reward(title)
    if reward_low is None:
        reward_low, reward_high = parse_rtc_reward(body)
    actor_comment_count = 0
    maintainer_paid = False
    tx_ids: list[str] = []
    actor_lower = actor.lower()
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        author = ((comment.get("author") or {}).get("login")) if isinstance(comment.get("author"), dict) else None
        comment_body = str(comment.get("body") or "")
        if author == actor:
            actor_comment_count += 1
        if author == "Scottcjn" and "paid" in comment_body.lower() and actor_lower in comment_body.lower():
            maintainer_paid = True
            tx_ids.extend(extract_tx_ids(comment_body))
    author = data.get("author") or {}
    return RustChainIssue(
        number=int(data["number"]),
        title=title,
        url=str(data.get("url") or ""),
        author=str(author.get("login") or ""),
        updated_at=str(data.get("updatedAt") or ""),
        reward_low_rtc=reward_low,
        reward_high_rtc=reward_high,
        is_claim=is_claim_title(title),
        actor_comment_count=actor_comment_count,
        maintainer_paid=maintainer_paid,
        tx_ids=tuple(sorted(set(tx_ids))),
        body_self_claim=is_self_claim_body(body),
    )


def fetch_issue(repo: str, number: int, actor: str) -> RustChainIssue | None:
    ok, data = _run_gh([
        "issue",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        "number,title,url,author,updatedAt,body,comments",
    ])
    if not ok or not isinstance(data, dict):
        return None
    return issue_from_gh(data, actor)


def build_dashboard(repo: str = "Scottcjn/rustchain-bounties", actor: str | None = None, limit: int = 80) -> RustChainDashboard:
    actor = actor or current_github_actor()
    ok, data = _run_gh([
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number",
    ])
    if not ok or not isinstance(data, list):
        return RustChainDashboard(repo=repo, actor=actor, scanned_count=0, opportunities=[], actor_claims=[])

    issues: list[RustChainIssue] = []
    for item in data:
        if not isinstance(item, dict) or "number" not in item:
            continue
        issue = fetch_issue(repo, int(item["number"]), actor)
        if issue:
            issues.append(issue)

    opportunities = [
        issue for issue in issues
        if issue.reward_high_rtc is not None
        and not issue.is_claim
        and not is_non_opportunity_title(issue.title)
        and not issue.body_self_claim
        and parse_rtc_reward(issue.title)[0] is not None
        and issue.actor_comment_count == 0
    ]
    actor_claims = [
        issue for issue in issues
        if issue.actor_comment_count > 0
    ]
    opportunities.sort(key=lambda issue: (-(issue.reward_high_rtc or 0), issue.number))
    actor_claims.sort(key=lambda issue: (issue.maintainer_paid, -int(issue.updated_at[:4] or "0"), issue.number))
    return RustChainDashboard(repo=repo, actor=actor, scanned_count=len(issues), opportunities=opportunities, actor_claims=actor_claims)


def build_payout_summary(repo: str = "Scottcjn/rustchain-bounties", limit: int = 120, hours: int = 24) -> RustChainPayoutSummary:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    ok, data = _run_gh([
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--limit",
        str(limit),
        "--json",
        "number",
    ])
    if not ok or not isinstance(data, list):
        return RustChainPayoutSummary(repo=repo, hours=hours, scanned_count=0, payouts=[])

    payouts: list[RustChainPayout] = []
    scanned_count = 0
    for item in data:
        if not isinstance(item, dict) or "number" not in item:
            continue
        ok, issue = _run_gh([
            "issue",
            "view",
            str(item["number"]),
            "--repo",
            repo,
            "--json",
            "number,title,url,comments",
        ])
        if not ok or not isinstance(issue, dict):
            continue
        scanned_count += 1
        for comment in issue.get("comments") or []:
            if not isinstance(comment, dict):
                continue
            payout = payout_from_comment(issue, comment, since)
            if payout:
                payouts.append(payout)

    payouts.sort(key=lambda payout: payout.paid_at, reverse=True)
    return RustChainPayoutSummary(repo=repo, hours=hours, scanned_count=scanned_count, payouts=payouts)


def dashboard_markdown(dashboard: RustChainDashboard, top: int = 20) -> str:
    pending = sum(issue.reward_high_rtc or issue.reward_low_rtc or 0 for issue in dashboard.actor_claims if not issue.maintainer_paid)

    def cell(text: str) -> str:
        return text.replace("|", "\\|")

    lines = [
        "# RustChain Bounty Dashboard",
        "",
        f"- Repo: `{dashboard.repo}`",
        f"- Actor: `{dashboard.actor}`",
        f"- Open issues scanned: {dashboard.scanned_count}",
        f"- Potential pending RTC for actor: {pending:g}",
        "",
        "## Actor Claims",
        "",
        "| Status | RTC | Issue | Title | Tx |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for issue in dashboard.actor_claims[:top]:
        status = "paid" if issue.maintainer_paid else "pending"
        reward_value = issue.reward_high_rtc or issue.reward_low_rtc
        reward = f"{reward_value:g}" if reward_value is not None else "-"
        tx = ", ".join(issue.tx_ids) if issue.tx_ids else "-"
        lines.append(f"| {status} | {reward} | [#{issue.number}]({issue.url}) | {cell(issue.title)} | {tx} |")

    lines.extend([
        "",
        "## Open Opportunities",
        "",
        "| RTC | Issue | Title | Updated |",
        "| ---: | --- | --- | --- |",
    ])
    for issue in dashboard.opportunities[:top]:
        reward = issue.reward_high_rtc or issue.reward_low_rtc or 0
        lines.append(f"| {reward:g} | [#{issue.number}]({issue.url}) | {cell(issue.title)} | {issue.updated_at} |")
    return "\n".join(lines) + "\n"


def payout_summary_markdown(summary: RustChainPayoutSummary, top: int = 40) -> str:
    total = sum(payout.amount_rtc or 0 for payout in summary.payouts)

    def cell(text: str) -> str:
        return text.replace("|", "\\|")

    lines = [
        "# RustChain Daily Payout Summary",
        "",
        f"- Repo: `{summary.repo}`",
        f"- Window: last {summary.hours} hours",
        f"- Issues scanned: {summary.scanned_count}",
        f"- Paid comments found: {len(summary.payouts)}",
        f"- Total RTC mentioned: {total:g}",
        "",
        "| Paid At | RTC | Recipient | Issue | Tx |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for payout in summary.payouts[:top]:
        amount = payout.amount_rtc if payout.amount_rtc is not None else 0
        tx = ", ".join(payout.tx_ids)
        issue = f"[#{payout.issue_number}]({payout.issue_url}) {cell(payout.issue_title)}"
        lines.append(f"| {payout.paid_at} | {amount:g} | {cell(payout.recipient)} | {issue} | {tx} |")
    return "\n".join(lines) + "\n"


def write_dashboard_json(dashboard: RustChainDashboard, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard.to_jsonable(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_payout_summary_json(summary: RustChainPayoutSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.to_jsonable(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
