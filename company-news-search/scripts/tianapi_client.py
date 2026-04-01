from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TIANAPI_GUONEI_ENDPOINT = "https://apis.tianapi.com/guonei/index"


def _project_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "company-news-search.json"


def load_tianapi_key() -> str | None:
    p = _project_config_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    key = (data.get("tianapi") or {}).get("key")
    if isinstance(key, str) and key.strip():
        return key.strip()
    return None


def ensure_tianapi_key() -> str:
    key = load_tianapi_key()
    if key:
        return key
    raise RuntimeError(
        f"missing tianapi key; please set tianapi.key in {_project_config_path()}"
    )


@dataclass(frozen=True)
class TianapiGuoneiResult:
    raw: dict[str, Any]

    @property
    def code(self) -> int:
        value = self.raw.get("code")
        return value if isinstance(value, int) else -1

    @property
    def msg(self) -> str:
        value = self.raw.get("msg")
        return value if isinstance(value, str) else ""

    @property
    def list(self) -> list[dict[str, Any]]:
        result = self.raw.get("result")
        if not isinstance(result, dict):
            return []
        value = result.get("list")
        return value if isinstance(value, list) else []


def fetch_guonei_list(
    *,
    key: str,
    num: int = 10,
    page: int = 1,
    form: int = 1,
    rand: int = 1,
    word: str | None = None,
    timeout_s: int = 20,
) -> TianapiGuoneiResult:
    params: dict[str, Any] = {
        "key": key,
        "num": max(1, min(50, int(num))),
        "page": max(1, int(page)),
        "form": 1 if int(form) == 1 else 0,
        "rand": 1 if int(rand) == 1 else 0,
    }
    if word and word.strip():
        params["word"] = word.strip()

    url = f"{TIANAPI_GUONEI_ENDPOINT}?{urllib.parse.urlencode(params)}"
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
        raise RuntimeError("unexpected Tianapi response shape (not an object)")
    result = TianapiGuoneiResult(raw=data)
    if result.code != 200:
        raise RuntimeError(f"tianapi error {result.code}: {result.msg}")
    return result


def normalize_tianapi_item(item: dict[str, Any], *, matched_query: str | None = None) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "source": item.get("source"),
        "published_at": item.get("ctime"),
        "url": item.get("url"),
        "summary": item.get("description"),
        "matched_query": matched_query,
    }

