from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


JUHE_TOUTIAO_ENDPOINT = "http://v.juhe.cn/toutiao/index"


def _project_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "company-news-search.json"


def load_juhe_key() -> str | None:
    p = _project_config_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = (data.get("juhe") or {}).get("key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def ensure_juhe_key() -> str:
    key = load_juhe_key()
    if key:
        return key
    raise RuntimeError(
        f"missing juhe key; please set juhe.key in {_project_config_path()}"
    )


@dataclass(frozen=True)
class JuheToutiaoResult:
    raw: dict[str, Any]

    @property
    def error_code(self) -> int:
        value = self.raw.get("error_code")
        return value if isinstance(value, int) else -1

    @property
    def reason(self) -> str:
        value = self.raw.get("reason")
        return value if isinstance(value, str) else ""

    @property
    def data(self) -> list[dict[str, Any]]:
        result = self.raw.get("result")
        if not isinstance(result, dict):
            return []
        value = result.get("data")
        return value if isinstance(value, list) else []


def fetch_toutiao_list(
    *,
    key: str,
    type: str = "top",
    page: int = 1,
    page_size: int = 30,
    is_filter: int = 0,
    timeout_s: int = 20,
) -> JuheToutiaoResult:
    params = {
        "key": key,
        "type": type,
        "page": max(1, min(50, int(page))),
        "page_size": max(1, min(30, int(page_size))),
        "is_filter": 1 if int(is_filter) == 1 else 0,
    }
    url = f"{JUHE_TOUTIAO_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KLinsight/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    data = json.loads(body)
    if not isinstance(data, dict):
        raise RuntimeError("unexpected Juhe response shape (not an object)")
    result = JuheToutiaoResult(raw=data)
    if result.error_code != 0:
        raise RuntimeError(f"juhe error {result.error_code}: {result.reason}")
    return result


def normalize_juhe_item(item: dict[str, Any]) -> dict[str, Any]:
    # Normalize to the project's common shape.
    return {
        "title": item.get("title"),
        "source": item.get("author_name"),
        "published_at": item.get("date"),
        "url": item.get("url"),
        "summary": None,
        "matched_query": None,
    }

