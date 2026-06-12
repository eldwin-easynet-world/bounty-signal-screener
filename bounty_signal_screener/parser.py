from __future__ import annotations

import html
import re
import urllib.request
from pathlib import Path

from .models import BountyLink


BOUNTY_LINK_RE = re.compile(
    r'<a[^>]+href="(https://github\.com/([^/]+/[^/]+)/issues/(\d+))"[^>]*>'
    r"\s*<span[^>]*>\$(\d+)</span>\s*<span[^>]*>(.*?)</span>",
    re.DOTALL,
)


def read_source(source: str) -> str:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as response:
            return response.read().decode("utf-8")
    return Path(source).read_text(encoding="utf-8")


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
    return links
