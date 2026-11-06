# Workbook source/schema review

Status: **source data mapping and the checked partial-data preview accepted after fixes**. Final export still requires the complete evaluable cohort, as enforced by workbook.mjs. The reviewer did not run/edit workbook.mjs, call providers or read credentials; all reviewer writes are under audit/.

Reviewed workbook revision: `99a99147e470e8fb737abd774f3e9a9fefd34d6b4e8acb59e525a39b2f51db8a`.
Analysis JSON used for independent numeric comparison: `cf4844df1045a0a9a664fbe5b9560cad4ed33c6c93071086b9bccd6f3adbda5c` (partial).

## Defects found and rechecked after parent fixes

1. Tool summary originally read nonexistent tool_calls_mean. It now correctly derives average calls from tool_calls_sum/n_episodes, guarding zero episodes.
2. Original raw preview displayed UTC 10:16:12 for an Asia/Shanghai 18:16:12 request. It now displays 18:16:12 and labels the column Beijing time; verified by viewing the rendered image against analysis.started/local_started.
3. The original workbook hid missing-client unknown usage behind terminal-only counts and omitted administrative flags on returned requests. Summary/usage views now use unknown_usage_including_missing_client_n, raw rows show exclusion flag/reason, and a separate administrative table keeps missing client observations unknown while labeling gateway-only evidence.
4. Broad semantic-score labels now consistently say removal-of-wrapper/去框, including the chart legend. The footnote calls this a posthoc supplementary diagnostic. Strict primary, actual workflow wait and hypothetical auto-strip analysis remain distinct.
5. Formula validation now rejects nonnumeric/nonfinite values before numeric tolerance comparisons and asserts the original value is restored after sensitivity testing.

## Checks actually performed

- Read workbook.mjs against analysis.py and current analysis.json table keys.
- Reviewed rendered summary, context/tool and raw-request previews. The time-zone fix was independently rechecked in the raw preview.
- Confirmed deterministic formula source order: code Go/GOAT rows 6/7, context Go/GOAT rows 8/9, tools Go/GOAT rows 10/11. Worksheet formulas use Go 6/8/10 and GOAT 7/9/11.
- Independently recomputed every one of the fifteen mixture rows from analysis.mix_strata and grid weights, then compared with the recorded actual spreadsheet formula values: zero numeric differences.
- Independently checked the recorded sensitivity test: doubling only Go code wait halves its correct/minute value and restoring the source restores the result exactly.
- Confirmed tool-source pass and valid episode success use distinct fields, context retains planned and actual sizes, and model/repair waits are represented as request-time sums.
- Confirmed final export rejects partial_data=true and output path resolves under the requested outputs/magpie-v2 folder.

Numeric evidence and file hashes: workbook-numeric-check.json. The parent-produced workbook-formula-checks.json supplies actual worksheet values; reviewer recomputation used analysis primitives rather than the stored expected column.

## Limits

This is read-only source/schema and partial-preview acceptance, not an independent re-export or a claim that final statistics are ready. Final tables/charts must be regenerated after data collection ends. During a partial preview, the worksheet may leave all mixture formulas blank when any stratum is unavailable even though a zero-weight-only analysis scenario could be computable; the final guard/full cohort avoids that partial-only difference. Ratio uncertainty and administrative recovery sensitivity remain in the full analysis/report rather than all being reproduced in the concise workbook.
