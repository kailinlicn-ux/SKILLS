"""
观测列表（watchlist）维护：增删查改，数据存于 data/watchlist.json。
无外部 API 依赖，仅读写本地 JSON。
"""
from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "watchlist.json"


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or f"item-{uuid.uuid4().hex[:8]}"


def load(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "updated_at": _utc_now(), "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cmd_list(path: Path) -> None:
    data = load(path)
    items = data.get("items", [])
    if not items:
        print("（空）")
        return
    for i, it in enumerate(items, 1):
        name = it.get("name", "")
        iid = it.get("id", "")
        aliases = it.get("aliases") or []
        extra = f" 别名:{','.join(aliases)}" if aliases else ""
        print(f"{i}. [{iid}] {name}{extra}")


def _find_index(items: list, by_id: str | None, by_name: str | None) -> int:
    if by_id:
        for j, it in enumerate(items):
            if it.get("id") == by_id:
                return j
    if by_name:
        t = by_name.strip().lower()
        for j, it in enumerate(items):
            if it.get("name", "").lower() == t:
                return j
            for a in it.get("aliases") or []:
                if a.lower() == t:
                    return j
    return -1


def cmd_add(path: Path, name: str, aliases: list[str]) -> None:
    data = load(path)
    items = data.setdefault("items", [])
    if _find_index(items, None, name) >= 0:
        raise SystemExit(f"已存在同名或别名: {name}")
    new_id = _slug(name)
    while _find_index(items, new_id, None) >= 0:
        new_id = f"{new_id}-{uuid.uuid4().hex[:4]}"
    items.append({"id": new_id, "name": name.strip(), "aliases": aliases})
    save(path, data)
    print(f"已添加: [{new_id}] {name.strip()}")


def cmd_remove(path: Path, by_id: str | None, by_name: str | None) -> None:
    data = load(path)
    items = data.setdefault("items", [])
    idx = _find_index(items, by_id, by_name)
    if idx < 0:
        raise SystemExit("未找到要删除的条目（可用 list 查看 id 与名称）")
    removed = items.pop(idx)
    save(path, data)
    print(f"已删除: [{removed.get('id')}] {removed.get('name')}")


def cmd_set_name(path: Path, by_id: str | None, old_name: str | None, new_name: str) -> None:
    data = load(path)
    items = data.setdefault("items", [])
    idx = _find_index(items, by_id, old_name)
    if idx < 0:
        raise SystemExit("未找到要修改的条目")
    items[idx]["name"] = new_name.strip()
    save(path, data)
    print(f"已更新名称: [{items[idx]['id']}] {new_name.strip()}")


def main() -> None:
    p = argparse.ArgumentParser(description="维护 data/watchlist.json")
    p.add_argument("--file", type=Path, default=DEFAULT_PATH, help="watchlist JSON 路径")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="列出全部")
    sp.set_defaults(func=lambda a: cmd_list(a.file))

    sp = sub.add_parser("add", help="添加一条")
    sp.add_argument("name", help="显示名称")
    sp.add_argument("--alias", action="append", default=[], help="别名，可重复")
    sp.set_defaults(func=lambda a: cmd_add(a.file, a.name, list(a.alias or [])))

    sp = sub.add_parser("remove", help="删除一条")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", dest="item_id", help="条目 id")
    g.add_argument("--name", help="名称或别名精确匹配")
    sp.set_defaults(func=lambda a: cmd_remove(a.file, a.item_id, a.name))

    sp = sub.add_parser("rename", help="修改显示名称")
    sp.add_argument("new_name", help="新名称")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", dest="item_id", help="条目 id")
    g.add_argument("--name", help="当前名称或别名")
    sp.set_defaults(func=lambda a: cmd_set_name(a.file, a.item_id, a.name, a.new_name))

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
