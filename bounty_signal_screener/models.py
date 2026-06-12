from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BountyLink:
    amount_usd: int
    title: str
    repo: str
    number: int
    url: str
    source_notes: tuple[str, ...] = ()
    source_crowd_count: int = 0

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GitHubState:
    issue_state: str
    comments_count: int
    assignees_count: int
    open_pr_count: int
    linked_pr_count: int
    verification: str
    notes: list[str]
    safety_flags: tuple[str, ...] = ()

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScreenedBounty:
    bounty: BountyLink
    github: GitHubState
    status: str
    score: int
    reason: str

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["bounty"] = self.bounty.to_jsonable()
        data["github"] = self.github.to_jsonable()
        return data
