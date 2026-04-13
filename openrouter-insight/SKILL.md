---
name: openrouter-insight
description: 通过仓库内脚本抓取 OpenRouter Rankings 页面，解析并输出当日/当周/当月模型 token 用量排行；在用户询问 OpenRouter 热门模型、当日调用量最高模型或排行榜洞察时使用。实现位于 openrouter-insight/scripts/，不依赖 pip 安装。
---

# OpenRouter Insight（Cursor Skill）

本 skill 约定如何调用仓库目录 `openrouter-insight/` 下的脚本（代码不放在 `.cursor/skills/` 内，仅在此说明流程与命令）。

## 目标与边界

- **只做**：请求 OpenRouter Rankings 页面 HTML（如 `https://openrouter.ai/rankings?view=day`），解析模型条目的 `tokens`，并按 token 用量排序输出。
- **不会做**：不依赖未文档化的内部 JSON 接口；不调用需要密钥的 OpenRouter 私有能力；不修改用户仓库内除本 skill 约定外的文件。
- **数据说明**：结果以 OpenRouter 排行榜页面展示为准，属于页面解析数据，不等同于官方公开排行榜 API（当前公开 OpenAPI 未提供此接口）。

## 实现脚本（唯一入口）

```text
openrouter-insight/scripts/openrouter_rankings.py
```

依赖：**仅 Python 标准库**（无需 `pip install`）。

## Agent 调用方式（优先）

1. **结构化输出（推荐）**：便于摘要、排序和下游处理。

```bash
python openrouter-insight/scripts/openrouter_rankings.py --view day --top 10 --json
```

2. **直接获取当日第一名（调用量最大模型）**：

```bash
python openrouter-insight/scripts/openrouter_rankings.py --view day --top 1 --json
```

3. **人类可读表格输出**：

```bash
python openrouter-insight/scripts/openrouter_rankings.py --view day --top 10
```

4. **网络不稳定时**：可适当增大超时（秒）。

```bash
python openrouter-insight/scripts/openrouter_rankings.py --view day --json --timeout 120
```

## CLI 参数约定

| 参数 | 含义 |
|------|------|
| `--view` | `day`（默认）/ `week` / `month` |
| `--category` | 可选，排行榜分类路径段（例如 `roleplay`） |
| `--top` | 输出前 N 条，默认 `10` |
| `--json` | 输出 JSON 数组，元素字段与脚本内 `RankedModel` 一致 |
| `--timeout` | HTTP 超时秒数，默认 30 |

## JSON 每条记录字段（`--json`）

- `rank`：按 token 用量降序后的名次（1 开始）
- `model_name`：页面显示名
- `model_id`：`author/slug`，可直接拼接成 `https://openrouter.ai/<model_id>`
- `author`
- `tokens_text`：如 `183B tokens`
- `tokens_value`：换算后的数值（便于比较/二次计算）
- `delta_share_text`：页面上展示的变化百分比（若可解析）
- `url`：模型详情页链接

## 退出码

- `0`：成功
- `1`：HTTP 或网络错误
- `2`：参数不合法，或成功拉取页面但未解析出任何模型（可能为 OpenRouter HTML 改版，需更新脚本解析逻辑）

## 向用户呈现结果时

- 注明数据来源为 **OpenRouter Rankings 页面** 解析结果，避免表述成「官方排行榜 API 返回」。
- 若命令失败，提示检查网络、代理或提高 `--timeout`。
