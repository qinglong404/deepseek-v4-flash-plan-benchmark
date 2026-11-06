# Frozen coding-contract bank

The bank contains twelve practical Python tasks, 589 named deterministic case
checks, reference solutions and one deliberately flawed solution per task.
Each case can contain a sequence of operations; case counts are diagnostics,
not independent quality samples. Tasks receive equal weight; a task is solved
only when all its cases pass.

## Public API

```python
import bank
bank.tasks()  # [{"id": str, "prompt": str}, ...]
result = bank.grade(task_id, python_source)
# {"passed": bool, "passed_checks": int, "total": int,
#  "checks": [{"name":str, "ok":bool, "error":str?}, ...], "error":str?}
bank.controls()  # {task_id: {"reference": result, "negative": result}}
```

`passed` is a boolean, never a check count. Every check requires the exact
contractual output types and values. Domain errors must raise ValueError. Failed
compile/import/API checks fail all cases. `error` excerpts are bounded for repair
feedback; the caller can further cap diagnostics. Class-state checks record each
feed/finish result or exception, so delayed output and poison-state bugs fail.
Caller-owned arguments are checked for mutation even on exceptions. JSON Patch
and record-resolution outputs are additionally probed for mutable aliasing.

The grader reads **frozen fixtures.json**, and does not execute the references to
compute live expected answers. `freeze.py` is the deterministic authoring tool;
it should not run after live trials begin. `manifest.json` records hashes of the
bank, freezer, fixture file and author control summary. Preserve those hashes in
the benchmark evidence. `author_controls.json` records the author's self-checks:
all 589 reference checks passed and every flawed solution was rejected. This is
not a claim of independent acceptance.

## Execution boundary

Run grading in a separate credential-free worker with the parent's OS-level
CPU/wall-time/memory bounds. The bank's AST/import gate permits only the standard
library modules named in every prompt, omits file/process/network builtins and
rejects disallowed imports, dangerous builtin names and dunder attribute access.
The gate is defense in depth, **not a secure sandbox** against deliberately
malicious Python. Source runs in a module registered for dataclasses/typing.
No reference or validator makes network calls or reads credentials.

The author controls complete in under one second on the authoring host; every
case is small enough for a 15-second CPU / 20-second wall / 768 MiB worker. Python
3.12-compatible syntax is used. The local author execution uses the installed
interpreter; the independent runner should record its exact interpreter version.

## Known measurement limits

- These are synthetic, explicit-contract implementation tasks. They test selected
  engineering semantics and do not measure project discovery, subjective design,
  library integration, domain knowledge or human maintainability.
- Frozen expected values originate in the supplied references. Independent author
  oracles cross-check all allocator cases (cell grid), all shortest-route cases
  (simple-path enumeration), all glob cases (regex plus recursive whole-path
  matching), and concatenated outputs for all SSE cases (whole-stream parser).
  Remaining tasks have boundary and generated cases but no independent author
  oracle; a non-author reviewer/runner must independently audit the bank.
- Random cases use a fixed seed and bounded small inputs. They do not establish
  asymptotic performance or exhaustive correctness for arbitrary size.
- Streaming cases test exact chunk-boundary behavior and state, not real sockets.
- JSON Patch is the prompt's explicit dialect: removing the document root is
  forbidden. Migration and batch conflict rules are intentionally fully defined
  deterministic policies rather than claims of an industry standard.
- Imported safe standard-library modules are real module objects. The worker is
  the required security boundary; do not run untrusted submissions in the main
  credential-bearing process.
