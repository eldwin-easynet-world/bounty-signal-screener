from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .github import fetch_github_state
from .models import BountyLink, GitHubState, ScreenedBounty


def classify(bounty: BountyLink, github: GitHubState) -> ScreenedBounty:
    if github.verification == "failed" or github.issue_state == "UNKNOWN":
        return ScreenedBounty(bounty, github, "unknown", 0, "live GitHub verification failed")

    if github.issue_state != "OPEN":
        return ScreenedBounty(bounty, github, "stale", -10, "source page listed a closed issue")

    if github.safety_flags:
        return ScreenedBounty(
            bounty,
            github,
            "unsafe",
            -20,
            f"issue asks for sensitive agent/session disclosure: {', '.join(github.safety_flags)}",
        )

    crowd_penalty = (
        bounty.source_crowd_count * 2
        + github.open_pr_count * 4
        + github.linked_pr_count * 4
        + github.assignees_count * 2
        + max(github.comments_count - 6, 0)
    )
    score = bounty.amount_usd - crowd_penalty

    if github.open_pr_count > 0:
        return ScreenedBounty(
            bounty,
            github,
            "crowded",
            score,
            f"{github.open_pr_count} open PR(s) already mention the issue",
        )

    if github.linked_pr_count > 0:
        return ScreenedBounty(
            bounty,
            github,
            "crowded",
            score,
            f"{github.linked_pr_count} PR link(s) found in issue comments",
        )

    if bounty.source_crowd_count >= 5:
        source_signal = ", ".join(bounty.source_notes) or f"{bounty.source_crowd_count} source crowd signal(s)"
        return ScreenedBounty(
            bounty,
            github,
            "crowded",
            score,
            f"source page reports {source_signal}",
        )

    if github.assignees_count > 0:
        return ScreenedBounty(bounty, github, "crowded", score, "issue already has assignee(s)")

    if github.comments_count > 12:
        return ScreenedBounty(bounty, github, "crowded", score, "issue discussion is already crowded")

    return ScreenedBounty(bounty, github, "candidate", score, "open issue with no open PR found")


def screen_bounties(
    bounties: list[BountyLink],
    max_items: int | None = None,
    workers: int = 8,
) -> list[ScreenedBounty]:
    items = bounties if max_items is None else bounties[:max_items]
    if workers <= 1:
        screened = [classify(bounty, fetch_github_state(bounty)) for bounty in items]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            screened = list(executor.map(lambda bounty: classify(bounty, fetch_github_state(bounty)), items))
    return sorted(screened, key=lambda item: (item.status != "candidate", -item.score, item.bounty.repo, item.bounty.number))
