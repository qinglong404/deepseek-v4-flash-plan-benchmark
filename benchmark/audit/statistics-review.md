# Independent statistics review

Status: **calculation implementation accepted on the executed synthetic cases and partial-data snapshot**. This does not certify collection complete or establish a provider winner. No API/model calls, credential reads or changes to the frozen experiment were made. Reviewer writes remain under audit/.

Analysis revision tested: `468701f47f41e38815f275957f7fd91cc467c1fb0051d3cd284fff4f75c538e4`.

## Checks actually executed

- Task-macro quality with three repetitions in task A and one in B: paired difference is 0 rather than the pooled-trial 0.5. Two task clusters/four pairs are reported; the 589 diagnostic assertions do not create sample size.
- Equal-task geometric latency weighting: opposing task ratios 4 and 1/4 give 1 despite unequal repetition counts.
- Zero-success throughput: positive GOAT/zero Go has an explicit positive-infinity state, both zero is undefined. In a two-task synthetic case, 255/1,000 bootstrap resamples were undefined; nominal CI is suppressed and 745 finite draws are labeled conditional diagnostics. This resolves the review's original interval-labeling finding.
- Failed first grade with repair pending stays unknown for eventual outcome. A returned first response awaiting its grade is now counted as observed/pending, with no fabricated pass/fail.
- A conservative whole-output single Python fence is identified; extra prose, multiple blocks and another language are rejected. External sidecar grades are keyed by attempt ID/rule. Strict primary scores and actual nine-second workflow wait remain unchanged when normalized source passes; hypothetical three-second auto-strip time is separately labeled post hoc.
- Cost arithmetic subtracts cached tokens from total input, never adds reasoning tokens to total completion again, converts timestamps to Asia/Shanghai, respects weekday peak boundaries, and preserves unknown cache/time as unknown cost. Hand case input=1,000/cache=400/output=200 produces peak $0.0004224 and off-peak $0.0002112 list-equivalent estimates; these are calculations, not verified billing.
- Baseline synthetic denominators: 12 serial paired trials, 14 concurrent requests/provider, six workload batches/provider (two at each level). Concurrent batch counts are kept apart from serial paired uncertainty.
- A correct final repository source at the turn cap stays source_pass=true and episode_success=false/censored=true.
- Superseded terminal attempts remain in raw request totals. Started-without-returned and journal-terminal-without-result states are separately retained.
- Supplementary low effort remains outside frozen high primary: synthetic high three-repeat versus low two-repeat comparison gives the expected quality difference -0.5 and geometric time ratio sqrt(0.125). Planned 36/24 trials and later-calendar confounding are explicit.
- Observed concurrency reconstructed across phases uses half-open intervals; exact end/start adjacency does not overcount, while three actual overlapping streams are detected. In-flight calls without terminal records make live reconstruction a lower bound, as documented.
- Frozen copy of current partial logs: all 76 terminal raw attempt IDs are retained; manual task-macro first-pass recomputation agrees. Eleven core trials are observed in that snapshot and four started attempts have no terminal result yet. Those four are unknown/in-flight-or-interrupted, not automatic failures. Snapshot file hashes and capture time are recorded in statistics-acceptance-results.json.

Separately executed the actual context runner with a fake local client (24 synthetic responses). Exact nine-field valid JSON passed; extra/missing keys, boolean replacing an integer, wrong nested owner, incomplete protocol with valid content, fenced JSON and wrong list order were rejected. No upstream was contacted.

## Findings and limitations retained

1. The source-only strict v2 score and posthoc fence-normalized source correctness answer different questions. The previous v1 wrapper-stripping convention cannot be pooled with strict v2, and a fence SyntaxError should not be described as an algorithm failure.
2. The baseline runner's generic equality can conflate bool/int/float types. Independently checked all 52 observed baseline outputs using exact keys, values and types: no grade disagreement in this run. No new calls or primary-score changes are needed for this dataset.
3. Low-phase fence diagnostics need the diagnostic collector to accept low_core_first/low_core_repair; the analysis itself supports them. Without such grades, fenced low source correctness remains explicitly unknown. Parent was notified.
4. Task bootstrap intervals are conditional exploratory summaries of this hand-picked bank. Missing draws, small task counts, shared link/gateway load, time of day, caching and posthoc supplementary choices constrain interpretation. No claim of statistical equivalence or universal model superiority follows.
5. Source grade, valid episode termination, transport completeness, and exact context JSON schema must remain separate. The audit confirms this separation on tested cases, not every possible malformed log or adversarial program.
6. Cross-phase context starts overlap timestamps of unmatched core starts in the partial journal. Parent was asked to confirm whether these are still active or interrupted and to account for observed load/unknown usage. The auditor did not inspect/change process state or launch any paid requests.

## Reproduction

- check_analysis.py; statistics-acceptance-results.json
- partial-statistics-snapshot/; partial-statistics-analysis.json
- check_context_grading.py; context-grading-results.json

Analysis and logs may evolve after this snapshot; acceptance is tied to the tested hash and recorded evidence.
