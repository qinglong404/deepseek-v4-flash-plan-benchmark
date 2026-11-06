# CSV 表索引

所有 CSV 均使用 UTF-8 BOM，便于 Excel 直接打开。文件保持 `analysis.json`/`quantity.json` 的原始字段名；缺失值不自动补零。

共 **50** 个表、**2,829** 行数据。逐题相关性和任务合同权重见 `../ANALYSIS_README.md`。

| 文件 | 数据行 | 列 | 字节 |
|---|---:|---:|---:|
| [`administratively_excluded_code_attempts.csv`](administratively_excluded_code_attempts.csv) | 1 | 12 | 492 |
| [`administratively_invalidated_terminal_requests.csv`](administratively_invalidated_terminal_requests.csv) | 1 | 46 | 1,390 |
| [`administratively_resolved_missing_client_attempts.csv`](administratively_resolved_missing_client_attempts.csv) | 2 | 20 | 1,052 |
| [`aggregate_records.csv`](aggregate_records.csv) | 822 | 4 | 93,076 |
| [`baseline_batches.csv`](baseline_batches.csv) | 12 | 37 | 6,426 |
| [`baseline_pair_summaries.csv`](baseline_pair_summaries.csv) | 4 | 12 | 418 |
| [`baseline_pairs.csv`](baseline_pairs.csv) | 26 | 13 | 4,214 |
| [`baseline_summaries.csv`](baseline_summaries.csv) | 8 | 52 | 5,386 |
| [`baseline_trials.csv`](baseline_trials.csv) | 52 | 42 | 26,787 |
| [`code_configurations.csv`](code_configurations.csv) | 4 | 15 | 1,183 |
| [`context_field_summaries.csv`](context_field_summaries.csv) | 72 | 6 | 2,838 |
| [`context_fields.csv`](context_fields.csv) | 216 | 8 | 13,954 |
| [`context_pairs.csv`](context_pairs.csv) | 12 | 10 | 1,387 |
| [`context_summaries.csv`](context_summaries.csv) | 8 | 71 | 7,084 |
| [`context_trials.csv`](context_trials.csv) | 24 | 46 | 13,499 |
| [`core_extraction_diagnostics.csv`](core_extraction_diagnostics.csv) | 72 | 16 | 7,325 |
| [`core_failures.csv`](core_failures.csv) | 32 | 6 | 1,486 |
| [`core_leave_one_task_out.csv`](core_leave_one_task_out.csv) | 12 | 2 | 445 |
| [`core_pairs.csv`](core_pairs.csv) | 36 | 17 | 6,859 |
| [`core_task_pairs.csv`](core_task_pairs.csv) | 12 | 7 | 1,025 |
| [`core_tasks.csv`](core_tasks.csv) | 24 | 50 | 8,514 |
| [`core_trials.csv`](core_trials.csv) | 72 | 63 | 32,487 |
| [`effort_task_comparisons.csv`](effort_task_comparisons.csv) | 24 | 31 | 9,538 |
| [`low_core_extraction_diagnostics.csv`](low_core_extraction_diagnostics.csv) | 48 | 16 | 5,200 |
| [`low_core_failures.csv`](low_core_failures.csv) | 32 | 6 | 1,469 |
| [`low_core_leave_one_task_out.csv`](low_core_leave_one_task_out.csv) | 12 | 2 | 448 |
| [`low_core_pairs.csv`](low_core_pairs.csv) | 24 | 17 | 4,788 |
| [`low_core_task_pairs.csv`](low_core_task_pairs.csv) | 12 | 7 | 785 |
| [`low_core_tasks.csv`](low_core_tasks.csv) | 24 | 50 | 7,761 |
| [`low_core_trials.csv`](low_core_trials.csv) | 48 | 63 | 22,532 |
| [`mix_grid.csv`](mix_grid.csv) | 15 | 10 | 2,270 |
| [`mix_grid_auto_strip_counterfactual.csv`](mix_grid_auto_strip_counterfactual.csv) | 15 | 10 | 2,248 |
| [`mix_strata.csv`](mix_strata.csv) | 6 | 5 | 317 |
| [`mix_strata_auto_strip_counterfactual.csv`](mix_strata_auto_strip_counterfactual.csv) | 6 | 5 | 318 |
| [`observed_concurrency.csv`](observed_concurrency.csv) | 16 | 21 | 2,465 |
| [`overlapping_failure_candidates.csv`](overlapping_failure_candidates.csv) | 4 | 10 | 919 |
| [`quantity_exclusion_summaries.csv`](quantity_exclusion_summaries.csv) | 24 | 6 | 2,164 |
| [`quantity_paired_quantity_ratios.csv`](quantity_paired_quantity_ratios.csv) | 18 | 17 | 6,914 |
| [`quantity_quantity_summaries.csv`](quantity_quantity_summaries.csv) | 36 | 33 | 17,483 |
| [`quantity_request_workflow_accounting.csv`](quantity_request_workflow_accounting.csv) | 4 | 17 | 1,561 |
| [`quantity_task_cost_summaries.csv`](quantity_task_cost_summaries.csv) | 288 | 13 | 28,867 |
| [`quantity_workflow_cost_records.csv`](quantity_workflow_cost_records.csv) | 120 | 43 | 53,134 |
| [`request_counters.csv`](request_counters.csv) | 155 | 5 | 6,901 |
| [`request_records.csv`](request_records.csv) | 321 | 46 | 172,300 |
| [`request_strata.csv`](request_strata.csv) | 20 | 52 | 12,589 |
| [`requests_without_terminal_workflow.csv`](requests_without_terminal_workflow.csv) | 1 | 46 | 1,390 |
| [`tool_summaries.csv`](tool_summaries.csv) | 4 | 28 | 1,242 |
| [`tool_trajectory_episodes.csv`](tool_trajectory_episodes.csv) | 12 | 72 | 7,655 |
| [`tool_trajectory_summaries.csv`](tool_trajectory_summaries.csv) | 4 | 53 | 3,138 |
| [`tool_trials.csv`](tool_trials.csv) | 12 | 35 | 3,521 |
