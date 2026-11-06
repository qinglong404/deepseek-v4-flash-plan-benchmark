# Analysis implementation and table schema

Run `python analysis.py` from any working directory, or select a result directory
with `--root DIR`. The default is the script's directory. `--draws` defaults to
10,000, with a fixed seed and a stable per-metric seed salt. The script imports
no client, calls no API, reads no credentials, and writes only `analysis.json`
and `analysis-summary.txt` in the result directory. It is safe to rerun while
JSONL collectors are appending: absent files and an incomplete trailing JSONL
row are tolerated and recorded. Running files are not transactional snapshots;
rerun after collection stops for final reporting.

No v1 data or earlier comparison is read. No frozen contracts, prompts, cases,
runner, repair feedback, or strict grades are modified by this script.

## Statistical definitions

The code primary endpoint is task-macro pass@1: average the three first-attempt
success indicators within each of the twelve task contracts, then average those
twelve task rates. Repetitions measure repeatability, not 36 independently chosen
problems. The 589 hidden checks are diagnostics, never confidence-interval units.

`core.summary` reports all observed outcomes per provider; missing tasks and
pending repairs are explicitly counted and are not imputed as failures. A code
row with an observed failed first attempt but a pending repair contributes to
first-pass reporting and not to completed-workflow reporting. In partial data,
task macro rates average observed task clusters only. This may be unbalanced and
must not be presented as the final 12-task result.

Core confidence intervals use matched trial identities (task and repetition),
resample whole task clusters 10,000 times, and keep all matched repetitions in
a sampled cluster together. Macro quality differences use equal task weight,
then equal observed repetition weight within task. All differences are GOAT-Go.
The primary first-pass difference and the secondary solved-after-one-repair
difference have separate complete-pair populations. The summary's all-observed
macro estimate and the paired CI estimate can therefore differ during partial
collection; each population's task/trial counts are retained.

Two latency ratios are reported: first attempts both correct, and completed
workflows both solved. For each task, average paired log(GOAT_seconds/Go_seconds)
over its eligible repetitions, average equally over eligible tasks, then
exponentiate. Values above one favor Go. These are conditional speed comparisons;
they must be read with correctness and failure rates. They do not assign finite
completion times to never-solved tasks.

Useful workflow throughput includes completed failed workflows in elapsed time:
`(sum solved_GOAT / sum workflow_seconds_GOAT) / (sum solved_Go / sum workflow_seconds_Go)`.
This ratio is above one when GOAT is better. Bootstrap resampling again samples
whole paired task clusters, recomputing the sums each draw. The point estimator
uses matched terminal workflows. Provider summary throughput also reports each
provider's all-observed terminal workflows; this may differ from the paired
comparison during partial data. Leave-one-task-out rows and minimum/maximum
show single-task sensitivity. Undefined ratios (e.g. zero Go solved numerator)
are null, not JSON infinity, with `estimate_state` distinguishing positive
infinity (GOAT positive, Go zero) from both-zero undefined. If ANY bootstrap draw
is undefined, the nominal CI is suppressed. Explicitly named
`conditional_finite_ci_*` quantiles may remain for audit diagnostics only; they
are not an unconditional 95% interval. Valid-draw and defined-leave-one-out counts
make omissions visible. With fewer than two observed clusters no CI is
reported. Percentile CIs use linearly interpolated 2.5% and 97.5% quantiles.
These small-sample intervals are exploratory and do not establish equivalence.

Baseline serial intervals resample the twelve matched serial pair identities,
not individual stream deltas. Baseline distributions include every terminal
request; missing first-visible times are omitted from that percentile only and
counted separately. Serial all-terminal and both-fixture-correct ratios are
separate. Concurrency pair wins and batch rows are descriptive; the few batches
are not inflated into independent token or request samples. A serial pair has
one stream per provider and shares the user's link. It is not a single global
stream. Concurrent provider spans derive from min(started) to max(ended);
shared batch wall time and `new_requests` are retained so resumed partial batches
cannot be mistaken for a fresh full batch.

Context seeds are matched by dataset identity, separately within each frozen
size label. Actual prompt tokens are reported alongside planned labels and
estimates; sizes are never reassigned after usage is observed. Full JSON pass
requires the recorded complete response, exact schema and every expected field.
Per-field semantic pass and protocol-complete field pass are separate correlated
diagnostics. Context latency intervals use paired dataset seeds and all terminal
requests, including failures, rather than conditioning on correctness.

