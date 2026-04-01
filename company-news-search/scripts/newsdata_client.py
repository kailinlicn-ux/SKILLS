from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NEWS_DATA_LATEST_ENDPOINT = "https://newsdata.io/api/1/latest"


def _project_config_path() -> Path:
    # Local workspace config for this project.
    return Path(__file__).resolve().parents[1] / "company-news-search.json"


def _load_apikey_from_path(p: Path) -> str | None:
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    apikey = (data.get("newsdata") or {}).get("apikey")
    if isinstance(apikey, str) and apikey.strip():
        return apikey.strip()
    return None


def load_newsdata_apikey() -> str | None:
    return _load_apikey_from_path(_project_config_path())


def ensure_newsdata_apikey(interactive: bool = True) -> str:
    _ = interactive  # kept for compatibility with existing call sites
    apikey = load_newsdata_apikey()
    if apikey:
        return apikey

    raise RuntimeError(
        f"missing newsdata apikey; please set newsdata.apikey in {_project_config_path()}"
    )


@dataclass(frozen=True)
class NewsDataResult:
    raw: dict[str, Any]

    @property
    def results(self) -> list[dict[str, Any]]:
        v = self.raw.get("results")
        return v if isinstance(v, list) else []


def fetch_latest(*, q: str, apikey: str, timeout_s: int = 20, **extra_params: Any) -> NewsDataResult:
    q = q.strip()
    if not q:
        raise ValueError("q is empty")

    params: dict[str, Any] = {"apikey": apikey, "qInTitle": q}
    for k, v in extra_params.items():
        if v is None:
            continue
        params[k] = v

    url = f"{NEWS_DATA_LATEST_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "KLinsight/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise RuntimeError("unexpected response shape (not an object)")
    return NewsDataResult(raw=data)

