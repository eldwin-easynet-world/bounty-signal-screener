import unittest

from bounty_signal_screener.github import count_linked_pr_mentions
from bounty_signal_screener.models import BountyLink, GitHubState
from bounty_signal_screener.parser import parse_bounty_links
from bounty_signal_screener.report import markdown_report
from bounty_signal_screener.screen import classify, screen_bounties


SAMPLE_HTML = """
<li class="bounty-list__item bounty-list__item--open">
  <a class="bounty-link bounty-open" href="https://github.com/example/project/issues/12">
    <span class="bounty-link__value">$100</span>
    <span class="bounty-link__title">Add docs testing support</span>
  </a>
</li>
<li class="bounty-list__item bounty-list__item--open">
  <a class="bounty-link bounty-open" href="https://github.com/example/project/issues/12">
    <span class="bounty-link__value">$100</span>
    <span class="bounty-link__title">Add docs testing support</span>
  </a>
</li>
"""


class ScreenerTest(unittest.TestCase):
    def test_parse_bounty_links_deduplicates_issues(self) -> None:
        links = parse_bounty_links(SAMPLE_HTML)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].amount_usd, 100)
        self.assertEqual(links[0].repo, "example/project")
        self.assertEqual(links[0].number, 12)

    def test_candidate_requires_open_issue_and_no_pr(self) -> None:
        bounty = BountyLink(100, "Add docs testing support", "example/project", 12, "https://github.com/example/project/issues/12")
        github = GitHubState("OPEN", comments_count=2, assignees_count=0, open_pr_count=0, linked_pr_count=0, verification="live-gh", notes=[])
        result = classify(bounty, github)
        self.assertEqual(result.status, "candidate")
        self.assertGreater(result.score, 0)

    def test_closed_issue_is_stale(self) -> None:
        bounty = BountyLink(100, "Add docs testing support", "example/project", 12, "https://github.com/example/project/issues/12")
        github = GitHubState("CLOSED", comments_count=2, assignees_count=0, open_pr_count=0, linked_pr_count=0, verification="live-gh", notes=[])
        result = classify(bounty, github)
        self.assertEqual(result.status, "stale")

    def test_open_pr_marks_crowded(self) -> None:
        bounty = BountyLink(100, "Add docs testing support", "example/project", 12, "https://github.com/example/project/issues/12")
        github = GitHubState("OPEN", comments_count=2, assignees_count=0, open_pr_count=1, linked_pr_count=0, verification="live-gh", notes=[])
        result = classify(bounty, github)
        self.assertEqual(result.status, "crowded")

    def test_linked_pr_marks_crowded(self) -> None:
        bounty = BountyLink(100, "Add docs testing support", "example/project", 12, "https://github.com/example/project/issues/12")
        github = GitHubState("OPEN", comments_count=2, assignees_count=0, open_pr_count=0, linked_pr_count=1, verification="live-gh", notes=[])
        result = classify(bounty, github)
        self.assertEqual(result.status, "crowded")

    def test_markdown_report_contains_links(self) -> None:
        bounty = BountyLink(100, "Add docs testing support", "example/project", 12, "https://github.com/example/project/issues/12")
        github = GitHubState("OPEN", comments_count=2, assignees_count=0, open_pr_count=0, linked_pr_count=0, verification="live-gh", notes=[])
        report = markdown_report([classify(bounty, github)])
        self.assertIn("[#12](https://github.com/example/project/issues/12)", report)
        self.assertIn("candidate", report)

    def test_count_linked_pr_mentions(self) -> None:
        comments = [
            {"body": "Implemented in https://github.com/example/project/pull/99"},
            {"body": "Also see other/repo#12 and other/repo#12."},
        ]
        self.assertEqual(count_linked_pr_mentions(comments), 2)

    def test_screen_bounties_accepts_single_worker(self) -> None:
        links = parse_bounty_links(SAMPLE_HTML)
        # This path intentionally exercises the serial branch without depending on gh.
        result = screen_bounties(links[:0], workers=1)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
