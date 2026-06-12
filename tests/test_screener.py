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

OPIRE_HTML = """
<main>
  <h1># $390.00 bounty for Add Wayland support</h1>
  <a href="https://github.com/autokey/autokey/issues/87">Issue</a>
  <div>23 solvers</div>
  <div>11 claimed</div>
</main>
"""

OPIRE_NEXT_HTML = r"""
<head>
  <meta property="og:title" content="$390.00 bounty: Add Wayland support"/>
</head>
<script>self.__next_f.push([1,"initialSelectedIssue\":{\"issueURL\":\"https://github.com/autokey/autokey/issues/87\",\"title\":\"Add Wayland support\",\"usersTrying\":[\"01AAA\",\"01BBB\"],\"usersClaiming\":[\"01CCC\"]},\"filters\":{}"])</script>
"""

OPIRE_CARD_LIST_HTML = r"""
<script>self.__next_f.push([1,"bountyIssues:[{\"id\":\"01CARD\",\"title\":\"Tiny Rust fix\",\"url\":\"https://github.com/example/card/issues/9\",\"platform\":\"GitHub\",\"featuredBy\":null,\"claimerUsers\":[{\"id\":\"01CLAIM\",\"username\":\"c\"}],\"tryingUsers\":[{\"id\":\"01TRY1\",\"username\":\"t\"},{\"id\":\"01TRY2\",\"username\":\"u\"}],\"programmingLanguages\":[\"Rust\"],\"createdAt\":1,\"pendingPrice\":{\"value\":4200,\"unit\":\"USD_CENT\"},\"organization\":{\"name\":\"example\"}}]"])</script>
"""


class ScreenerTest(unittest.TestCase):
    def test_parse_bounty_links_deduplicates_issues(self) -> None:
        links = parse_bounty_links(SAMPLE_HTML)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].amount_usd, 100)
        self.assertEqual(links[0].repo, "example/project")
        self.assertEqual(links[0].number, 12)

    def test_parse_opire_issue_page_with_source_crowd_signals(self) -> None:
        links = parse_bounty_links(OPIRE_HTML)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].amount_usd, 390)
        self.assertEqual(links[0].repo, "autokey/autokey")
        self.assertEqual(links[0].number, 87)
        self.assertEqual(links[0].title, "Add Wayland support")
        self.assertEqual(links[0].source_crowd_count, 34)
        self.assertIn("23 solvers", links[0].source_notes)

    def test_parse_opire_next_embedded_data(self) -> None:
        links = parse_bounty_links(OPIRE_NEXT_HTML)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].amount_usd, 390)
        self.assertEqual(links[0].repo, "autokey/autokey")
        self.assertEqual(links[0].source_crowd_count, 3)
        self.assertIn("2 trying", links[0].source_notes)
        self.assertIn("1 claiming", links[0].source_notes)

    def test_parse_opire_embedded_issue_card_list(self) -> None:
        links = parse_bounty_links(OPIRE_CARD_LIST_HTML)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].amount_usd, 42)
        self.assertEqual(links[0].repo, "example/card")
        self.assertEqual(links[0].number, 9)
        self.assertEqual(links[0].title, "Tiny Rust fix")
        self.assertEqual(links[0].source_crowd_count, 3)
        self.assertIn("2 trying", links[0].source_notes)
        self.assertIn("1 claiming", links[0].source_notes)
        self.assertIn("languages: Rust", links[0].source_notes)

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

    def test_source_crowd_signals_mark_crowded(self) -> None:
        bounty = BountyLink(
            390,
            "Add Wayland support",
            "autokey/autokey",
            87,
            "https://github.com/autokey/autokey/issues/87",
            source_notes=("23 solvers", "11 claimed"),
            source_crowd_count=34,
        )
        github = GitHubState("OPEN", comments_count=2, assignees_count=0, open_pr_count=0, linked_pr_count=0, verification="live-gh", notes=[])
        result = classify(bounty, github)
        self.assertEqual(result.status, "crowded")
        self.assertIn("source page reports", result.reason)

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
