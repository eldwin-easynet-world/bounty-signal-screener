from __future__ import annotations

import json
import os
import re
import subprocess

from .models import BountyLink, GitHubState


LINKED_PULL_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/pull/\d+|[\w.-]+/[\w.-]+#\d+")


def _run_gh(args: list[str]) -> tuple[bool, object]:
    env = os.environ.copy()
    env.setdefault("GH_CONFIG_DIR", "/Users/boqiang.liang/.config/gh-eldwin")
    try:
        output = subprocess.check_output(["gh", *args], text=True, stderr=subprocess.DEVNULL, env=env, timeout=20)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, {"error": exc.__class__.__name__}
    try:
        return True, json.loads(output)
    except json.JSONDecodeError:
        return False, {"error": "JSONDecodeError"}


def fetch_github_state(bounty: BountyLink) -> GitHubState:
    issue_ok, issue_data = _run_gh(
        [
            "issue",
            "view",
            str(bounty.number),
            "--repo",
            bounty.repo,
            "--json",
            "state,comments,assignees",
        ]
    )
    if not issue_ok or not isinstance(issue_data, dict):
        return GitHubState(
            issue_state="UNKNOWN",
            comments_count=0,
            assignees_count=0,
            open_pr_count=0,
            linked_pr_count=0,
            verification="failed",
            notes=[str(issue_data)],
        )

    pr_ok, pr_data = _run_gh(
        [
            "pr",
            "list",
            "--repo",
            bounty.repo,
            "--state",
            "open",
            "--search",
            str(bounty.number),
            "--json",
            "number,title,url",
        ]
    )
    notes: list[str] = []
    if not pr_ok or not isinstance(pr_data, list):
        notes.append(f"open PR query failed: {pr_data}")
        pr_data = []

    linked_pr_count = count_linked_pr_mentions(issue_data.get("comments") or [])
    if linked_pr_count:
        notes.append(f"{linked_pr_count} PR link(s) mentioned in issue comments")

    return GitHubState(
        issue_state=str(issue_data.get("state", "UNKNOWN")),
        comments_count=len(issue_data.get("comments") or []),
        assignees_count=len(issue_data.get("assignees") or []),
        open_pr_count=len(pr_data),
        linked_pr_count=linked_pr_count,
        verification="live-gh",
        notes=notes,
    )


def count_linked_pr_mentions(comments: list[object]) -> int:
    links: set[str] = set()
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = str(comment.get("body") or "")
        for match in LINKED_PULL_RE.findall(body):
            links.add(match.rstrip(".,)"))
    return len(links)
