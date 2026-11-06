# Independent benchmark acceptance

Status: **core banks and isolated grading boundary accepted for the planned comparison**. This is acceptance of the measurement tooling and bounded test bank, not of either provider's performance. The reviewer did not author the bank, client or grader and made no model/API calls or credential reads. All reviewer writes are under audit/.

## What actually ran

| Scope | Independently executed result |
|---|---|
| Frozen coding bank | All twelve references passed all 589 checks; all twelve supplied semantic negatives were rejected. |
| Fresh coding adversaries | A hand-designed check group for every task passed. Additional 100 TTL sequences, 100 allocator sequences, 100 invoice cases, and 100 graphs passed against separately implemented list-order, cell-grid, rational-arithmetic and path-enumeration oracles. These are validator checks, not extra provider quality samples. |
| Repository bank | References passed 40/40 and 62/62 checks; all ten supplied semantic negatives were rejected. Additional stock conservation/replay and configuration overlay/ownership checks passed. |
| Repository loader | tests.py was ignored, external imports were rejected, and public repository import aliases worked. Candidate modules use an in-memory loader rather than disk or sys.path imports. |
| Generated context | Twelve generated cases (four size bins, seeds 0/1/2) matched a separately implemented serialized-JSON oracle; bytes/answers were deterministic and grading was invariant to physical record order. Prompt hashes are recorded. |
| Actual grading boundary | Independently ran 36 bwrap worker executions: fourteen references passed and twenty-two semantic negatives failed. Same filesystem/network/process/environment/resource boundary as main grader; audit-owned input files were the only path difference. |
| Streaming client | Eight mocked protocol cases reran after fixes. Missing finish/DONE, malformed tool arguments/identity, malformed SSE and stream errors are incomplete; valid completion is accepted; start and terminal journal IDs link. |
| Real local deadline | At a 0.25-second deadline, post-header idle and newline-free trickle returned at approximately 0.251 seconds. Trickle before response headers completed returned after 1.014 seconds and was classified as deadline. No upstream was contacted. |

Final semantic-bank checks and actual bwrap runs used `/usr/bin/python3.12`, version 3.12.3. The same local semantic checks also passed on Python 3.13.12 before this matched-runtime rerun.

## Frozen evidence identity

- contracts/bank.py: `a9075dec404a89db11d4c0bee7fbb13cb48543c1c51dcfc2c290ddcf2406df95`
- contracts/fixtures.json: `838247238d6152665e530ffdf93ba31d8e557ecf4a287ef37ef7eb61dca32317`
- scenarios/bank.py: `4d90228d712edd6baef20334b2f909536622bf584545415ecbf942ab878bbe08`
- worker.py: `a743806b09d28a19b88abe34700740ca2493d927dc6a8899221a790f8f8305af`
- client.py at the fixed protocol/deadline test: `2533e9add1d9bae5fa933e41b0f8617465567dcd34f660b763196e9dd244f166`

The audit preserves a snapshot of coding bank and fixtures; original hashes were unchanged after acceptance. The bank's read-only mount and new filesystem/network namespaces resolve the earlier concern that an AST/import allowlist alone cannot prevent on-disk credential access.

## Remaining limits and nonblocking findings

1. Client watchdog is hard after response headers exist. Before headers, timeouts are per transport operation; a continuously trickled header can overrun the application deadline. Main accepted disclosure of this edge. Never claim a strict end-to-end 600-second upper bound.
2. The context oracle's generic private helper uses Python equality for duplicate records, which conflates JSON `true` and `1`. An independent adversarial helper-only check reproduces this; none of the twelve generated prompts contains that ambiguity and all generated expected answers match the strict oracle. This is a reusable-helper limit, not a discovered scoring error in this frozen dataset.
3. The initial grader's failure-label string matcher omitted `not permitted`/`unsupported` and could label restriction errors semantic. Main was notified. This does not change pass rates and can be corrected deterministically during classification without calling providers again.
4. Test banks cover bounded synthetic contracts. They are not an exhaustive proof of arbitrary inputs, performance complexity, secure execution against hostile kernel exploits, tool-use trajectory quality, integration quality, or universal model capability.
5. The reviewer did not verify real provider routing, live usage accounting or live timings. Those require main's request evidence. Parsed usage is authoritative only when supplied; unknown usage cannot be recorded as zero. Statistical units remain task contracts, not assertions or random validator checks.
6. Temperature-zero repetitions estimate repeatability on this bank. Workload choice, shared local network/gateway interference, caching and time of day limit generalization. Keep these dimensions visible in the decision analysis.

## Reproduction artifacts

- check_contracts.py and contract-acceptance-results.json
- check_scenarios.py and scenario-acceptance-results.json
- check_sandbox.py and sandbox-acceptance-results.json
- mock_client_check.py and mock-client-results-fixed.json
- local_deadline_check.py and local-deadline-results.json
- design-review.md and client-review.md (historical findings before fixes)

Earlier source snapshots/findings are retained as history; the positive acceptance above applies to the hashes and final reruns stated here.
