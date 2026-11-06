# Measured workflow quantity model

Run `python quantity.py` after regenerating `analysis.json`. Defaults: read
`analysis.json` and write `quantity.json` beside the script, 10,000 task-cluster
bootstrap draws, nominal USD100 allowance. `--root DIR`, `--draws N` and
`--allowance USD` are available. The script reads no other runtime source,
credentials, account, billing API or gateway, and makes no network calls. It
records the source analysis SHA256 and partial-data status. Frozen benchmarks,
collectors, grades and analysis.py are unchanged.

This model answers how measured token consumption, failures and repair behavior
translate the same nominal allowance into useful work. It is **not exact billing,
actual subscription deductions, residual quota, or guaranteed purchasable tasks**.
Known partial cost totals never imply unknown calls were free. Published USD100
allowance values must be understood in the same list-equivalent unit as the rate
model; discounts/allowance multipliers or a different provider accounting basis
would require a separate conversion and are not inferred here.

## Estimand and common eligibility

For each provider, high/low effort, and price scenario:

`correct workflows / allowance = allowance * mean_task(mean_eligible_trial(success)) / mean_task(mean_eligible_trial(whole_workflow_cost))`.

A workflow is the measured initial call plus the prescribed repair if needed.
Both successful and failed workflow costs enter the cost mean. Each task has
equal weight, followed by equal eligible-repetition weight within its task. This
is a ratio of macro means; averaging per-task success/cost ratios would overweight
cheap tasks. Assertions and individual stream chunks are never statistical units.

Actual strict and actual conservative-extracted quantities share **exactly the
same eligible workflows** within each provider/effort/price scenario: workflow
terminal, whole selected cost known, and strict plus conservative outcomes known.
A pending conservative diagnostic therefore excludes that workflow from both
headline quantities, with its known cost and exclusion reason still visible.
Strict raw success is not rewritten. Conservative source success is the existing
posthoc one-whole-fence diagnostic, retaining all actual spent repair costs.

Complete whole-workflow usage requires known nonnegative input, cached and output
tokens for EVERY first/repair request, with cached<=input. One missing first or
repair stage makes whole usage unknown. A known repair cost alone cannot price
an unknown failed first request. Actual observed cost additionally requires every
stage's recorded timestamp-dependent list-equivalent estimate. The script sums
stage costs and checks agreement with the supplied aggregate, without replacing
unknown values with zero. Missing stages, pending outcomes, excluded task counts
and sample coverage remain explicit.

Provider summary subsets can differ when one provider loses usage. Direct
GOAT/Go quantity ratios additionally use the **same eligible trial identities in
both providers** and equal paired-task weighting. The modeled allowance cancels
from that ratio. The cost-known subset may be unrepresentative: missing usage on
hard failures can bias an extrapolation. Neither bootstrap nor matching repairs
unknown costs. Do not present the model as full-cost accounting when coverage is
incomplete.

## Price scenarios

- `observed_start_period`: sum each measured first/repair estimate from analysis.
  This can be a mixture of the recorded weekday peak/off-peak periods.
- `uniform_off_peak`: reprice every known whole-workflow component at per-million
  uncached input / cached input / output rates USD0.15 / 0.003 / 0.60.
- `uniform_peak`: reprice the same known components at USD0.30 / 0.006 / 1.20.

Prompt/input tokens include cached input, so uncached=input-cache. Output tokens
already include reasoning; reasoning is never added or charged twice. A uniform
scenario is a reprice holding measured tokens, cache hits, settings and repair
behavior fixed. It is not evidence the model behaves the same at another hour.
Uniform peak prices are exactly twice off-peak, so eligible-set quantities are
halved. Repricing can be known when usage is known but the original timestamp is
missing; the observed cost remains unknown and each scenario's coverage is shown.

Monthly models do not simulate five-hour/weekly caps, scheduling, changing cache
hits, price changes or different real task mixtures. High and supplementary low
remain separate; low was added after early high observations. There is no
arbitrary weighted overall winner.

## Auto-strip counterfactual

`counterfactual_conservative` is a separate posthoc deterministic policy:

