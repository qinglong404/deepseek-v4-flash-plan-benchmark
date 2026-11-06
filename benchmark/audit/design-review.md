# Independent design review

Reviewed 2026-11-05. Scope: frozen PLAN.md only; no implementation or submissions existed at review time. No credentials or external API calls were read or made.

The design correctly separates task families, counts task-level pass rates, retains failed attempts, and avoids combining the previous exploratory sample with the new experiment. The following details should be frozen before data collection.

1. **Shared-network interference.** Two simultaneous requests per provider can create four simultaneous streams on the same local gateway/network. Label those quality trials as matched-load trials; randomize the order of provider starts; keep a serial paired calibration stratum; record launch/termination timestamps so overlapping disruptions can be identified. Do not attribute simultaneous failures solely to the provider.
2. **Repetitions and uncertainty.** Three temperature-zero sessions per contract do not create 36 independent tasks. Use the twelve distinct task identities as statistical clusters; show task-level outcomes and repeat variability. Confidence intervals across this hand-selected bank describe the bank, not all programming work.
3. **Stream termination and clocks.** Define success using the provider's documented terminal protocol and a valid completion reason, not HTTP status or EOF alone. Measure first event, first visible text, first visible tool-call bytes, and total duration separately. Ignore reasoning/keepalive events for visible TTFT. Missing usage is unknown, not zero.
4. **Repairs.** Freeze feedback formatting and a bounded excerpt budget. First-attempt accuracy, conditional repair accuracy, eventual accuracy, and throughput including failures/repairs answer different questions. Include timeouts and parser errors in attempted-trial records.
5. **Tool episodes.** Define the twelve-turn cap as model responses, including empty/error responses; freeze stopping conditions and tool-result ordering. Report cap hits and deadline hits explicitly. They establish failure under the experimental budget, not universal model inability.
6. **Cache and long-context bins.** Repetition creates an intended-warm condition; reported cached-token usage is required to claim a measured cache hit. Save each long-context prompt's bytes, hash, seed, expected answer and planned bin before the call. Report actual token counts without reclassifying failed trials out of their planned bins.
7. **Restrictions and fairness.** Freeze allowed imports, supported Python version, source/output protocol, and validation resource bounds in the prompts. Distinguish restriction failures, extraction/protocol failures, semantic errors, resource kills, truncation and transport interruptions. Apply the same policy to both providers.
8. **Configuration and caps.** Record request parameters actually sent and any returned model/route metadata. A requested effort value does not prove equivalent effective effort. The generous output cap avoids a low artificial truncation threshold; still report all cap hits and separate token use from correctness.

No claims of universal model superiority should be drawn from this sample. Present workload-mix sensitivity and uncertainty alongside the raw dimensions.

## Checks actually executed

- Read PLAN.md in full.
- Listed the benchmark directory; PLAN.md was the only file at review time.
- Computed SHA-256 of PLAN.md: `4f100c64defb39dc866864d40b6dbabc4379efbc639dd2dac760e5f21a6fc327`.

Implementation validation, reference execution, negative controls, and independent adversarial checks are pending the task banks.
