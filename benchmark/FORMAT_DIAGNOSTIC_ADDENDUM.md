# Secondary format diagnostic

Added after first completed core cases exposed a fenced-code response (2026-11-05, Asia/Shanghai). Primary scoring, hidden fixtures, prompts, retries, output settings and all raw outcomes remain unchanged.

The first experiment tolerated a code fence; v2's frozen Python compiler requires raw source. To avoid conflating Python correctness with Markdown wrapping, report a supplemental semantic score using this fixed conservative transformation: only if the entire final response is whitespace plus exactly one blank/python/py-labeled Markdown code block plus whitespace, remove its wrapper and rerun the same immutable validator. If prose or additional fence lines occur, do not select a block or guess the intended code. This diagnostic was not pre-registered, so label it secondary and retain raw strict scores alongside it.

Store one normalized diagnostic per attempt ID in core-extracted-grades.jsonl. Such diagnostics never change model feedback or trigger/skip live retries. Any hypothetical workflow which would auto-strip this wrapper must be identified as a secondary deterministic-normalization view; actual API effort and observed waits remain available separately.