- If normalized first-source correctness is known true, use the measured FIRST
  request's cost, even if the actual strict collector spent a repair afterward.
- Otherwise, if normalized first-source correctness is known false and the
  recorded workflow is terminal, use its actual whole cost and normalized final
  correctness.
- Unknown selection/outcome or any required cost component remains excluded.

This is inferred cost under an automatic wrapper-strip policy, not new API
measurement, actual billing or a refund. It never changes observed waits/costs.
Its known-cost population can differ from the actual-workflow population because
a valid first source may have known first cost but an unknown actual repair cost.
Coverage and policy basis are therefore shown separately, not silently pooled.
Raw strict success fields are not assigned normalized success in counterfactual
task tables. First/workflow actual seconds and costs remain alongside inferred
counterfactual fields for review.

## Uncertainty and limits

Bootstrap resamples whole task clusters with replacement, retaining each task's
eligible repeated trials; the point estimate is recomputed from sampled task
means. Provider intervals require at least two eligible task clusters. Matched
provider ratios resample paired task clusters. Fixed seed2026110523 and stable
cohort salts make results reproducible. The same resampling indices are used for
uniform off/peak when their eligible task sets match.

Zero success gives zero useful quantity when cost is positive. A zero cost with
positive success is marked positive infinity and represented numerically as null;
both-zero is undefined. A ratio with zero Go useful quantity is not called a tie.
If any bootstrap ratio draw is undefined, the nominal95% interval is suppressed.
Explicitly named conditional finite quantiles may remain for diagnostics, with
valid/undefined draw counts, and must not be called an unconditional95% interval.
These small synthetic-task intervals do not include quota/pricing/model-drift
uncertainty or selection bias from unknown usage.

## JSON tables

All tables contain flat scalar records for workbook/report use.

| Table | Meaning |
|---|---|
| workflow_cost_records | Per workflow stage-derived actual/counterfactual costs, token knownness, success flags, actual waits and per-scenario eligibility/exclusions |
| quantity_summaries | Provider/effort/price/endpoint task-macro cost, same-population success, modeled correct workflows/allowance, bootstrap interval and coverage |
| task_cost_summaries | Per-task eligible-workflow mean cost and success; counterfactual rows are labeled and raw strict fields are null |
| exclusion_summaries | Counts by provider/effort/price/scenario and combined exclusion reason |
| paired_quantity_ratios | Matched known-cost trial/task subsets, GOAT/Go quantities ratio, interval, state and coverage |
| request_workflow_accounting | Measured selected workflow cost-known counts versus all request subtotals, including administrative/superseded/pending attempts and missing client finals |

`quantity_summaries.endpoint` is `actual_strict`,
`actual_conservative_extracted`, or `counterfactual_conservative`.
`task_macro_cost_per_workflow` is estimated USD list equivalent, not charged USD.
`modeled_correct_workflows_per_allowance` is an expectation under the specified
workload model, not a guaranteed count. Cost JSON precision supports reproducible
arithmetic and is not a claim of cent-level or micro-dollar billing precision.
No total exact charge is output.

## Author hand-calculation example

TaskA has three eligible recorded costs USD0.15/0.30/0.45, strict successes1/0/1,
and normalized source successes1/1/1. TaskB has one cost USD0.60, strict0 and
normalized0. Equal-task mean cost=(0.30+0.60)/2=0.45. Strict success=(2/3+0)/2=1/3;
normalized success=(1+0)/2=1/2. Per nominal USD100 this gives strict74.074... and
normalized111.111... correct workflows. Naively pooling four repetitions would
produce a different, incorrect task weighting.

If TaskA's second workflow has normalized first success and first-only cost0.15,
auto-strip changes A's mean modeled cost to(0.15+0.15+0.45)/3=0.25. B remains0.60;
macro counterfactual cost0.425 and useful quantity117.647.... Recorded actual
cost0.30 for that workflow remains unchanged. Doubling uniform rates halves
modeled useful quantities. An extra workflow with unknown first usage but known
repair cost remains excluded, never priced as repair-only.

These examples are author checks. Independent acceptance must verify the model,
coverage and calculations before the report uses them.
