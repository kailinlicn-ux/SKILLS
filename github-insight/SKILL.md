---
name: github-insight
description: 通过仓库内脚本抓取 GitHub Trending 页面，按「stars today」排序输出仓库列表；在用户询问 GitHub 今日趋势、涨星最快、热门仓库或开展 GitHub 相关洞察时使用。实现位于 github-insight/scripts/，不依赖 pip 安装。
---

# GitHub Insight（Cursor Skill）

本 skill 约定如何调用仓库目录 `github-insight/` 下的脚本（代码不放在 `.cursor/skills/` 内，仅在此说明流程与命令）。

## 目标与边界

- **只做**：拉取 GitHub 官方 [Trending](https://github.com/trending) 页面 HTML，解析每条仓库的 **stars today**（页内展示值），并按该指标或页面顺序输出；可选 JSON 便于下游处理。
- **不会做**：不调用需密钥的 GitHub API 做全量「精确到 API 的逐日涨星统计」；不修改用户仓库内除本 skill 约定外的文件。
- **数据说明**：GitHub 未提供「全站按自然日涨星」的公开排序接口；**stars today** 以 Trending 页展示为准，与站内算法相关，不等同于自建历史快照的差分。

## 实现脚本（唯一入口）

```text
github-insight/scripts/github_trending.py
```

依赖：**仅 Python 标准库**（无需 `pip install`）。

## Agent 调用方式（优先）

1. **结构化输出（推荐）**：便于解析与摘要。

```bash
python github-insight/scripts/github_trending.py --json --since daily --sort stars_today
```

2. **人类可读表格**：

```bash
python github-insight/scripts/github_trending.py --since daily
```

3. **网络不稳定时**：可适当增大超时（秒）。

```bash
python github-insight/scripts/github_trending.py --json --timeout 120
```

## CLI 参数约定

| 参数 | 含义 |
|------|------|
| `--since` | `daily`（默认） / `weekly` / `monthly` |
| `--language` | 可选，对应 `https://github.com/trending/<lang>` 段，如 `python`、`typescript` |
| `--spoken-language-code` | 可选，如 `en` |
| `--sort` | `stars_today`（默认，按解析到的今日 stars 降序）或 `page_order`（保持 GitHub 页面顺序） |
| `--json` | 输出 JSON 数组，元素字段与脚本内 `TrendingRepo` 一致 |
| `--timeout` | HTTP 超时秒数，默认 30 |

## JSON 每条记录字段（`--json`）

- `full_name`：如 `owner/repo`
- `description`、`language`
- `stars_total`、`forks`、`stars_today`
- `url`：仓库 HTTPS 链接
- `rank_on_page`：在 Trending 页中出现的序号（解析顺序）

## 退出码

- `0`：成功
- `1`：HTTP 或网络错误
- `2`：成功拉取页面但未能解析出任何仓库（可能为 GitHub HTML 改版，需更新脚本解析逻辑）

## 向用户呈现结果时

- 注明数据来源为 **GitHub Trending** 与 **当日页内 stars today**，避免说成「官方 API 的全局涨星排名」。
- 若命令失败，提示检查网络、代理或提高 `--timeout`。
