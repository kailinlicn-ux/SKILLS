"""
Fetch OpenRouter rankings page and parse top models by token usage.

This script intentionally parses server-rendered HTML from openrouter.ai/rankings
because there is no documented public rankings JSON API in OpenRouter OpenAPI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_USER_AGENT = "KLinsight-OpenRouterInsight/1.0 (+https://openrouter.ai/)"
RANKINGS_BASE_URL = "https://openrouter.ai/rankings"

_TOKEN_SCALE = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "T": 1_000_000_000_000,
}


@dataclass(frozen=True)
class RankedModel:
    rank: int
    model_name: str
    model_id: str
    author: str
    tokens_text: str
    tokens_value: float
    delta_share_text: str
    url: str


def _parse_token_count(token_text: str) -> float:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMBT])\s*", token_text)
    if not m:
        raise ValueError(f"Invalid token text: {token_text!r}")
    num = float(m.group(1))
    unit = m.group(2)
    return num * _TOKEN_SCALE[unit]


def build_rankings_url(*, view: str = "day", category: str | None = None) -> str:
    view = view.strip().lower()
    if view not in ("day", "week", "month"):
        raise ValueError("view must be one of: day, week, month")

    path = RANKINGS_BASE_URL
    if category:
        seg = category.strip().strip("/")
        if seg:
            path = f"{path}/{urllib.parse.quote(seg)}"

    return f"{path}?{urllib.parse.urlencode({'view': view})}"


def fetch_html(url: str, *, timeout_s: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _extract_leaderboard_slice(html: str) -> str:
    anchor = html.find('id="leaderboard"')
    if anchor < 0:
        return html
    # Keep a large tail chunk to avoid cutting off rows when section ids are
    # duplicated in navigation markup.
    return html[anchor : anchor + 220_000]


def _parse_rankings_from_section(section: str) -> list[RankedModel]:
    link_pattern = re.compile(
        r'<a[^>]*class="[^"]*truncate[^"]*"[^>]*href="/(?P<model_id>[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9._:-]*)"[^>]*>(?P<model_name>[^<]+)</a>',
        flags=re.IGNORECASE,
    )
    token_pattern = re.compile(r"(?P<token>\d+(?:\.\d+)?[KMBT])(?:<!-- -->)?\s*tokens", flags=re.IGNORECASE)
    author_pattern = re.compile(
        r"by(?:<!-- -->)?\s*<a[^>]*href=\"/(?P<author>[a-z0-9][a-z0-9_-]*)\"",
        flags=re.IGNORECASE,
    )
    delta_pattern = re.compile(r"(?P<delta>\d+(?:\.\d+)?%)")

    out: list[RankedModel] = []
    seen_model_ids: set[str] = set()

    for match in link_pattern.finditer(section):
        model_id = match.group("model_id").strip()
        if model_id in seen_model_ids:
            continue

        model_name = re.sub(r"\s+", " ", match.group("model_name")).strip()
        window = section[match.end() : match.end() + 5000]

        token_m = token_pattern.search(window)
        if not token_m:
            continue
        token_text = token_m.group("token").upper()

        author = model_id.split("/", 1)[0]
        author_m = author_pattern.search(window)
        if author_m:
            author = author_m.group("author").strip()

        delta_share = ""
        delta_m = delta_pattern.search(window)
        if delta_m:
            delta_share = delta_m.group("delta")

        seen_model_ids.add(model_id)
        out.append(
            RankedModel(
                rank=0,  # filled after sorting
                model_name=model_name,
                model_id=model_id,
                author=author,
                tokens_text=f"{token_text} tokens",
                tokens_value=_parse_token_count(token_text),
                delta_share_text=delta_share,
                url=f"https://openrouter.ai/{model_id}",
            )
        )

    out.sort(key=lambda x: x.tokens_value, reverse=True)
    return [
        RankedModel(
            rank=i,
            model_name=m.model_name,
            model_id=m.model_id,
            author=m.author,
            tokens_text=m.tokens_text,
            tokens_value=m.tokens_value,
            delta_share_text=m.delta_share_text,
            url=m.url,
        )
        for i, m in enumerate(out, start=1)
    ]


def parse_rankings_html(html: str) -> list[RankedModel]:
    section = _extract_leaderboard_slice(html)
    parsed = _parse_rankings_from_section(section)
    if parsed:
        return parsed
    # Fallback: parse against full HTML in case anchor slicing misses rows.
    return _parse_rankings_from_section(html)


def run_cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Fetch OpenRouter rankings and list top models by token usage.",
    )
    p.add_argument(
        "--view",
        choices=("day", "week", "month"),
        default="day",
        help="Ranking window (default: day).",
    )
    p.add_argument(
        "--category",
        default=None,
        help="Optional rankings category path segment, e.g. roleplay.",
    )
    p.add_argument(
        "--top",
        type=int,
        default=10,
        help="How many entries to output (default: 10).",
    )
    p.add_argument("--json", action="store_true", help="Print JSON instead of plain text table.")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default: 30).")

    args = p.parse_args(argv)
    if args.top <= 0:
        print("--top must be > 0", file=sys.stderr)
        return 2

    url = build_rankings_url(view=args.view, category=args.category)
    try:
        html = fetch_html(url, timeout_s=args.timeout)
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code} fetching {url}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Network error fetching {url}: {e}", file=sys.stderr)
        return 1

    items = parse_rankings_html(html)
    if not items:
        print(
            "No models parsed from rankings page (OpenRouter HTML may have changed).",
            file=sys.stderr,
        )
        return 2

    items = items[: args.top]
    if args.json:
        payload: list[dict[str, Any]] = [asdict(x) for x in items]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Source: {url}\n")
    print("rank  tokens        model                               model_id")
    print("----  ------------  ----------------------------------  ------------------------------------------")
    for m in items:
        print(f"{m.rank:>4}  {m.tokens_text:<12}  {m.model_name:<34}  {m.model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
