---
name: company-news-search
description: 接收 company-watchlist 的 list 输出，统一调用 newsdata.io 搜索最新新闻；仅定义流程与输入输出约定，不在未知 API 细节时臆造实现。
---

# 公司新闻搜索（Company News Search）

本 skill 用于把 `company-watchlist` 的输出转化为“最新新闻检索任务”，并统一使用 `newsdata.io` 查询。

## 目标与边界

- **只做**：解析 watchlist 列表 → 为每家公司生成查询词 → 调用 `newsdata.io` → 聚合/去重/排序 → 输出结果。
- **不会做**：
  - 不在未知 API 细节时编造 URL、参数、鉴权方式、返回字段映射。
  - 不做投资建议。
  - 不修改 `company-watchlist/data/watchlist.json`（watchlist 维护由 `company-watchlist` skill 负责）。

## 命令行用法（国外新闻：newsdata.io）

国外新闻搜索已实现为脚本 `company-news-search/scripts/search_foreign_news.py`，默认以**交互方式等待用户输入**（不依赖管道）：

```bash
python company-news-search/scripts/search_foreign_news.py --per-company 5
```

运行后脚本会提示你粘贴 `company-watchlist list` 的输出，多行输入后以单独一行 `END` 结束。

如需在自动化场景下使用，仍可选择：

- 管道输入（可选）：`watchlist.py list | search_foreign_news.py ...`
- 参数输入（可选）：`--input-text "1. [anthropic] Anthropic"`

### CSV 持久化（工作空间）

- 默认会把每次查询结果写入：`company-news-search/data/news_results.csv`（追加模式）；若文件不存在则自动新建
- 每家公司保留并写入最新 5 条新闻
- CSV 字段：
  - `time`
  - `company_name`
  - `news_title`
  - `news_link`
- 可通过 `--csv-path` 指定其他工作空间内路径
- **写入前处理（强制）**：
  - 若 `news_title` 判定为英文，必须先翻译为中文，再写入 `news_title` 字段。
  - 若翻译失败，允许回退写入原标题，但应在日志/结果中明确记录该条“翻译失败”。

### apikey 获取与保存（每个用户不同）

- 仅从项目文件读取：`company-news-search/company-news-search.json`
- key 字段固定为：`newsdata.apikey`
- 用户也有可能直接给出`newsdata.apikey`，这种情况就直接把它写入`company-news-search.json`文件
- 若不存在或为空，脚本直接报错并提示你先填写该文件。

### Secrets 约定（给其他 AI agent 复用）

- 本 skill 统一使用项目文件：`company-news-search/company-news-search.json`
- newsdata 的 key 字段约定为：
  - `newsdata.apikey`
- 读取方式（必须遵守）：
  1. 仅读取 `company-news-search/company-news-search.json` 中的 `newsdata.apikey`
- 禁止把 apikey 写入其他仓库文件（如 `SKILL.md`、脚本源码、`data/*.json`、提交记录等）。

## 上游输入（来自 company-watchlist）

上游建议通过命令：

```bash
python company-watchlist/scripts/watchlist.py list
```

其输出为纯文本，可能是：

- 空列表：`（空）`
- 非空：每行一个条目，格式为：
  - `{序号}. [{id}] {name}`
  - 或 `{序号}. [{id}] {name} 别名:{alias1},{alias2},...`

本 skill 的第一步是把上述文本解析成结构化对象：

- `CompanyItem`
  - `id`: string
  - `name`: string
  - `aliases`: string[]

## 核心流程

1. **解析 watchlist 文本**
   - 忽略空行。
   - 若仅包含 `（空）`：直接返回“无公司需要搜索”的空结果。
   - 提取每行的 `id`、`name`、`aliases[]`（若无 `别名:` 则为空数组）。

2. **为每家公司生成查询词（query candidates）**
   - 默认候选顺序：
     1) `name`
     2) `aliases`（按原顺序追加）
   - 对候选进行去重（trim/大小写归一仅用于去重，不改变展示）。

3. **调用新闻 API**
   - 统一使用 `newsdata.io`
   - 查询参数使用标题关键词：`qInTitle`
   - 每家公司保留最新 5 条并写入 CSV

5. **聚合、去重与排序**
   - 将同一公司、不同 query 返回的新闻合并。
   - 去重优先级：
     1) `url`（若存在）
     2) 退化为 `(title + published_at + source)`
   - 按 `published_at` 倒序排序，截取每公司 Top-K（K 由实现配置）。

6. **输出**
   - 输出包含两部分（便于人读 + 便于机器用）：
     - 摘要：每公司命中数量与最新若干条标题/时间/来源
     - 结构化 JSON：用于后续流程串联

## 统一的新闻条目结构（标准化结果）

为屏蔽不同 API 的字段差异，内部统一使用：

- `NewsItem`
  - `title`: string
  - `source`: string | null
  - `published_at`: string | null  （建议统一为 ISO 8601 字符串）
  - `url`: string | null
  - `summary`: string | null
  - `matched_query`: string | null （记录命中使用的 query，便于解释与排错）

## 需要用户后续提供的信息（用于落地实现）

1. `newsdata.io` 的调用实现约定（鉴权、请求参数、返回字段、分页/limit、时间筛选、错误码、限流策略）。

