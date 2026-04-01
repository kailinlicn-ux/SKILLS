from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from newsdata_client import ensure_newsdata_apikey, fetch_latest
from watchlist_parse import CompanyItem, build_query_candidates, parse_watchlist_list_output


def _configure_stdio_utf8() -> None:
    # Avoid Windows console encoding failures (e.g. cp936/gbk) when API text includes uncommon unicode.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


@dataclass(frozen=True)
class NewsItem:
    title: str | None
    source: str | None
    published_at: str | None
    url: str | None
    summary: str | None
    matched_query: str | None


def _to_iso(dt: Any) -> str | None:
    # newsdata.io usually returns strings; keep best-effort normalization.
    if dt is None:
        return None
    if isinstance(dt, str):
        s = dt.strip()
        return s or None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def normalize_newsdata_result(item: dict[str, Any], *, matched_query: str) -> NewsItem:
    # Field names are based on typical newsdata.io responses; if missing, keep None.
    title = item.get("title")
    link = item.get("link") or item.get("url")
    source = item.get("source_id") or item.get("source_name") or item.get("source")
    published_at = item.get("pubDate") or item.get("pub_date") or item.get("published_at")
    summary = item.get("description") or item.get("content")

    return NewsItem(
        title=title if isinstance(title, str) else None,
        source=source if isinstance(source, str) else None,
        published_at=_to_iso(published_at),
        url=link if isinstance(link, str) else None,
        summary=summary if isinstance(summary, str) else None,
        matched_query=matched_query,
    )


def dedupe_news(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []

    for it in items:
        if it.url:
            key = f"url:{it.url}"
        else:
            key = f"tps:{it.title}|{it.published_at}|{it.source}"
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def sort_news(items: list[NewsItem]) -> list[NewsItem]:
    # Best-effort: sort by published_at string desc (ISO-like sorts OK).
    return sorted(items, key=lambda x: (x.published_at or ""), reverse=True)


def search_company(
    company: CompanyItem, *, apikey: str, per_company_limit: int, per_query_limit: int
) -> tuple[list[NewsItem], list[dict[str, str]]]:
    collected: list[NewsItem] = []
    errors: list[dict[str, str]] = []
    for q in build_query_candidates(company):
        try:
            res = fetch_latest(q=q, apikey=apikey)
        except Exception as e:
            errors.append({"query": q, "error": str(e)})
            continue
        for raw in res.results[: max(0, per_query_limit)]:
            if isinstance(raw, dict):
                collected.append(normalize_newsdata_result(raw, matched_query=q))
        if per_company_limit and len(collected) >= per_company_limit:
            break

    collected = sort_news(dedupe_news(collected))
    if per_company_limit:
        collected = collected[:per_company_limit]
    return collected, errors


def _read_stdin_text() -> str:
    return sys.stdin.read()


def _read_multiline_from_tty() -> str:
    prompt = (
        "请粘贴 company-watchlist 的 list 输出，多行输入，单独一行输入 END 结束。\n"
        "示例: 1. [anthropic] Anthropic\n> "
    )
    sys.stderr.write(prompt)
    sys.stderr.flush()
    lines: list[str] = []
    tty_in = None
    try:
        if os.name == "nt":
            tty_in = open("CON", "r", encoding=sys.stdin.encoding or "utf-8", errors="replace")
        else:
            tty_in = open("/dev/tty", "r", encoding=sys.stdin.encoding or "utf-8", errors="replace")
        while True:
            line = tty_in.readline()
            if not line:
                break
            text = line.rstrip("\r\n")
            if text == "END":
                break
            lines.append(text)
    finally:
        if tty_in:
            tty_in.close()
    return "\n".join(lines)


def _default_csv_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "news_results.csv"


def append_news_to_csv(
    *,
    company_name: str,
    items: list[NewsItem],
    csv_path: Path,
    max_rows: int = 10,
) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = (not csv_path.exists()) or csv_path.stat().st_size == 0
    rows = items[: max(0, max_rows)]

    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["time", "company_name", "news_title", "news_link"])
        for it in rows:
            writer.writerow(
                [
                    it.published_at or datetime.now().isoformat(),
                    company_name,
                    it.title or "",
                    it.url or "",
                ]
            )
    return len(rows)


def main() -> None:
    _configure_stdio_utf8()

    ap = argparse.ArgumentParser(
        description="Consume company-watchlist list output from stdin, search foreign news via newsdata.io, output JSON."
    )
    ap.add_argument("--per-company", type=int, default=5, help="max news items per company")
    ap.add_argument("--per-query", type=int, default=10, help="max raw results consumed per query candidate")
    ap.add_argument("--json-only", action="store_true", help="only print JSON (no human summary)")
    ap.add_argument("--non-interactive", action="store_true", help="do not prompt for apikey (require env or saved)")
    ap.add_argument("--csv-path", default=str(_default_csv_path()), help="workspace csv path for persisted news rows")
    ap.add_argument("--csv-topn", type=int, default=10, help="max rows written to csv per company each run")
    ap.add_argument(
        "--input-text",
        default="",
        help="direct watchlist list text input; when set, no stdin/tty input is needed",
    )
    args = ap.parse_args()

    if args.input_text.strip():
        text = args.input_text
    elif not sys.stdin.isatty():
        text = _read_stdin_text()
    else:
        text = _read_multiline_from_tty()

    companies = parse_watchlist_list_output(text)
    if not companies:
        print(json.dumps({"items": [], "note": "empty watchlist"}, ensure_ascii=False, indent=2))
        return

    apikey = ensure_newsdata_apikey(interactive=not args.non_interactive)

    out: list[dict[str, Any]] = []
    csv_path = Path(args.csv_path)
    for c in companies:
        news, errors = search_company(
            c,
            apikey=apikey,
            per_company_limit=max(0, args.per_company),
            per_query_limit=max(0, args.per_query),
        )
        written = append_news_to_csv(
            company_name=c.name,
            items=news,
            csv_path=csv_path,
            max_rows=max(0, args.csv_topn),
        )
        out.append(
            {
                "company": {"id": c.id, "name": c.name, "aliases": list(c.aliases)},
                "region": "foreign",
                "items": [asdict(n) for n in news],
                "errors": errors,
                "csv_written": written,
            }
        )

    payload = {"items": out, "csv_path": str(csv_path)}
    if args.json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # Human-friendly summary to stderr, JSON to stdout
    for block in out:
        c = block["company"]
        items = block["items"]
        print(f"- {c['name']} [{c['id']}] 命中 {len(items)} 条", file=sys.stderr)
        for it in items[: min(3, len(items))]:
            print(f"  - {it.get('published_at') or ''} {it.get('title') or ''}", file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

