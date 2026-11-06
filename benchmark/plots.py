#!/usr/bin/env python3
"""Create seven standalone, publication-style PNG figures from analysis.json.

Run with the bundled local environment (no API/network/credential access):
  work/magpie-benchmark-v2/plot-env/bin/python \
    work/magpie-benchmark-v2/plots.py

The only user-facing outputs are the seven PNG files. Missing or pending trials
remain explicit, never zero-imputed. Candidate assertion counts are not treated
as independent observations. Partial output is visibly watermarked.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager, ticker
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT.parent.parent / "outputs" / "magpie-v2"
FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
PROVIDERS = ("go", "goat")
NAMES = {"go": "OpenCode Go", "goat": "Command GOAT"}
SHORT = {"go": "Go", "goat": "GOAT"}
BLUE = "#31688e"
ORANGE = "#cf7b2e"
COLORS = {"go": BLUE, "goat": ORANGE}
INK = "#263746"
MUTED = "#6f7d86"
GRID = "#dce3e8"
RED = "#aa4651"
SIZES = ("16K", "64K", "160K", "320K")
TASK_LABELS = {
    "sse_stream": "SSE 增量流解析",
    "ttl_lru": "TTL + LRU 缓存",
    "atomic_ledger": "原子账本 / 幂等",
    "interval_overlay": "区间覆盖 / 切分",
    "json_patch": "JSON Patch",
    "dependency_scheduler": "依赖调度",
    "csv_parser": "流式 CSV",
    "utf8_frames": "UTF-8 帧解析",
    "money_allocation": "精确金额分摊",
    "invoice_allocation": "发票优惠 / 税额",
    "invoice": "发票优惠 / 税额",
    "migration_plan": "数据库迁移计划",
    "shortest_route": "最短路 / 稳定择优",
    "record_conflicts": "批量记录冲突",
    "priority_schedule": "优先级 / 依赖调度",
    "path_glob": "路径 Glob 匹配",
    "interval_allocator": "区间分配 / 合并",
    "decimal_invoice": "精确发票 / 税额",
}
FIELD_LABELS = {
    "active_skus": "活跃 SKU 列表",
    "available_units": "可用件数",
    "available_value_cents": "可用总价值",
    "highest_value_sku": "最高价值 SKU",
    "over_reserved_skus": "超额预留列表",
    "owners": "所有者映射",
    "restock_needed": "补货总量",
    "most_recent_winner_seq": "最新胜出序号",
    "excluded_conflicting_event_ids": "冲突事件排除",
}
DATA_MAPPING = {
    "01-code-quality.png": ["tables.core_trials", "core.extraction_note"],
    "02-latency-distributions.png": ["tables.request_records", "tables.core_trials", "tables.baseline_trials", "tables.context_trials", "tables.tool_trials"],
    "03-paired-correct-latency.png": ["tables.core_trials", "core.metrics.first_correct_latency_ratio_goat_over_go", "core.metrics.workflow_correct_latency_ratio_goat_over_go"],
    "04-context-scaling.png": ["tables.context_trials", "tables.context_summaries", "tables.context_field_summaries"],
    "05-matched-concurrency.png": ["tables.baseline_trials", "tables.baseline_batches"],
    "06-workload-mix-sensitivity.png": ["tables.mix_grid", "tables.mix_strata", "workload_mix"],
    "07-effort-strata.png": ["tables.code_configurations", "tables.core_trials", "tables.low_core_trials", "effort_comparison"],
}


def configure():
    if not FONT.is_file():
        raise FileNotFoundError("Required CJK font is missing: " + str(FONT))
    font_manager.fontManager.addfont(str(FONT))
    family = font_manager.FontProperties(fname=str(FONT)).get_name()
    plt.rcParams.update({
        "font.family": family,
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "axes.edgecolor": "#b8c4cd",
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.unicode_minus": False,
        "grid.color": GRID,
        "grid.linewidth": 0.65,
        "legend.frameon": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def values(rows, key, positive=False):
    return [r[key] for r in rows if finite(r.get(key)) and (not positive or r[key] > 0)]


def avg(seq):
    seq = [v for v in seq if finite(v)]
    return sum(seq) / len(seq) if seq else None


def geom(seq):
    seq = [v for v in seq if finite(v) and v > 0]
    return math.exp(sum(math.log(v) for v in seq) / len(seq)) if seq else None


def fmt(value, digits=2):
    return (f"{value:.{digits}f}" if finite(value) else "—")


def rate(seq):
    known = [v for v in seq if v is not None]
    return (sum(v is True for v in known) / len(known), sum(v is True for v in known), len(known)) if known else (None, 0, 0)


def empty(ax, message="本阶段尚无终态数据"):
    ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)


def style(ax, axis="x"):
    ax.grid(True, axis=axis, zorder=0)
    ax.set_axisbelow(True)


def provider_handles():
    return [Patch(facecolor=COLORS[p], label=NAMES[p]) for p in PROVIDERS]


def outcome_handles():
    return [
        Line2D([], [], color=MUTED, marker="o", linestyle="", markersize=5, label="合格 / 完整"),
        Line2D([], [], color=MUTED, marker="x", linestyle="", markersize=6, label="失败 / 不完整"),
        Line2D([], [], color=INK, marker=">", markerfacecolor="none", linestyle="", markersize=7, label="截尾 / 截止值"),
    ]


def frame(fig, data, title, subtitle, source_hash):
    fig.suptitle(title, x=0.055, y=0.985, ha="left", fontsize=19, fontweight="bold")
    fig.text(0.055, 0.945, subtitle, ha="left", va="top", fontsize=11, color=MUTED)
    state = "部分数据 · 不作最终结论" if data.get("partial_data") else "完整 v2 数据"
    stamp = data.get("generated_at", "未记录生成时间")
    fig.text(0.055, 0.015, f"{state}  |  analysis.json {source_hash[:12]}  |  {stamp}", fontsize=8, color=MUTED)


def save(fig, out, filename, dpi, source_hash):
    path = out / filename
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.16, metadata={
        "Title": filename,
        "Description": "Data source: analysis.json SHA-256 " + source_hash + "; " + ", ".join(DATA_MAPPING[filename]),
        "Software": "Matplotlib; Magpie benchmark v2 standalone plot builder",
    })
    plt.close(fig)
    return path


def task_order(rows):
    # Frozen task IDs are read as optional metadata, never used to alter scores.
    known = {r.get("task_id") for r in rows if r.get("task_id")}
    path = ROOT / "core-tasks.json"
    if path.exists():
        try:
            ordered = [r["id"] for r in json.loads(path.read_text())]
            return ordered + sorted(known - set(ordered))
        except (ValueError, TypeError, KeyError):
            pass
    return sorted(known)


def figure_quality(data, out, dpi, source_hash):
    rows = data.get("tables", {}).get("core_trials", [])
    tasks = task_order(rows)
    fig, axes = plt.subplots(1, 4, figsize=(18.5, 10.0), sharey=True)
    frame(fig, data, "复杂代码：格式遵从与可执行语义分别计分",
          "12 个任务簇 × 每边 3 次；条形标签为合格 / 已判定次数，缺失保持未知。修复列保留原始一次修复策略。", source_hash)
    fields = [
        ("first_pass", "A  主评分 · 首次严格输出"),
        ("solved", "B  主评分 · 含一次修复"),
        ("first_after_conservative_extraction_pass", "C  次级 · 首次去围栏语义"),
        ("workflow_after_conservative_extraction_solved", "D  次级 · 含修复去围栏语义"),
    ]
    by = defaultdict(list)
    for r in rows:
        by[r.get("task_id"), r.get("provider")].append(r)
    y = np.arange(len(tasks))
    if not tasks:
        for ax in axes:
            empty(ax)
    for ax, (field, title) in zip(axes, fields):
        ax.set_title(title, loc="left", pad=15, fontsize=12)
        for pi, provider in enumerate(PROVIDERS):
            offset = -0.17 if pi == 0 else 0.17
            for index, task in enumerate(tasks):
                population = by[task, provider]
                relevant = [r for r in population if r.get("workflow_terminal")] if field in ("solved", "workflow_after_conservative_extraction_solved") else population
                fraction, passed, n = rate([r.get(field) for r in relevant])
                if fraction is not None:
                    ax.barh(index + offset, fraction * 100, height=0.28, color=COLORS[provider], alpha=.9, zorder=2)
                    xpos = max(3, fraction * 100 - 3) if fraction > .20 else fraction * 100 + 3
                    ax.text(xpos, index + offset, f"{passed}/{n}", va="center", ha="right" if fraction > .20 else "left",
                            color="white" if fraction > .20 else COLORS[provider], fontsize=9, fontweight="bold")
                else:
                    ax.text(2, index + offset, "未知", va="center", color=MUTED, fontsize=8)
        ax.set_xlim(0, 105)
        ax.set_xticks((0, 50, 100), ("0%", "50%", "100%"))
        ax.set_xlabel("完整任务通过率")
        ax.set_ylim(len(tasks) - .45, -.65)
        ax.set_yticks(y)
        ax.set_yticklabels([TASK_LABELS.get(task, task.replace("_", " ")) for task in tasks], fontsize=11)
        for separator in np.arange(.5, len(tasks), 1):
            ax.axhline(separator, color=GRID, lw=.6, zorder=0)
        style(ax)
    fig.legend(handles=provider_handles(), loc="upper right", bbox_to_anchor=(.985, .947), ncol=2)
    fig.text(.055, .066,
             "C / D 为观察 Markdown 格式问题后追加的次级分析：只去除一个完整代码围栏，不挑选多块代码；不改变主评分、修复反馈或主置信区间。\n"
             "各断言用于定位缺陷；589 条合约检查不构成 589 个独立样本。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.15, right=.985, top=.855, bottom=.14, wspace=.20)
    return save(fig, out, "01-code-quality.png", dpi, source_hash)


def marker_for(row, successful):
    censored = bool(row.get("censored") or row.get("deadline_hit"))
    if censored:
        return ">", COLORS[row["provider"]], "none"
    if successful is False:
        return "x", RED, RED
    return "o", COLORS[row["provider"]], COLORS[row["provider"]]


def point(ax, x, y, row, successful, size=28, alpha=.7):
    marker, edge, face = marker_for(row, successful)
    if marker == "x":
        ax.scatter(x, y, marker=marker, c=[COLORS[row["provider"]]], s=size + 5, linewidths=1.25, alpha=alpha, zorder=4)
    else:
        ax.scatter(x, y, marker=marker, edgecolors=edge, facecolors=face,
                   s=size + (8 if marker == ">" else 0), linewidths=.9, alpha=alpha, zorder=4)


def _distribution(ax, rows, key, groups, success_lookup=None):
    known = missing = failed = censored = 0
    ys = []
    labels = []
    for gi, (label, selected) in enumerate(groups):
        ys.append(gi)
        labels.append(label)
        for provider in PROVIDERS:
            population = [r for r in selected if r.get("provider") == provider]
            failed += sum((success_lookup(r) if success_lookup else bool(r.get("complete"))) is False for r in population)
            censored += sum(bool(r.get("censored") or r.get("deadline_hit")) for r in population)
            center = gi + (-.16 if provider == "go" else .16)
            usable = [r for r in population if finite(r.get(key)) and r[key] > 0]
            missing += len(population) - len(usable)
            xx = [r[key] for r in usable]
            if xx:
                known += len(xx)
                if len(xx) >= 4:
                    low, med, high = np.quantile(xx, [.25, .5, .75])
                    ax.plot([low, high], [center, center], color=COLORS[provider], lw=6, alpha=.18, solid_capstyle="round", zorder=2)
                    ax.plot([med, med], [center-.055, center+.055], color=COLORS[provider], lw=2, zorder=3)
                for index, r in enumerate(usable):
                    jitter = 0 if len(usable) == 1 else (((index * .61803398875) % 1) - .5) * .18
                    success = success_lookup(r) if success_lookup else bool(r.get("complete"))
                    point(ax, r[key], center + jitter, r, success, size=24, alpha=.62)
    ax.set_yticks(ys, labels, fontsize=10)
    ax.set_ylim(len(groups) - .50, -.5)
    if known:
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(ticker.LogLocator(base=10, subs=(1, 2, 5), numticks=8))
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:g}"))
        ax.xaxis.set_minor_formatter(ticker.NullFormatter())
        ax.set_xlabel("秒 · 对数刻度")
        style(ax)
    else:
        ax.text(.5, .5, "尚无可绘制耗时", transform=ax.transAxes, ha="center", color=MUTED)
        ax.set_xticks([])
    ax.text(0, -.29, f"已知 N={known}；缺失={missing}；失败={failed}；截尾={censored}",
            transform=ax.transAxes, fontsize=8.2, color=MUTED)


def figure_latency(data, out, dpi, source_hash):
    tables = data.get("tables", {})
    requests = tables.get("request_records", [])
    serial = [r for r in tables.get("baseline_trials", []) if r.get("phase") == "serial"]
    core = [r for r in requests if r.get("phase") in ("core_first", "core_repair")]
    context = tables.get("context_trials", [])
    tool_turns = [r for r in requests if str(r.get("phase", "")).startswith("tool")]
    tools = tables.get("tool_trials", [])
    grades = {}
    for r in tables.get("core_trials", []):
        grades[r.get("first_attempt_id")] = r.get("first_pass")
        if r.get("repair_attempt_id"):
            grades[r["repair_attempt_id"]] = r.get("repair_pass")
    fig, axes = plt.subplots(2, 4, figsize=(19.5, 10.8))
    frame(fig, data, "等待时间分布：分别观察首个可见输出与完整返回",
          "四个工作负载分别绘制，横轴范围各自独立；每点是一条请求，工具总耗时列每点是一轮仓库 episode。", source_hash)
    definitions = [
        ("A  固定输出 · 串行基线", serial, [("串行请求", serial)], lambda r: bool(r.get("fixture_pass"))),
        ("B  复杂代码 · 首答与修复请求", core, [("首答", [r for r in core if r.get("phase") == "core_first"]),
                                                        ("修复", [r for r in core if r.get("phase") == "core_repair"])], lambda r: grades.get(r.get("attempt_id"))),
        ("C  长上下文 · 分计划长度", context, [(s, [r for r in context if r.get("size_label") == s]) for s in SIZES], lambda r: bool(r.get("full_json_pass"))),
        ("D  仓库工具 · 按测量单位标注", tool_turns, [("模型调用 / turn", tool_turns)], lambda r: bool(r.get("complete"))),
    ]
    for col, (title, population, groups, success) in enumerate(definitions):
        axes[0, col].set_title(title, fontsize=11, loc="left", pad=12)
        _distribution(axes[0, col], population, "first_visible_seconds", groups, success)
        if col == 3:
            _distribution(axes[1, col], tools, "total_seconds", [("完整 episode", tools)], lambda r: bool(r.get("episode_success")))
        else:
            _distribution(axes[1, col], population, "total_seconds", groups, success)
    axes[0, 0].set_ylabel("首个文本 / 工具调用可见")
    axes[1, 0].set_ylabel("总耗时")
    fig.legend(handles=provider_handles() + outcome_handles(), loc="upper center", bbox_to_anchor=(.53, .910), ncol=5, fontsize=9)
    fig.text(.055, .060,
             "小点保留所有有测量值的终态样本；宽线为四分位距，细线为中位数（N≥4）。失败包含严格语义失败或协议不完整。\n"
             "缺失首个可见输出不作 0 秒处理。工具 episode 为各模型调用耗时之和，未含本地工具/判题器时间；它与单请求总耗时单位不同。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.085, right=.985, top=.845, bottom=.17, hspace=.64, wspace=.42)
    return save(fig, out, "02-latency-distributions.png", dpi, source_hash)


def _core_pairs(rows):
    lookup = defaultdict(dict)
    for row in rows:
        lookup[row.get("trial_id")][row.get("provider")] = row
    return [v for k, v in sorted(lookup.items()) if all(p in v for p in PROVIDERS)]


def figure_ratios(data, out, dpi, source_hash):
    trials = data.get("tables", {}).get("core_trials", [])
    tasks = task_order(trials)
    pairs = _core_pairs(trials)
    metrics = data.get("core", {}).get("metrics", {})
    fig, axes = plt.subplots(1, 2, figsize=(15.6, 10.0), sharey=True)
    frame(fig, data, "配对合格耗时：每道题都展示重复试验，避免单题支配",
          "比值 = Command GOAT 秒数 ÷ OpenCode Go 秒数；>1 表示 Go 更快。仅纳入双方均通过主评分的同一题次。", source_hash)
    specs = [
        ("first_pass", "first_seconds", "first_correct_latency_ratio_goat_over_go", "A  首次严格合格"),
        ("solved", "workflow_seconds", "workflow_correct_latency_ratio_goat_over_go", "B  工作流严格解出 · 含失败首答与修复耗时"),
    ]
    all_ratios = []
    for ax, (criterion, clock, metric_key, title) in zip(axes, specs):
        ax.set_title(title, loc="left", fontsize=12, pad=14)
        for index, task in enumerate(tasks):
            matching = [p for p in pairs if p["go"].get("task_id") == task]
            eligible = [p for p in matching if all(p[provider].get(criterion) is True and finite(p[provider].get(clock)) and p[provider][clock] > 0 for provider in PROVIDERS)]
            ratios = [p["goat"][clock] / p["go"][clock] for p in eligible]
            all_ratios.extend(ratios)
            for j, value in enumerate(ratios):
                jitter = (j - (len(ratios) - 1) / 2) * .12
                ax.scatter(value, index + jitter, color=BLUE if value >= 1 else ORANGE, s=34, alpha=.7, zorder=3)
            center = geom(ratios)
            if center is not None:
                ax.scatter(center, index, marker="D", c=INK, s=32, edgecolor="white", linewidth=.5, zorder=4)
            else:
                ax.text(.02, index, "无双方合格配对", transform=ax.get_yaxis_transform(), fontsize=8.5, color=MUTED, va="center")
            ax.text(.99, index, f"{len(ratios)}/{len(matching)} 对", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=8.5, color=MUTED)
        metric = metrics.get(metric_key, {})
        estimate, lo, hi = metric.get("estimate"), metric.get("ci_low"), metric.get("ci_high")
        overall_y = len(tasks) + .35
        if finite(estimate) and estimate > 0:
            all_ratios.append(estimate)
            if finite(lo) and finite(hi) and lo > 0:
                ax.plot([lo, hi], [overall_y, overall_y], color=INK, lw=2.4, zorder=4)
                all_ratios.extend([lo, hi])
            ax.scatter(estimate, overall_y, marker="D", c=INK, s=65, zorder=5)
            ci = f"{estimate:.2f} [{lo:.2f}, {hi:.2f}]" if finite(lo) and finite(hi) else f"{estimate:.2f}，CI 不可用"
            ax.text(.01, -.09, ci + f"；任务簇 N={metric.get('n_clusters', 0)}", transform=ax.transAxes, fontsize=10, color=INK)
        else:
            ax.text(.01, -.09, "整体配对比值 / CI 尚不可用", transform=ax.transAxes, fontsize=10, color=MUTED)
        ax.axvline(1, color=MUTED, lw=1.2, linestyle="--", zorder=1)
        ax.axhline(len(tasks) - .25, color=GRID, lw=1)
        ax.set_xscale("log", base=2)
        ax.set_xlabel("GOAT / Go 合格耗时比 · 对数刻度")
        ax.set_yticks(list(range(len(tasks))) + [overall_y], [TASK_LABELS.get(t, t.replace("_", " ")) for t in tasks] + ["任务宏平均 + 95% CI"])
        ax.set_ylim(len(tasks) + 1.0, -.7)
        style(ax)
    lower = min([.5] + all_ratios) / 1.2
    upper = max([2.0] + all_ratios) * 1.3
    for ax in axes:
        ax.set_xlim(lower, upper)
        ax.xaxis.set_major_locator(ticker.LogLocator(base=2, subs=(1,), numticks=8))
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:g}×"))
        ax.xaxis.set_minor_formatter(ticker.NullFormatter())
    legend = [Line2D([], [], color=BLUE, marker="o", linestyle="", label="重复试验：Go 更快"),
              Line2D([], [], color=ORANGE, marker="o", linestyle="", label="重复试验：GOAT 更快"),
              Line2D([], [], color=INK, marker="D", linestyle="", label="题内几何平均 / 整体任务宏平均")]
    fig.legend(handles=legend, loc="upper right", bbox_to_anchor=(.98, .914), ncol=3, fontsize=9)
    fig.text(.055, .058,
             "整体区间按任务簇重采样，题内重复保留；不把断言或同题重复当作独立任务。括号为探索性 95% bootstrap 区间。\n"
             "此图以双方成功为条件，会排除失败与单方成功；必须与质量图及包含失败耗时的任务组合图一起阅读。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.18, right=.98, top=.85, bottom=.20, wspace=.20)
    return save(fig, out, "03-paired-correct-latency.png", dpi, source_hash)


def figure_context(data, out, dpi, source_hash):
    tables = data.get("tables", {})
    rows = tables.get("context_trials", [])
    summaries = tables.get("context_summaries", [])
    field_summaries = tables.get("context_field_summaries", [])
    fig, axes = plt.subplots(2, 2, figsize=(16.0, 12.0))
    frame(fig, data, "长上下文：计划标签、实际 token、整答正确率与耗时",
          "4 个预定长度 × 每长 3 个种子 × 两套餐；长度标签按冻结设计保留，实际 usage 才是输入 token 的权威值。", source_hash)
    a, b, c, d = axes.flat
    a.set_title("A  计划字符估算 vs 实际输入 token", loc="left")
    known_token_rows = [r for r in rows if finite(r.get("estimated_tokens")) and finite(r.get("input_tokens")) and r["estimated_tokens"] > 0 and r["input_tokens"] > 0]
    if known_token_rows:
        for provider in PROVIDERS:
            pop = [r for r in known_token_rows if r.get("provider") == provider]
            a.scatter([r["estimated_tokens"] / 1000 for r in pop], [r["input_tokens"] / 1000 for r in pop],
                      marker="o" if provider == "go" else "s", color=COLORS[provider], alpha=.72, s=45, label=NAMES[provider])
        all_values = [r[k] / 1000 for r in known_token_rows for k in ("estimated_tokens", "input_tokens")]
        low, high = min(all_values) * .72, max(all_values) * 1.35
        a.plot([low, high], [low, high], linestyle="--", color=MUTED, lw=1, label="1:1 参考线")
        a.set_xscale("log")
        a.set_yscale("log")
        a.set_xlim(low, high)
        a.set_ylim(low, high)
        for axis in (a.xaxis, a.yaxis):
            axis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:g}"))
        a.legend(fontsize=9, loc="upper left")
        style(a, "both")
    else:
        empty(a)
    a.set_xlabel("计划字符数 / 4，千 token（估算）")
    a.set_ylabel("实际输入，千 token（usage）")
    a.text(.01, -.20, f"可配对 usage N={len(known_token_rows)}；其余={len(rows)-len(known_token_rows)}。", transform=a.transAxes, fontsize=9, color=MUTED)

    b.set_title("B  整个 JSON 正确 vs 字段诊断", loc="left")
    summary_lookup = {(r.get("size_label"), r.get("provider")): r for r in summaries}
    for provider in PROVIDERS:
        full = [summary_lookup.get((s, provider), {}).get("full_json_pass_rate") for s in SIZES]
        fields = [summary_lookup.get((s, provider), {}).get("complete_field_pass_rate") for s in SIZES]
        b.plot(range(4), [np.nan if v is None else v * 100 for v in full], "o-", color=COLORS[provider], lw=2, label=SHORT[provider] + " 整答")
        b.plot(range(4), [np.nan if v is None else v * 100 for v in fields], "s--", color=COLORS[provider], alpha=.8, label=SHORT[provider] + " 字段诊断")
    xlabels = [s + "\nN=" + "/".join(str(summary_lookup.get((s, p), {}).get("n_datasets", 0)) for p in PROVIDERS) for s in SIZES]
    b.set_xticks(range(4), xlabels)
    b.set_ylabel("正确率（%）")
    b.set_ylim(-4, 106)
    b.set_yticks((0, 25, 50, 75, 100))
    b.set_xlabel("冻结计划长度；N 顺序为 Go / GOAT")
    b.legend(ncol=2, fontsize=9, loc="lower left")
    style(b, "y")

    c.set_title("C  每个种子的首个可见与总耗时", loc="left")
    has_time = False
    missing_times = 0
    for si, size in enumerate(SIZES):
        for pi, provider in enumerate(PROVIDERS):
            pop = sorted([r for r in rows if r.get("size_label") == size and r.get("provider") == provider], key=lambda r: str(r.get("seed")))
            total = values(pop, "total_seconds", positive=True)
            if total:
                median = float(np.median(total))
                c.plot([si + (-.14 if pi == 0 else .14) - .07, si + (-.14 if pi == 0 else .14) + .07], [median, median], color=COLORS[provider], lw=2.3)
            for ri, row in enumerate(pop):
                x = si + (-.14 if pi == 0 else .14) + (ri - (len(pop) - 1) / 2) * .045
                tv, fv = row.get("total_seconds"), row.get("first_visible_seconds")
                if finite(tv) and tv > 0:
                    has_time = True
                    point(c, x, tv, row, bool(row.get("full_json_pass")), size=34)
                    if finite(fv) and fv > 0:
                        c.plot([x, x], [fv, tv], color=COLORS[provider], alpha=.25, lw=.9)
                        c.scatter(x, fv, edgecolor=COLORS[provider], facecolor="white", s=19, linewidth=.9, zorder=3)
                else:
                    missing_times += 1
    c.set_xticks(range(4), SIZES)
    c.set_xlim(-.5, 3.5)
    if has_time:
        c.set_yscale("log")
        c.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:g}"))
    else:
        c.text(.5, .5, "等待上下文终态数据", transform=c.transAxes, ha="center", color=MUTED)
    c.set_ylabel("秒 · 对数刻度")
    c.set_xlabel("小空心点 = 首个可见；实心 / 叉 / 三角 = 总耗时")
    c.text(.01, -.20, f"未知总耗时={missing_times}；横短线=中位数；失败 / 截尾保留。", transform=c.transAxes, fontsize=9, color=MUTED)
    style(c, "y")

    d.set_title("D  字段完整性诊断 · 同一答案内相关", loc="left")
    field_names = list(FIELD_LABELS)
    lookup = {(r.get("size_label"), r.get("provider"), r.get("field")): r.get("complete_pass_rate") for r in field_summaries}
    for fi, field in enumerate(field_names):
        for si, size in enumerate(SIZES):
            for pi, provider in enumerate(PROVIDERS):
                x = si * 2 + pi
                fraction = lookup.get((size, provider, field))
                base = np.array(colors.to_rgb(COLORS[provider]))
                face = (1 - fraction * .83) * np.ones(3) + fraction * .83 * base if finite(fraction) else np.array([.95, .96, .97])
                d.add_patch(Rectangle((x - .5, fi - .5), 1, 1, facecolor=face, edgecolor="white", linewidth=1.5))
                d.text(x, fi, f"{fraction:.0%}" if finite(fraction) else "—", ha="center", va="center", fontsize=8.8,
                       color="white" if finite(fraction) and fraction >= .8 else INK)
    d.set_xlim(-.5, 7.5)
    d.set_ylim(8.5, -.5)
    d.set_yticks(range(9), [FIELD_LABELS[f] for f in field_names], fontsize=9)
    d.set_xticks(range(8), [s + "\n" + p for s in SIZES for p in ("Go", "GOAT")], fontsize=8.5)
    for tick, p in zip(d.get_xticklabels(), PROVIDERS * 4):
        tick.set_color(COLORS[p])
    for spine in d.spines.values():
        spine.set_visible(False)
    fig.text(.055, .060,
             "整答通过须协议完整、JSON 模式精确且全部字段正确。字段百分比仅用于解释错误类型；9 个字段来自同一答案，不构成独立的统计样本。\n"
             "种子、套餐与实际 token 一一对应；缺失 usage 保持未知。长度间差异包含任务数据、缓存与时段影响，不能视为纯网络带宽测量。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.09, right=.975, top=.87, bottom=.17, hspace=.49, wspace=.45)
    return save(fig, out, "04-context-scaling.png", dpi, source_hash)


def figure_concurrency(data, out, dpi, source_hash):
    tables = data.get("tables", {})
    rows = [r for r in tables.get("baseline_trials", []) if r.get("phase") == "concurrency"]
    batches = tables.get("baseline_batches", [])
    fig, axes = plt.subplots(1, 3, figsize=(17.0, 7.4))
    frame(fig, data, "同一网络上的并发阶梯：吞吐量与单请求等待分别看",
          "每边并发 1 / 2 / 4；每档两个匹配批次，共每边 14 条请求。两套餐同批共享本机网络，不推断套餐绝对并发上限。", source_hash)
    levels = (1, 2, 4)
    a, b, c = axes
    a.set_title("A  固定输出合格吞吐量", loc="left")
    for provider in PROVIDERS:
        pooled = []
        for li, level in enumerate(levels):
            pop = [r for r in batches if r.get("provider") == provider and r.get("concurrency_per_provider") == level]
            good = sum(r.get("fixture_passed", 0) for r in pop)
            spans = values(pop, "provider_observed_span_seconds", positive=True)
            pooled.append(60 * good / sum(spans) if spans and len(spans) == len(pop) else np.nan)
            for ri, row in enumerate(pop):
                value = row.get("fixture_correct_per_minute_provider_span")
                if finite(value):
                    x = li + (-.10 if provider == "go" else .10) + (ri - (len(pop) - 1) / 2) * .04
                    a.scatter(x, value, color=COLORS[provider], s=29, alpha=.50)
        a.plot(range(3), pooled, "D-", color=COLORS[provider], lw=2, ms=6, label=NAMES[provider])
    a.set_ylabel("通过固定输出校验的请求 / 分钟")
    a.set_xticks(range(3), [str(x) for x in levels])
    a.set_xlabel("每个套餐的并发请求数")
    a.legend(fontsize=9)
    a.set_ylim(bottom=0)
    style(a, "y")
    for ax, key, title in [(b, "total_seconds", "B  单请求总耗时"), (c, "first_visible_seconds", "C  首个可见输出")]:
        ax.set_title(title, loc="left")
        for provider in PROVIDERS:
            medians, p90s = [], []
            for li, level in enumerate(levels):
                pop = [r for r in rows if r.get("provider") == provider and r.get("concurrency_per_provider") == level]
                vv = values(pop, key, positive=True)
                medians.append(float(np.median(vv)) if vv else np.nan)
                p90s.append(float(np.quantile(vv, .90)) if vv else np.nan)
                for ri, row in enumerate(pop):
                    value = row.get(key)
                    if finite(value) and value > 0:
                        x = li + (-.12 if provider == "go" else .12) + ((((ri * .618) % 1) - .5) * .10)
                        point(ax, x, value, row, bool(row.get("fixture_pass")), size=24, alpha=.55)
            ax.plot(range(3), medians, "o-", color=COLORS[provider], lw=2, ms=4.5)
            ax.plot(range(3), p90s, "--", color=COLORS[provider], lw=1.1, alpha=.7)
        ax.set_xticks(range(3), [str(x) for x in levels])
        ax.set_xlabel("每个套餐的并发请求数")
        ax.set_ylabel("秒（实线中位数；虚线经验 P90）")
        ax.set_ylim(bottom=0)
        style(ax, "y")
    counts = ";  ".join(f"C={level}: " + "/".join(str(sum(r.get("concurrency_per_provider") == level and r.get("provider") == p for r in rows)) for p in PROVIDERS) for level in levels)
    fig.text(.055, .14, "各档请求 N（Go / GOAT）  " + counts, fontsize=10, color=MUTED)
    fig.text(.055, .067,
             "吞吐量菱形 = 60 × 两批合格请求总数 / 两批各自套餐跨度总秒数；淡点为每批结果，失败保留在跨度内。\n"
             "延迟小点保留单请求；P90 仅为少量样本的经验分位数，不表示稳定尾延迟或置信区间。串行基线不混入此图。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.07, right=.985, top=.80, bottom=.28, wspace=.31)
    return save(fig, out, "05-matched-concurrency.png", dpi, source_hash)


def figure_mix(data, out, dpi, source_hash):
    tables = data.get("tables", {})
    grid = tables.get("mix_grid", [])
    strata = tables.get("mix_strata", [])
    fig = plt.figure(figsize=(16.5, 9.7))
    gs = fig.add_gridspec(1, 2, width_ratios=(1.25, 1))
    a, b = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])
    frame(fig, data, "按你的任务数量组合做敏感性分析，不强行给一个总冠军",
          "权重是代码 / 上下文 / 仓库工具的任务次数比例；采用各阶段主评分及实际流程耗时，包含失败和截止后的等待。", source_hash)
    a.set_title("A  不同组合的有效吞吐量比：GOAT / Go", loc="left", pad=23)
    h = math.sqrt(3) / 2
    for pct in (.25, .5, .75):
        a.plot([pct/2, 1-pct/2], [pct*h, pct*h], color=GRID, lw=.7)
        a.plot([pct, (1+pct)/2], [0, (1-pct)*h], color=GRID, lw=.7)
        a.plot([1-pct, (1-pct)/2], [0, (1-pct)*h], color=GRID, lw=.7)
        a.text(pct, -.045, f"{pct:.0%}", ha="center", va="top", fontsize=8, color=MUTED)
        a.text(pct / 2 - .055, pct*h, f"{pct:.0%}", ha="right", va="center", fontsize=8, color=MUTED)
    a.plot([0, 1, .5, 0], [0, 0, h, 0], color="#9baab6", lw=1.2)
    ratios = [r.get("throughput_ratio_goat_over_go") for r in grid]
    logs = [math.log2(v) for v in ratios if finite(v) and v > 0]
    extent = max([.25] + [abs(v) for v in logs])
    cmap = colors.LinearSegmentedColormap.from_list("go_goat_ratio", [BLUE, "#f7f8f9", ORANGE])
    norm = colors.Normalize(-extent, extent)
    for row in grid:
        code, context, tools = (row.get(name + "_weight_pct", 0) / 100 for name in ("code", "context", "tools"))
        x, y = context + .5 * tools, tools * h
        ratio = row.get("throughput_ratio_goat_over_go")
        known = finite(ratio) and ratio > 0
        face = cmap(norm(math.log2(ratio))) if known else "#e9edf0"
        a.scatter(x, y, s=1350, marker="h", facecolor=face, edgecolor="white", linewidth=1.5, zorder=3)
        a.text(x, y, f"{ratio:.2f}×" if known else "—", ha="center", va="center", fontsize=10,
               color="white" if known and abs(math.log2(ratio)) > .65 * extent else INK, fontweight="bold", zorder=4)
    a.text(-.06, -.085, "代码 100%", ha="left", va="top", color=INK, fontsize=12)
    a.text(1.06, -.085, "上下文 100%", ha="right", va="top", color=INK, fontsize=12)
    a.text(.5, h + .075, "仓库工具 100%", ha="center", va="bottom", color=INK, fontsize=12)
    a.set_xlim(-.13, 1.13)
    a.set_ylim(-.13, h + .16)
    a.set_aspect("equal")
    a.axis("off")
    mappable = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    colorbar = fig.colorbar(mappable, ax=a, orientation="horizontal", fraction=.045, pad=.07, shrink=.85)
    positions = [-extent, 0, extent]
    colorbar.set_ticks(positions, labels=[f"{2**v:.2f}×" for v in positions])
    colorbar.set_label("<1：Go 更高    |    1：相同    |    >1：GOAT 更高", fontsize=10)

    b.set_title("B  组合计算的原始分层输入", loc="left", pad=23)
    lookup = {(r.get("stratum"), r.get("provider")): r for r in strata}
    strata_order = ("code", "context", "tools")
    labels = {"code": "复杂代码 · 含一次修复", "context": "长上下文 · 精确整答", "tools": "仓库工具 · 完整 episode"}
    yy = np.arange(3)
    for pi, provider in enumerate(PROVIDERS):
        for index, name in enumerate(strata_order):
            row = lookup.get((name, provider), {})
            p, t = row.get("pass_rate"), row.get("mean_seconds")
            throughput = 60 * p / t if finite(p) and finite(t) and t > 0 else None
            offset = -.18 if pi == 0 else .18
            if throughput is not None:
                b.barh(index + offset, throughput, height=.28, color=COLORS[provider], alpha=.9)
            b.text(.01, index + offset, f"p={p:.0%}；t={t:.1f}s；簇 N={row.get('n_clusters', 0)}" if finite(p) and finite(t) else "未完成 / 无可用分母",
                   transform=b.get_yaxis_transform(), va="center", fontsize=9, color=INK,
                   bbox={"facecolor": "white", "edgecolor": "none", "alpha": .8, "pad": 1.5})
    b.set_yticks(yy, [labels[s] for s in strata_order], fontsize=10)
    b.set_ylim(2.65, -.65)
    b.set_xlabel("有效完成任务 / 分钟 = 60p / t")
    b.set_xlim(left=0)
    style(b)
    b.legend(handles=provider_handles(), loc="upper right", fontsize=10)
    fig.text(.055, .105,
             "公式：有效完成任务 / 分钟 = 60 × Σ(w × 分层通过率) ÷ Σ(w × 分层平均总秒数)；Σw = 1。\n"
             "网格步长 25 个百分点；底边刻度为上下文比例，左边为工具比例，剩余为代码。同格两套餐采用相同权重。", fontsize=11, color=INK)
    fig.text(.055, .053,
             "此网格是探索性敏感性分析，不声明置信区间。灰色破折号表示缺失数据或比值分母不可用；不是 0 倍。\n"
             "不包含串行 / 并发固定输出基线、旧 v1 数据或追加的去围栏次级评分。结果只适用于这次网络、时段与任务分布。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.055, right=.98, top=.83, bottom=.24, wspace=.31)
    return save(fig, out, "06-workload-mix-sensitivity.png", dpi, source_hash)


def _configuration_rows(tables):
    if tables.get("code_configurations"):
        return tables["code_configurations"]
    output = []
    for effort, key in (("high", "core_trials"), ("low", "low_core_trials")):
        rows = tables.get(key, [])
        for provider in PROVIDERS:
            population = [r for r in rows if r.get("provider") == provider]
            tasks = sorted({r.get("task_id") for r in population if r.get("task_id")})
            summary = {"provider": provider, "effort": effort, "n_tasks": len(tasks),
                       "n_first_trials": sum(r.get("first_pass") is not None for r in population),
                       "n_workflows": sum(bool(r.get("workflow_terminal")) for r in population)}
            for target, source in (("strict_first_pass_macro", "first_pass"), ("strict_solved_macro", "solved"),
                                   ("after_extraction_first_pass_macro", "first_after_conservative_extraction_pass"),
                                   ("after_extraction_solved_macro", "workflow_after_conservative_extraction_solved")):
                task_rates = [rate([r.get(source) for r in population if r.get("task_id") == task])[0] for task in tasks]
                summary[target] = avg(task_rates)
            output.append(summary)
    return output


def figure_effort(data, out, dpi, source_hash):
    tables = data.get("tables", {})
    configurations = _configuration_rows(tables)
    high, low = tables.get("core_trials", []), tables.get("low_core_trials", [])
    config = {}
    for row in configurations:
        effort = str(row.get("effort") or row.get("effort_stratum") or row.get("configuration") or "").lower()
        effort = "low" if "low" in effort else "high" if "high" in effort else effort
        config[row.get("provider"), effort] = row
    fig, axes = plt.subplots(2, 2, figsize=(16.2, 11.8))
    frame(fig, data, "推理强度单独比较：名义 effort、实际思考量与完成速度",
          "high：原定 12 题 × 每边 3 次；low：追加 12 题 × 每边 2 次。追加试验在 low 调用前确定，属于次级分析。", source_hash)
    groups = [(provider, effort) for effort in ("high", "low") for provider in PROVIDERS]
    for ax, columns, title in [
        (axes[0, 0], ("strict_first_pass_macro", "strict_solved_macro"), "A  严格输出质量 · 任务宏平均"),
        (axes[0, 1], ("after_extraction_first_pass_macro", "after_extraction_solved_macro"), "B  单一完整围栏提取后的语义 · 追加诊断"),
    ]:
        ax.set_title(title, loc="left")
        for gi, (provider, effort) in enumerate(groups):
            row = config.get((provider, effort), {})
            offset = (gi - 1.5) * .18
            for si, column in enumerate(columns):
                fraction = row.get(column)
                if finite(fraction):
                    ax.bar(si + offset, fraction * 100, width=.15, color=COLORS[provider], alpha=.85,
                           hatch="///" if effort == "low" else None, edgecolor="white", linewidth=.6, zorder=3)
                    ax.text(si + offset, fraction * 100 + 2.5, f"{fraction:.0%}", ha="center", fontsize=8, color=COLORS[provider])
        ax.set_xticks((0, 1), ("首次", "含一次必要修复"))
        ax.set_xlim(-.5, 1.5)
        ax.set_ylim(0, 112)
        ax.set_yticks((0, 25, 50, 75, 100))
        ax.set_ylabel("各任务通过率的宏平均（%）")
        style(ax, "y")
    combined = []
    for effort, population in (("high", high), ("low", low)):
        for row in population:
            r = dict(row)
            r["effort_group"] = effort
            r["complete"] = bool(r.get("first_complete"))
            combined.append(r)
    c, d = axes[1]
    c.set_title("C  首答请求等待 · 含失败样本", loc="left")
    d.set_title("D  实际 usage 中的思考 token · 首答", loc="left")
    counts = []
    has_latency = has_reasoning = False
    for gi, (provider, effort) in enumerate(groups):
        population = sorted([r for r in combined if r.get("provider") == provider and r["effort_group"] == effort], key=lambda r: str(r.get("trial_id")))
        total = values(population, "first_seconds", positive=True)
        reasoning = values(population, "first_reasoning_tokens")
        counts.append(f"{SHORT[provider]} {effort}: 首答 N={len(population)}，思考 token 已知={len(reasoning)}")
        if total:
            med = float(np.median(total))
            c.plot([gi-.19, gi+.19], [med, med], color=COLORS[provider], lw=2.4, zorder=4)
            has_latency = True
        if reasoning:
            med = float(np.median(reasoning))
            d.plot([gi-.19, gi+.19], [med/1000, med/1000], color=COLORS[provider], lw=2.4, zorder=4)
            has_reasoning = True
        for ri, row in enumerate(population):
            jitter = (((ri * .61803398875) % 1) - .5) * .32
            tv, fv = row.get("first_seconds"), row.get("first_visible_seconds")
            if finite(tv) and tv > 0:
                point(c, gi + jitter, tv, row, row.get("first_pass"), size=22, alpha=.54)
                if finite(fv) and fv > 0:
                    c.scatter(gi+jitter, fv, facecolor="white", edgecolor=COLORS[provider], s=12, linewidth=.6, alpha=.5, zorder=2)
            tokens = row.get("first_reasoning_tokens")
            if finite(tokens):
                d.scatter(gi+jitter, tokens/1000, color=COLORS[provider], marker="o" if effort == "high" else "s", s=20, alpha=.5, zorder=3)
    ticklabels = [SHORT[p] + "\n" + effort for p, effort in groups]
    for ax in (c, d):
        ax.set_xticks(range(4), ticklabels)
        ax.set_xlim(-.55, 3.55)
        ax.axvline(1.5, color=GRID, linestyle="--", lw=1)
        style(ax, "y")
    if has_latency:
        c.set_yscale("log")
        c.yaxis.set_major_locator(ticker.LogLocator(base=10, subs=(1, 2, 5), numticks=8))
        c.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:g}"))
        c.yaxis.set_minor_formatter(ticker.NullFormatter())
    else:
        c.text(.5, .5, "尚无首答耗时", ha="center", transform=c.transAxes, color=MUTED)
    if has_reasoning:
        d.set_yscale("symlog", linthresh=1)
        lo, hi = d.get_ylim()
        d.set_yticks([v for v in (0, .1, .5, 1, 2, 5, 10, 20, 50, 100, 200) if lo <= v <= hi])
        d.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{x:g}"))
    else:
        d.text(.5, .5, "尚无思考 token usage", ha="center", transform=d.transAxes, color=MUTED)
    c.set_ylabel("秒 · 对数刻度")
    c.set_xlabel("实心 = 通过；叉 = 失败；小空心点 = 首个可见输出")
    d.set_ylabel("千思考 token · 对称对数刻度")
    d.set_xlabel("横短线 = 中位数；缺失 usage 保持未知")
    legend = [Patch(facecolor=COLORS[p], hatch="///" if effort == "low" else None,
                    label=SHORT[p] + " · " + effort, edgecolor="white") for p, effort in groups]
    fig.legend(handles=legend, loc="upper right", bbox_to_anchor=(.98, .918), ncol=4, fontsize=9)
    fig.text(.055, .10, "  |  ".join(counts[:2]) + "\n" + "  |  ".join(counts[2:]), fontsize=9.5, color=MUTED)
    fig.text(.055, .047,
             "高低 effort、时段与调用顺序未随机交错，属于描述性追加对比，不证明 effort 的因果效果。B 的格式提取规则在观察问题后追加。\n"
             "图 C / D 每点为请求，重复试验相关；不以这些点数替代 12 个任务簇。reasoning token 属于输出 usage，不能再次相加计费。", fontsize=10, color=MUTED)
    fig.subplots_adjust(left=.085, right=.975, top=.85, bottom=.21, hspace=.43, wspace=.25)
    return save(fig, out, "07-effort-strata.png", dpi, source_hash)


def build_all(analysis_path=ROOT / "analysis.json", out_dir=DEFAULT_OUTPUT, dpi=180):
    configure()
    analysis_path = Path(analysis_path)
    raw = analysis_path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    builders = (figure_quality, figure_latency, figure_ratios, figure_context, figure_concurrency, figure_mix, figure_effort)
    return [builder(data, out, dpi, source_hash) for builder in builders]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=ROOT / "analysis.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()
    paths = build_all(args.analysis, args.out, args.dpi)
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
