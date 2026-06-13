# Bounty Signal Screener

Small CLI for filtering marketplace bounty pages against live GitHub state.

The first supported sources are the unitaryHACK bounty page plus Opire single
issue pages and embedded issue-card lists. The tool extracts GitHub issue links,
then checks:

- issue state,
- open pull requests mentioning the issue,
- assignee count,
- comment count,
- source-page solver or claim signals when available,
- recent maintainer or contributor signals.

This is meant to prevent stale marketplace pages from wasting implementation
time. It does not claim a bounty is winnable; it only separates "worth a closer
look" from "already solved, crowded, or stale".

## Quickstart

```sh
python3 -m bounty_signal_screener.cli \
  --source https://unitaryhack.dev/bounties/ \
  --json-out artifacts/unitaryhack.json \
    --markdown-out artifacts/unitaryhack.md
```

## RustChain Bounty Dashboard

The RustChain dashboard mode scans live open issues in
`Scottcjn/rustchain-bounties`, extracts posted RTC rewards, separates real
opportunities from claim/wallet/status issues, and tracks comments by a specific
GitHub actor so an agent can see pending versus paid RTC claims.

```sh
python3 -m bounty_signal_screener.cli \
  --rustchain-dashboard \
  --rustchain-actor boqiang \
  --rustchain-limit 120 \
  --json-out artifacts/rustchain-dashboard.json \
  --markdown-out artifacts/rustchain-dashboard.md
```

If the GitHub CLI is available and authenticated, the screener uses it for live
issue and PR state. Without `gh`, it still parses source-page candidates but
marks live verification as unavailable.

## Scores

`candidate` means the issue is open and no open PR was found by the configured
GitHub search. It still needs manual review.

`crowded` means the issue is open but already has an open PR, assignee, or high
comment count. For Opire pages, high solver or claim counts also mark an issue
as crowded because GitHub state alone can miss marketplace competition.

`stale` means the source page listed the issue, but GitHub currently shows it as
closed.

`unknown` means live verification failed.

## Validation

```sh
python3 -m unittest discover -s tests
python3 -m bounty_signal_screener.cli --source fixtures/sample_bounties.html
python3 -m bounty_signal_screener.cli --source https://app.opire.dev/issues/01J73BXYSGA83XKW25TPF2QMK0
```