Tool episodes distinguish final source hidden-test success from episode success
(source success plus final model response before termination/cap). Censored turn
caps remain in the denominator. Turns, tool errors, termination reasons and final
source checks are retained. The runner's elapsed metric sums model request times
and excludes local grader/tool execution; analysis does not relabel it as full
human wall time. Core workflow time likewise follows recorded request times.

## Strict versus conservative-extraction diagnostics

Strict raw outcomes remain the primary endpoints and determine repair inputs.
`core-extracted-grades.jsonl` is an optional sidecar generated externally by the
parent's same isolated frozen validator. Each row has `attempt_id`, `provider`,
`trial_id`, `stage`, `extraction_rule` and `extracted_code_grade`.

The permitted rule is `single_whole_fenced_block_v1`: the complete final response
must be whitespace plus exactly one fenced block labeled lowercase `python`,
`py`, or blank plus whitespace; the body cannot contain an additional fence line.
There is no selection among multiple blocks, no edits and no alternative snippets.
The script detects this wrapper to normalize a resulting SyntaxError as `format`
and merges the externally computed grade. It never executes submitted code.
Nonfenced attempts retain their primary grade in `after_conservative_extraction`
fields. Fenced attempts awaiting a diagnostic remain unknown; known denominators
are explicitly counted. `first_extracted_pass`/`repair_extracted_pass` denote only
actual secondary grader observations, while the `after_...` fields provide the
combined no-wrapper-needed/one-wrapper-only view. These fields diagnose valid
source inside a formatting violation; they do not overwrite strict quality or
any primary CI, repair trajectory, throughput, or workload-mix input.

`core.secondary_metrics` adds paired task-cluster CIs for conservatively extracted
first-source correctness, source correctness after the recorded repair, and
first-call latency among both-first-source-correct pairs. These were requested
after observing a wrapper violation and are explicitly posthoc diagnostics.
The deterministic `auto_strip_*` counterfactual uses measured first-call time
when the normalized first source passes; otherwise it uses recorded workflow
time and normalized final success. Its intervals, useful-throughput ratio,
leave-one-task-out range, and optional `mix_grid_auto_strip_counterfactual` are
separate. It measures no new API speed and cannot change actual spent wait.

Raw failure labels remain available. Normalized grader labels inspect both
top-level and per-check diagnostics for restriction phrases including
`not permitted`, `unsupported`, `restricted`, `allowlist`, `forbidden`, `blocked`,
`disallow`, and `not allowed`. Syntax/indentation failures are separate. Resource
and grader-process failures are preserved. For incomplete requests, deadline,
HTTP error and transport evidence can explain a raw `route_unverified`; the raw
label and route-header presence remain visible. Overlapping cross-provider
incomplete calls are temporal disruption candidates, not proof of a shared cause.
Restriction rejections are benchmark nonpasses, not demonstrated algorithm
errors. The model prompt disclosed imports, IO and resources, but did not fully
spell out the AST gate's name/dunder-attribute bans. This is an execution-contract
limitation; normalized restriction outcomes must be reported separately.

## Supplementary low-effort stratum

The later `LOW_EFFORT_ADDENDUM.md` adds all twelve frozen contracts, two trials
per provider at low effort, with unchanged strict grading, extraction diagnostics
and one-repair policy. `low-core-results.jsonl` and `low-core-first-grades.jsonl`
are analyzed in the separate `low_core` section and mirrored `low_core_*` tables,
with 24 planned trials/provider. This is a hypothesis-driven posthoc addition
after observing different reasoning lengths at nominal high. It is never pooled
into the frozen high primary endpoint. Completion now requires both effort
strata and the original baseline/context/tool strata to be terminal.

`code_configurations` reports four provider/effort combinations with strict and
extracted task-macro quality, first/workflow times, counterfactual time, and
reasoning/output tokens. `effort_task_comparisons` joins high/low by provider and
task. `effort_comparison.metrics_by_provider` resamples tasks for descriptive
low-minus-high quality differences and geometric means of ratios of each task's
low/high mean times or tokens. High has three repetitions, low two. Effort,
calendar order, cache and load are confounded; this is not a randomized causal
effort study. Selecting a configuration should compare observed quality with
time/budget, while equal observed quality is not proof of equivalence.

## Administrative collector interruption and recovery

