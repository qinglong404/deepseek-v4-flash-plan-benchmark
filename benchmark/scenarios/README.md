# Frozen repository/context assets

`bank.py` version `repository-context-bank-v2.1` contains no model calls,
credentials, real-project fixtures, or external service dependencies.

## Interface

- `repositories()` returns fresh `{id, prompt, files, write_paths}` dictionaries.
  Give ONLY these initial files and prompts to the model, not this bank module.
- `grade_repository(id, files)` grades the supplied source strings in memory and
  returns `{passed, total, checks}`; loading errors also include `error`. Each
  check has `name`, `ok`, and optionally a bounded `error`. The grader never
  executes or reads candidate `tests.py`. Models cannot change the hidden checks.
- `controls()` returns entries containing `id`, `reference_files`, and
  `negative_controls` (`[{id, files}]`). Keep these maps private to the evaluator.
- `context_case(size_label, seed)` returns `{id, prompt, expected,
  estimated_tokens}`. Accepted sizes are `16K`, `64K`, `160K`, `320K`, case
  insensitive. The estimate is `ceil(characters / 4)`, not a tokenizer result.

Repository `inventory_idempotency` has 40 semantic checks, 3 source files and 5
negative controls. `configuration_overlay` has 62 checks, 3 source files and 5
negative controls. Their references fix all three source files in each case.
Visible `tests.py` examples are provided but remain read-only.

The in-memory loader permits only imports from the enumerated repository source
mapping, restricted builtins/methods, and ordinary Python functions. It rejects
private/frame attributes, reflection, dynamic execution, classes, IO APIs and
non-repository imports. It is an additional restriction, not an OS sandbox.
**Run grading in the parent's resource-limited isolated worker**: nontermination
and excessive allocation still require timeout/CPU/memory controls.

Contexts use seeded nonces at the beginning, 56 meaningful focus-tenant event
records spread from beginning to end, and varied irrelevant-tenant records.
They require 9 exact JSON fields derived using sequence/ID ordering, tombstones,
discard-all conflicting event IDs, exact duplicate elimination, defaults and
aggregations. Identical `(size_label, seed)` yields identical bytes for paired
providers; new seeds alter the nonce, tenant, IDs, values and distractors. Cache
repeats can reuse the exact case. Header/footer mark records as untrusted data.

Author's local validation: both references pass (40/40, 62/62), all 10 negative
controls fail semantic checks, tampering with `tests.py` cannot alter grading,
and 12 contexts (4 sizes × seeds 1/2/3) agree with a separately written
parse/sort/reduce oracle. Parent should rerun independent validation before calls.
