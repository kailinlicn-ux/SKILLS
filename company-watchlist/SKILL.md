---
name: company-watchlist
description: 仅维护本目录内公司观测列表 data/watchlist.json。当用户要查看、添加、删除、重命名观测公司或管理别名时使用；不涉及财报抓取、事件检索或网络搜索。
---

# 公司观测列表（Watchlist）

本技能**只做一件事**：维护本目录下 `data/watchlist.json` 中的观测公司列表。

## 数据文件

- 路径：`data/watchlist.json`（相对本目录 `company-watchlist/`）
- 字段：`version`、`updated_at`、`items[]`
- 每条：`id`（稳定键）、`name`（主显示名）、`aliases`（可选别名）
- 如果文件不存在则创建一个

## 命令行（可选）

在仓库根目录执行：

```bash
python company-watchlist/scripts/watchlist.py list
python company-watchlist/scripts/watchlist.py add "公司名称" --alias 别名A
python company-watchlist/scripts/watchlist.py remove --id <id>
python company-watchlist/scripts/watchlist.py remove --name <名称或别名>
python company-watchlist/scripts/watchlist.py rename "新名称" --id <id>
python company-watchlist/scripts/watchlist.py rename "新名称" --name <当前名或别名>
```

或先 `cd company-watchlist` 后使用 `python scripts/watchlist.py ...`。

## 对话中维护

用户要求增删查改时：

1. 读取 `company-watchlist/data/watchlist.json`（或本目录下 `data/watchlist.json`），必要时展示当前列表。
2. 按意图更新 JSON，或调用 `scripts/watchlist.py` 做等价变更；**保持 `id` 稳定**，除非用户明确要求删除后重建。
3. 写回后回复变更摘要与最新列表。

**不要**调用 WebSearch、WebFetch，不要运行与 watchlist 无关的脚本。

## 约束

- 不擅自批量清空或替换列表，除非用户明确要求。
- 本技能不提供投资建议。
