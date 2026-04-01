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

from tianapi_client import ensure_tianapi_key, fetch_guonei_list, normalize_tianapi_item
from watchlist_parse import CompanyItem, build_query_candidates, parse_watchlist_list_output


def _configure_stdio_utf8() -> None:
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


def normalize_tianapi_result(item: dict[str, Any], *, matched_query: str) -> NewsItem:
    n = normalize_tianapi_item(item, matched_query=matched_query)
    return NewsItem(
        title=n.get("title") if isinstance(n.get("title"), str) else None,
        source=n.get("source") if isinstance(n.get("source"), str) else None,
        published_at=n.get("published_at") if isinstance(n.get("published_at"), str) else None,
        url=n.get("url") if isinstance(n.get("url"), str) else None,
        summary=n.get("summary") if isinstance(n.get("summary"), str) else None,
        matched_query=n.get("matched_query") if isinstance(n.get("matched_query"), str) else None,
    )


def dedupe_news(items: Iterable[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in items:
        key = f"url:{it.url}" if it.url else f"tps:{it.title}|{it.published_at}|{it.source}"
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def sort_news(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(items, key=lambda x: (x.published_at or ""), reverse=True)


def search_company(
    company: CompanyItem, *, api_key: str, per_company_limit: int, per_query_limit: int, page: int
) -> tuple[list[NewsItem], list[dict[str, str]]]:
    collected: list[NewsItem] = []
    errors: list[dict[str, str]] = []
    for q in build_query_candidates(company):
        try:
            res = fetch_guonei_list(
                key=api_key, num=max(1, min(50, per_query_limit)), page=page, form=1, rand=1, word=q
            )
        except Exception as e:
            errors.append({"query": q, "error": str(e)})
            continue
        for raw in res.list[: max(0, per_query_limit)]:
            if isinstance(raw, dict):
                collected.append(normalize_tianapi_result(raw, matched_query=q))
        if per_company_limit and len(collected) >= per_company_limit:
            break

    collected = sort_news(dedupe_news(collected))
    # Keep latest 5 news items per company.
    collected = collected[:5]
    return collected, errors


def _read_stdin_text() -> str:
    return sys.stdin.read()


def _read_multiline_from_tty() -> str:
    prompt = (
        "请粘贴 company-watchlist 的 list 输出，多行输入，单独一行输入 END 结束。\n"
        "示例: 1. [alibaba] 阿里巴巴\n> "
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


def append_news_to_csv(*, company_name: str, items: list[NewsItem], csv_path: Path, max_rows: int = 10) -> int:
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
        description="Consume watchlist list text, search domestic news via Tianapi, output JSON and append CSV."
    )
    ap.add_argument("--per-company", type=int, default=5)
    ap.add_argument("--per-query", type=int, default=10)
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--csv-path", default=str(_default_csv_path()))
    ap.add_argument("--csv-topn", type=int, default=5)
    ap.add_argument("--input-text", default="")
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

    key = ensure_tianapi_key()
    out: list[dict[str, Any]] = []
    csv_path = Path(args.csv_path)
    for c in companies:
        news, errors = search_company(
            c,
            api_key=key,
            per_company_limit=max(0, args.per_company),
            per_query_limit=max(1, args.per_query),
            page=max(1, args.page),
        )
        written = append_news_to_csv(
            company_name=c.name,
            items=news,
            csv_path=csv_path,
            max_rows=5,
        )
        out.append(
            {
                "company": {"id": c.id, "name": c.name, "aliases": list(c.aliases)},
                "region": "domestic",
                "items": [asdict(n) for n in news],
                "errors": errors,
                "csv_written": written,
            }
        )

    payload = {"items": out, "csv_path": str(csv_path)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

