# 数据字典

## 推荐阅读顺序

1. `report/DeepSeek套餐扩展实测报告.md`：人类可读结论、逐题表、图和边界。
2. `data/ANALYSIS_README.md`：统计单位、配对、bootstrap、成本与缺失值定义。
3. `data/QUANTITY_README.md`：同额度任务数模型及反事实边界。
4. `data/tables/README.md`：50 个 CSV 的行列数和入口。
5. `benchmark/PLAN.md`：冻结实验方案。
6. `benchmark/COLLECTOR_RECOVERY_ADDENDUM.md`：采集中断和行政恢复规则。

## 最终 JSON

| 文件 | 内容 |
|---|---|
| `data/analysis.json` | 最终统计、配对区间、逐题汇总、失败分类、并发和组合权重 |
| `data/quantity.json` | $100 同额度成本推算、配对数量比和统一价格重计价 |
| `data/tool-trajectory.json` | 12 个工具 episode 的工具调用、响应等待和测试前后轨迹 |
| `data/background-load.json` | 与本机 Magpie 可见后台调用的重叠聚合；不含提示或账号 |
| `data/external-load-observation.json` | 测试者报告的跨设备 OpenCode 负载及不可测量边界 |
| `data/historical-hour-profile.json` | 高低峰时段背景与解释限制 |
| `data/analysis-summary.txt` | 适合终端的紧凑结果摘要 |

## 主要 CSV

| 文件 | 单位 | 说明 |
|---|---|---|
| `request_records.csv` | 每次客户端终态请求 | provider、阶段、耗时、token、usage 已知性、路由与行政排除 |
| `request_counters.csv` | 请求内分类计数 | 每个 provider/阶段的失败、终止原因等分类 |
| `core_trials.csv` | 每个 high 代码题次 | 首答、修复、严格/去框结果、等待与 token |
| `core_pairs.csv` | 同一题的 Go/GOAT 配对 | 首答和最终工作流配对差异 |
| `core_tasks.csv` | provider × 合同 | 合同级宏平均与重复次数 |
| `low_core_trials.csv` | 每个 low 代码题次 | 补充思考档的同一组指标 |
| `context_trials.csv` | 长上下文组 × provider | 实际输入 token、完整 JSON、字段正确率和耗时 |
| `context_fields.csv` | 每组的九个字段 | 字段是否正确；字段相关，不是独立样本 |
| `tool_trials.csv` | 每个仓库 episode | 最终代码、完整流程、轮数、工具错误与截断 |
| `baseline_trials.csv` | 短任务请求 | 串行与标称并发的延迟分布 |
| `mix_grid.csv` | 15 个任务组合 | 代码/上下文/工具任务次数权重敏感性 |
| `mix_grid_auto_strip_counterfactual.csv` | 15 个反事实组合 | 假设客户端自动去框的效率，不是实测 |
| `quantity_workflow_cost_records.csv` | 每个 code workflow | 实测 token、缓存、价格时段和等值成本 |
| `quantity_paired_quantity_ratios.csv` | 匹配题次配对 | 同额度合格任务数的 GOAT/Go 比值与区间 |
| `administratively_*` | 行政排除/恢复记录 | 不把采集器中断或未知 usage 伪装成套餐结果 |

`data/tables/README.md` 给出全部 50 个 CSV 的实时行数、列数和文件大小。

## `analysis.json` 的常用入口

| 路径 | 说明 |
|---|---|
| `partial_data` | 必须为 `false` 才是最终队列 |
| `tables.core_trials` | high 的 72 行逐题次数据 |
| `tables.core_pairs` | 36 行同题配对 |
| `core.summary` | provider 级 high 宏平均 |
| `core.metrics` | 配对差、正确题延迟比、有效完成效率比及区间 |
| `core.secondary_metrics` | 事后去框与自动去框反事实 |
| `tables.low_core_trials` | low 的 48 行补充题次 |
| `context.summary` | 四档实际输入长度的表现与延迟 |
| `tools.summary` | 两个合成仓库的工具流程结果 |
| `requests.provider_totals` | 已知终端请求、完整载荷和未知 usage |
| `requests.raw_unreturned_attempts` | 中断原始 attempt；与行政恢复分开 |
| `workload_mix` | 任务次数组合的情景网格 |

## 原始文件

`benchmark/requests.jsonl` 是每个客户端终态请求一行；`attempt-journal.jsonl` 同时保存 started/terminal 事件。结果文件保留原始答案和评分。`benchmark/contracts/`、`contexts/`、`scenarios/` 保存冻结题库、提示、参考实现、负对照与验收逻辑。

`benchmark/audit/` 包含独立数学验收、合成恢复测试、账本检查、并发检查和工作簿复核。审计中的合成数字用于检验代码，不是模型性能观测。

