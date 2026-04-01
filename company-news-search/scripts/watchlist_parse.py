from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyItem:
    id: str
    name: str
    aliases: tuple[str, ...] = ()


_LINE_RE = re.compile(
    r"^\s*\d+\.\s+\[(?P<id>[^\]]+)\]\s+(?P<name>.*?)(?:\s+别名:(?P<aliases>.*))?\s*$"
)


def parse_watchlist_list_output(text: str) -> list[CompanyItem]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return []
    if len(lines) == 1 and lines[0] == "（空）":
        return []

    out: list[CompanyItem] = []
    for ln in lines:
        m = _LINE_RE.match(ln)
        if not m:
            raise ValueError(f"cannot parse watchlist line: {ln!r}")
        iid = (m.group("id") or "").strip()
        name = (m.group("name") or "").strip()
        aliases_raw = (m.group("aliases") or "").strip()
        aliases: list[str] = []
        if aliases_raw:
            aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        out.append(CompanyItem(id=iid, name=name, aliases=tuple(aliases)))
    return out


def build_query_candidates(company: CompanyItem) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(q: str) -> None:
        q2 = (q or "").strip()
        if not q2:
            return
        key = q2.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(q2)

    add(company.name)
    for a in company.aliases:
        add(a)
    return out

