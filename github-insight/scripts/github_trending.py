"""
Fetch GitHub Trending and rank repos by "stars today" (shown on the trending page).

GitHub does not publish a public API for global daily star velocity. The official
Trending UI surfaces an approximate daily figure ("N stars today") per repo; this
script scrapes that page and sorts by that metric for insight workflows.

Docs: https://github.com/trending?since=daily
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


DEFAULT_USER_AGENT = "KLinsight-GitHubInsight/1.0 (+https://github.com/)"


@dataclass(frozen=True)
class TrendingRepo:
    full_name: str
    description: str
    language: str
    stars_total: int
    forks: int
    stars_today: int
    url: str
    rank_on_page: int


def _parse_int_loose(s: str) -> int:
    s = s.strip().replace(",", "")
    if not s:
        return 0
    lower = s.lower()
    if lower.endswith("k"):
        return int(float(lower[:-1]) * 1000)
    return int(float(s))


def _article_blocks(html: str) -> list[str]:
    # One Box-row article per trending repo
    pattern = re.compile(
        r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>',
        re.IGNORECASE | re.DOTALL,
    )
    return [m.group(1) for m in pattern.finditer(html)]


def _first_match(pattern: str, text: str) -> re.Match[str] | None:
    return re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)


def _parse_repo_block(block: str, rank: int) -> TrendingRepo | None:
    title = _first_match(
        r'<h2[^>]*class="[^"]*h3[^"]*"[^>]*>\s*<a[^>]+href="/((?:[^/]+)/(?:[^/]+))"',
        block,
    )
    if not title:
        title = _first_match(
            r'<h2[^>]*>\s*<a[^>]+href="/((?:[^/]+)/(?:[^/]+))"',
            block,
        )
    if not title:
        return None
    full_name = title.group(1).strip()

    desc_m = _first_match(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', block)
    description = ""
    if desc_m:
        description = re.sub(r"<[^>]+>", "", desc_m.group(1))
        description = re.sub(r"\s+", " ", description).strip()

    lang_m = _first_match(
        r'<span[^>]*itemprop="programmingLanguage"[^>]*>([^<]+)</span>',
        block,
    )
    language = lang_m.group(1).strip() if lang_m else ""

    stars_total = 0
    st_m = _first_match(
        rf'href="/{re.escape(full_name)}/stargazers"[^>]*>([^<]+)</a>',
        block,
    )
    if st_m:
        stars_total = _parse_int_loose(st_m.group(1))

    forks = 0
    fk_m = _first_match(
        rf'href="/{re.escape(full_name)}/network/members"[^>]*>([^<]+)</a>',
        block,
    )
    if not fk_m:
        fk_m = _first_match(
            rf'href="/{re.escape(full_name)}/forks"[^>]*>([^<]+)</a>',
            block,
        )
    if fk_m:
        forks = _parse_int_loose(fk_m.group(1))

    stars_today = 0
    today_m = _first_match(r"([\d,.]+[kK]?)\s+stars\s+today", block)
    if today_m:
        stars_today = _parse_int_loose(today_m.group(1))

    url = f"https://github.com/{full_name}"
    return TrendingRepo(
        full_name=full_name,
        description=description,
        language=language,
        stars_total=stars_total,
        forks=forks,
        stars_today=stars_today,
        url=url,
        rank_on_page=rank,
    )


def parse_trending_html(html: str) -> list[TrendingRepo]:
    blocks = _article_blocks(html)
    out: list[TrendingRepo] = []
    for i, block in enumerate(blocks, start=1):
        repo = _parse_repo_block(block, rank=i)
        if repo:
            out.append(repo)
    return out


def build_trending_url(
    *,
    since: str,
    language: str | None,
    spoken_language_code: str | None,
) -> str:
    since = since.strip().lower()
    if since not in ("daily", "weekly", "monthly"):
        raise ValueError("since must be one of: daily, weekly, monthly")

    path = "/trending"
    if language:
        seg = language.strip().strip("/")
        if seg:
            path += f"/{urllib.parse.quote(seg)}"

    q: dict[str, str] = {"since": since}
    if spoken_language_code:
        q["spoken_language_code"] = spoken_language_code.strip()

    return f"https://github.com{path}?{urllib.parse.urlencode(q)}"


def fetch_html(url: str, *, timeout_s: int = 30, user_agent: str = DEFAULT_USER_AGENT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def run_cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="List GitHub Trending repos, sorted by stars gained today (per trending page).",
    )
    p.add_argument(
        "--since",
        choices=("daily", "weekly", "monthly"),
        default="daily",
        help="Trending window (default: daily).",
    )
    p.add_argument(
        "--language",
        default=None,
        help="Optional GitHub language segment, e.g. python, typescript (see /trending/<lang>).",
    )
    p.add_argument(
        "--spoken-language-code",
        default=None,
        dest="spoken_language_code",
        metavar="CODE",
        help='Optional spoken language filter, e.g. en (maps to spoken_language_code=).',
    )
    p.add_argument(
        "--sort",
        choices=("stars_today", "page_order"),
        default="stars_today",
        help="Sort order (default: stars_today descending).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print JSON array instead of a plain table.",
    )
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default: 30).")

    args = p.parse_args(argv)

    url = build_trending_url(
        since=args.since,
        language=args.language,
        spoken_language_code=args.spoken_language_code,
    )

    try:
        html = fetch_html(url, timeout_s=args.timeout)
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code} fetching {url}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Network error fetching {url}: {e}", file=sys.stderr)
        return 1

    repos = parse_trending_html(html)
    if args.sort == "stars_today":
        repos = sorted(repos, key=lambda r: r.stars_today, reverse=True)

    if args.json:
        payload: list[dict[str, Any]] = [asdict(r) for r in repos]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Source: {url}\n")
    if not repos:
        print("No repositories parsed (GitHub HTML may have changed).", file=sys.stderr)
        return 2

    w = max(len(r.full_name) for r in repos)
    for r in repos:
        line = (
            f"{r.stars_today:>8}  today  |  {r.stars_total:>10}  stars  |  {r.full_name:<{w}}  |  {r.language}"
        )
        print(line)
        if r.description:
            print(f"{'':>8}         {r.description}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