`collector-interruptions.json` explicitly lists three excluded attempt IDs for
one original trial pair: one returned original Go first response and two starts
whose collector died before saving a client terminal record. Its SHA256 is saved
under `administrative_recovery.manifest_sha256`. Only listed IDs are filtered
from primary code grade/workflow reconstruction. The entire pair is rerun fresh
under its original trial identity; no other tasks are selectively rerun.

All original records remain in all-attempt tables. The original returned grade,
including restriction classification, appears in
`administratively_excluded_code_attempts`; its measured tokens/cost/time remain
in terminal request accounting. It is neither rewritten as a pass nor described
as an algorithm error. The two missing client finals appear separately under
`administratively_resolved_missing_client_attempts` with client latency, usage
and estimated cost null. Gateway status499 and elapsed time retain explicit
gateway prefixes and never substitute for client observations. Gateway token
zeros are not evidence of measured zero usage.

`requests.raw_unreturned_attempts` retains all missing client finals;
`requests.unreturned_attempts` and `unresolved_unreturned_attempts_n` exclude only
the explicit administrative resolutions. The completion gate uses the unresolved
count, reports both resolved missing finals, and labels any final cohort as
evaluable cohorts completed with administrative replacements. Such collector
interruptions are not provider failures. Missing charges remain unknown.

`administrative_recovery.sensitivity_drop_recovered_pair` repeats the core paired
statistics while dropping that entire recovered trial identity. At full data this
has 35 paired trials while retaining all twelve task clusters. It exposes the
possible influence of administrative replacement without silently deleting the
original genuine returned restriction failure or imputing outcomes for interrupted
responses. Collector/PID evidence, rather than apparent overlapping unfinished
journal starts alone, determines the recovery interpretation.

## Usage and estimated cost

All requests are deduplicated by `attempt_id`, including requests embedded in
result files and requests never selected by a resumed final workflow. Result
rows are deduplicated by provider/trial identity using the latest recorded row.
Journal starts without terminal request records are `in_flight_or_interrupted_unknown`,
not declared free, successful or failed. Costs cannot be inferred for them.
`requests_without_terminal_workflow` retains attempts not yet referenced by a
completed selected workflow. Workflow throughput follows recorded chosen
responses; unknown pending/abandoned overhead is flagged for review rather than
silently inserted or deleted. Request/cost totals include all terminal attempts.

`observed_concurrency` and per-request reconstructed stream fields use timestamp
intervals across ALL phases/providers. During a live partial run these are lower
bounds because unreturned calls may have no terminal record. Runner metadata's
nominal per-provider concurrency is kept separately; concurrent phases may add
to total link load. Half-open intervals treat an end at another start as no
overlap. These load descriptions support interpretation, not causal attribution.

Prompt tokens include cached tokens; uncached input is prompt minus cached.
Completion tokens already include reasoning tokens, which are reported separately
and never charged twice. Missing cache/usage values remain unknown. Cache labels
are `reported_zero_cache`, `reported_cache_hit`, or `unknown`; the script does not
infer cold/warm cache from request order.

Estimated USD list-equivalent rates per million uncached input / cached input /
completion tokens are 0.30 / 0.006 / 1.20 for Monday–Friday 09:00–12:00 and
14:00–18:00 Asia/Shanghai, and 0.15 / 0.003 / 0.60 otherwise. Request start chooses
the period; a request crossing a boundary is not split. A missing timestamp or
unknown required token component leaves cost unknown. Known-cost sums do not
include unknown charges. This is an estimate using the requested pricing model,
not exact billing, subscription deductions, residual allowance or observed charge.

## Workload sensitivity

The 15 triangular-grid rows use code/context/tools task-count percentages drawn
from 0/25/50/75/100 and summing to 100. Each provider has:

`expected_correct_tasks_per_minute = 60 * sum(weight_s * pass_rate_s) / sum(weight_s * mean_total_seconds_s)`.

Code uses task-macro success/time with the prescribed repair workflow. Context
uses dataset-macro exact JSON success/time. Tools use repository-macro episode
success/time. Weights describe expected counts of tasks, not runtime/token/cost
shares. Baseline and v1 are excluded. Missing positive-weight strata yield null,
not a fabricated estimate. This convenience view has no asserted overall winner
or uncertainty interval; quality, latency, failures and the task bootstrap remain
separate decision inputs.

