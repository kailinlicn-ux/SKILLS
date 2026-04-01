from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NEWS_DATA_LATEST_ENDPOINT = "https://newsdata.io/api/1/latest"
ENV_APIKEY = "NEWSDATA_APIKEY"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _user_config_path() -> Path:
    # Per-user secret storage; do NOT put API keys in repo files.
    return Path.home() / ".klinsight" / "company-news-search.json"


def _project_config_path() -> Path:
    # Optional local dev config (should be gitignored).
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
    env = os.environ.get(ENV_APIKEY)
    if env:
        return env.strip()

    apikey = _load_apikey_from_path(_project_config_path())
    if apikey:
        return apikey
    return _load_apikey_from_path(_user_config_path())


def save_newsdata_apikey(apikey: str) -> Path:
    apikey = apikey.strip()
    if not apikey:
        raise ValueError("apikey is empty")

    p = _user_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["updated_at"] = _utc_now_iso()
    data.setdefault("newsdata", {})
    data["newsdata"]["apikey"] = apikey

    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def ensure_newsdata_apikey(interactive: bool = True) -> str:
    apikey = load_newsdata_apikey()
    if apikey:
        return apikey

    if not interactive:
        raise RuntimeError(
            f"missing {ENV_APIKEY} and no apikey in {_project_config_path()} or {_user_config_path()}"
        )

    def _read_from_tty(prompt: str) -> str:
        """
        Read user input from the controlling terminal (not stdin),
        so it still works when stdin is a pipe.
        """
        sys.stderr.write(prompt)
        sys.stderr.flush()
        try:
            if os.name == "nt":
                with open("CON", "r", encoding=sys.stdin.encoding or "utf-8", errors="replace") as tty_in:
                    return (tty_in.readline() or "").rstrip("\r\n")
            with open("/dev/tty", "r", encoding=sys.stdin.encoding or "utf-8", errors="replace") as tty_in:
                return (tty_in.readline() or "").rstrip("\n")
        except Exception:
            # Fallback: may still fail if stdin is piped, but keeps behavior for interactive runs.
            return input().strip()

    # Ask the user once, then persist per-user.
    apikey = _read_from_tty(
        "请输入 newsdata.io 的 apikey（将保存到你的用户目录 ~/.klinsight/company-news-search.json，不会写入仓库）\n> "
    ).strip()
    if not apikey:
        raise RuntimeError("empty apikey")
    save_newsdata_apikey(apikey)
    return apikey


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

    params: dict[str, Any] = {"apikey": apikey, "q": q}
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

