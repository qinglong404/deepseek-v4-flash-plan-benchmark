# Independent streaming-client review

Reviewed source SHA-256 `46394bfb782292bd615f88a5d2450d14df2553efd6a01546541045707b7323ee` before baseline launch. Scope: client.py and updated PLAN.md; no live gateway/API calls, credential reads, or edits outside audit/.

## Findings sent to main

1. **High: invalid tool calls accepted as complete.** A nonempty list suffices; neither tool identity nor JSON argument completeness is validated. Mocked streams with an unterminated `{` argument or missing name/id return `complete=true`. This conflicts with the frozen complete-arguments definition. Validate assembled calls and preserve a protocol-specific failure reason.
2. **High: the 600-second application deadline is not a wall-time deadline.** The clock is checked only after `iter_lines()` yields. A blocked read can overrun by the transport read timeout, and a stream sending partial lines can continue resetting the read timeout while yielding no line. Either enforce a transport cancellation/watchdog deadline or label this as a checked-on-event soft deadline. The message also hardcodes `600s` when another deadline argument is passed.
3. **Medium: malformed events are silently tolerated.** Malformed JSON increments a counter but does not prevent successful completion after a later finish/DONE. Local mock confirmed this. Lost content could change the answer; classify the protocol damage and do not silently treat it as a clean response.
4. **Medium: attempts are recorded only after completion.** A process interruption during a paid call leaves no start record, making silent duplicate calls possible on resume. Append a linked start event immediately before the transport; completed results should reference a unique attempt ID. Started-without-terminal attempts have unknown completion/usage.

## Verification performed

Executed `python work/magpie-benchmark-v2/audit/mock_client_check.py` using a fake httpx transport, fake configuration reader, fake monotonic clock and in-memory append collector. Eight deterministic cases: normal stop/DONE, missing DONE, missing finish, malformed tool arguments, missing tool identity, malformed event followed by valid stop/DONE, error event, and alternate deadline. Normal, missing-DONE, missing-finish and stream-error outcomes behaved as expected. Results saved in mock-client-results.json.

The deadline overrun is a source/control-flow finding; no real-time 600-second test was run. No provider behavior is inferred from these mocks. Streaming protocol variants, real timing and route-header presence remain live-integration questions for the main runner.