## JSON layout

Top-level metadata: `schema_version`, `generated_at`, `partial_data`, bootstrap
seed/draw count, source row counts and warnings. Sections `core`, `low_core`,
`effort_comparison`, `baseline`, `context`, `tools`, `requests`, `workload_mix`
`workload_mix_auto_strip_counterfactual` and `administrative_recovery` contain
aggregates and interpretation.
`tables` contains worksheet-ready lists of flat scalar records:

| Table | One row represents |
|---|---|
| request_records | Every terminal request attempt with phase, protocol/route/failure, latency, cache, tokens, reasoning, local pricing and estimated cost |
| request_counters | Provider/phase/dimension/value count for failure/status/route/cache/finish/period |
| request_strata | Provider/phase/effort/peak-period/concurrency descriptive stratum |
| observed_concurrency | Reconstructed global/provider stream-count summaries by provider/phase |
| requests_without_terminal_workflow | Terminal calls not yet referenced by a selected terminal workflow |
| administratively_invalidated_terminal_requests | Original returned attempts excluded from primary pair analysis, with all measured request fields retained |
| administratively_resolved_missing_client_attempts | Collector-interrupted starts; unknown client usage/time and separately labeled gateway evidence |
| administratively_excluded_code_attempts | Original returned code grades, raw/normalized restriction labels and exclusion reason |
| overlapping_failure_candidates | Two incomplete calls on different providers with overlapping measured intervals |
| core_trials | One task/repetition/provider workflow, primary first/repair grades, timings, tokens, secondary extraction diagnostics and pending state |
| core_tasks | One task/provider macro component, first/solved/extraction rates and first/workflow times/tokens |
| core_pairs | One matched task/repetition trial with both providers' correctness, times and ratios |
| core_task_pairs | One paired task with quality differences and descriptive first-time ratio |
| core_failures | Task/provider/stage raw versus normalized failure count |
| core_leave_one_task_out | Throughput ratio after excluding one task cluster |
| core_extraction_diagnostics | Compact per-trial primary versus conservative-extraction observations |
| low_core_* | Independent low-effort equivalents of all core tables |
| code_configurations | Provider/effort task-macro quality, time, reasoning/output budget; four configurations |
| effort_task_comparisons | Per-provider/task high-versus-low descriptive differences and ratios |
| baseline_trials | One fixed-output request |
| baseline_summaries | Provider/phase/concurrency percentiles, exact correctness and tokens |
| baseline_pairs | One matched fixed-output trial with total/visible pair wins and ratios |
| baseline_pair_summaries | Pair wins and missing counts by serial/concurrency level |
| baseline_batches | One provider/concurrency/repetition measured batch span and correct throughput |
| context_trials | One dataset/provider with planned/actual size, full JSON grade and request measurements |
| context_fields | One expected field/dataset/provider, with raw semantic and complete-response pass flags |
| context_field_summaries | Field pass rates by size/provider |
| context_summaries | Size/provider grades, actual tokens, cache/usage and timing |
| context_pairs | One matched dataset with both providers' results and times |
| tool_trials | One repository/repetition/provider episode with source versus episode success, turns/errors/censoring |
| tool_summaries | Repository/provider episode statistics |
| mix_strata | Provider/code-context-tools pass rate and mean time inputs |
| mix_grid | One of fifteen task-count workload mixtures with both provider throughputs and ratio |
| mix_strata_auto_strip_counterfactual | Explicit posthoc deterministic auto-strip input rates/times |
| mix_grid_auto_strip_counterfactual | Fifteen optional counterfactual mixtures, keeping primary grid intact |
| aggregate_records | Numeric/text/boolean scalar aggregate leaves, addressed by metric_path |

The bootstrap result structure is `{estimate, ci_low, ci_high, n_clusters,
n_pairs, draws_requested, draws_valid, resampling_unit, seed, direction, ...}`.
Ratio direction is explicit: latency GOAT/Go >1 favors Go, useful-throughput
GOAT/Go >1 favors GOAT. No NaN or infinity is emitted; unavailable values are null.

The author exercised deterministic hand-calculated examples for task-macro
quality, clustered interval extrema, correct-only latency, failed-workflow
throughput, peak/off-peak cost, extraction, restriction normalization, and empty
partial runs. These are author checks, not independent acceptance; a non-author
reviewer must audit formulas and recompute selected estimates before delivery.
