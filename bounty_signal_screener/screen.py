from __future__ import annotations

from .github import fetch_github_state
from .models import BountyLink, GitHubState, ScreenedBounty


def classify(bounty: BountyLink, github: GitHubState) -> ScreenedBounty:
    if github.verification == "failed" or github.issue_state == "UNKNOWN":
        return ScreenedBounty(bounty, github, "unknown", 0, "live GitHub verification failed")

    if github.issue_state != "OPEN":
        return ScreenedBounty(bounty, github, "stale", -10, "source page listed a closed issue")

    crowd_penalty = github.open_pr_count * 4 + github.assignees_count * 2 + max(github.comments_count - 6, 0)
    score = bounty.amount_usd - crowd_penalty

    if github.open_pr_count > 0:
        return ScreenedBounty(
            bounty,
            github,
            "crowded",
            score,
            f"{github.open_pr_count} open PR(s) already mention the issue",
        )

    if github.assignees_count > 0:
        return ScreenedBounty(bounty, github, "crowded", score, "issue already has assignee(s)")

    if github.comments_count > 12:
        return ScreenedBounty(bounty, github, "crowded", score, "issue discussion is already crowded")

    return ScreenedBounty(bounty, github, "candidate", score, "open issue with no open PR found")


def screen_bounties(bounties: list[BountyLink], max_items: int | None = None) -> list[ScreenedBounty]:
    items = bounties if max_items is None else bounties[:max_items]
    screened = [classify(bounty, fetch_github_state(bounty)) for bounty in items]
    return sorted(screened, key=lambda item: (item.status != "candidate", -item.score, item.bounty.repo, item.bounty.number))
