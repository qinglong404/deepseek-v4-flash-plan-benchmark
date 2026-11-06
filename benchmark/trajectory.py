#!/usr/bin/env python3
"""Derive read-only tool-episode trajectories from a JSONL snapshot.

No API calls, credential access, source execution, or changes to benchmark
runners/graders. Only --output is written. All timing quantities called
response_wait_* are sums of recorded model response total_ms / 1000; they are
NOT elapsed human wall time and exclude local tool/grader execution.

Usage:
  python work/magpie-benchmark-v2/trajectory.py --self-check
  python work/magpie-benchmark-v2/trajectory.py

The fixed planned cohort is 2 repositories x 3 repetitions x 2 providers = 12.
Unrecorded episodes remain unknown, rather than receiving zero counts/times.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
PROVIDERS = ("go", "goat")
REPOSITORIES = ("inventory_idempotency", "configuration_overlay")
REPETITIONS = (0, 1, 2)
TOOLS = ("list_files", "read_file", "write_file", "run_tests")
SCHEMA_VERSION = "tool-trajectory-v1"


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def boolean(value):
    return value if type(value) is bool else None


def scalar_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def parse_snapshot(raw):
    """Parse complete JSON objects, reporting malformed/truncated lines explicitly.

    Reading an actively appended file can end within a UTF-8 character or JSON
    line. That trailing fragment is ignored with a warning. Complete malformed
    lines are also surfaced and skipped; they never manufacture an episode.
    """
    rows, warnings = [], []
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("top-level row must be an object")
        except (ValueError, UnicodeDecodeError) as exc:
            trailing = index == len(lines) and not line.endswith((b"\n", b"\r"))
            warnings.append({"kind": "truncated_trailing_line" if trailing else "malformed_line",
                             "line": index, "error": type(exc).__name__ + ": " + str(exc)[:240]})
            continue
        rows.append((index, row))
    return rows, warnings


def _base(provider, repository, repetition):
    row = {"provider": provider, "repository_id": repository, "repetition": repetition,
           "trial_id": f"{repository}-r{repetition}", "record_state": "not_recorded"}
    count_fields = [
        "model_responses", "response_complete_n", "response_incomplete_n", "response_complete_unknown_n",
        "response_deadline_hit_n", "response_wait_unknown_n", "requested_tool_calls_n",
        "recorded_tool_calls_n", "unknown_tool_calls_n", "tool_error_calls_n",
        "successful_write_calls_n", "failed_write_calls_n", "run_tests_passed_n", "run_tests_failed_n",
        "run_tests_unknown_n", "run_tests_error_n", "writes_before_first_passed_test_n",
        "successful_writes_before_first_passed_test_n", "writes_after_first_passed_test_n",
        "successful_writes_after_first_passed_test_n", "failed_tests_after_first_passed_test_n",
        "responses_through_first_write_n", "responses_through_first_passed_test_n",
        "responses_after_first_passed_test_n", "final_grade_passed_checks", "final_grade_total_checks",
        "response_wait_until_first_write_unknown_n", "response_wait_until_first_passed_test_unknown_n",
        "response_wait_after_first_passed_test_unknown_n", "episode_warning_n", "source_line",
        "duplicate_identity_rows_n", "first_write_attempt_turn", "first_write_attempt_trace_index",
        "first_write_turn", "first_write_trace_index", "first_passed_test_turn", "first_passed_test_trace_index",
    ] + [tool + "_calls_n" for tool in TOOLS]
    for name in count_fields:
        row[name] = None
    for name in [
        "response_wait_total_seconds", "response_wait_known_seconds", "recorded_episode_seconds",
        "recorded_minus_derived_seconds", "response_wait_until_first_write_seconds",
        "response_wait_until_first_write_known_seconds", "response_wait_until_first_passed_test_seconds",
        "response_wait_until_first_passed_test_known_seconds", "response_wait_after_first_passed_test_seconds",
        "response_wait_after_first_passed_test_known_seconds", "source_pass", "final_grade_pass",
        "episode_success", "censored", "turn_cap", "last_run_tests_pass", "final_grade_vs_last_tests_agree",
        "final_response_complete", "final_response_has_tool_calls", "termination", "first_response_started",
        "last_response_ended", "response_failure_classes", "response_finish_reason_counts_json", "episode_warnings_json",
    ]:
        row[name] = None
    return row


def _test_outcome(event):
    result = event.get("result")
    if not isinstance(result, dict):
        return None
    if result.get("error"):
        return False
    return boolean(result.get("passed"))


def _successful_write(event):
    result = event.get("result")
    return (event.get("tool") == "write_file" and isinstance(result, dict)
            and isinstance(result.get("written"), str) and not result.get("error"))


def _wait_stats(responses, positions):
    known, unknown = [], 0
    for position in positions:
        milliseconds = responses[position].get("total_ms")
        if numeric(milliseconds) and milliseconds >= 0:
            known.append(milliseconds / 1000)
        else:
            unknown += 1
    known_sum = sum(known)
    return {"seconds": known_sum if unknown == 0 else None,
            "known_seconds": known_sum, "unknown_n": unknown, "response_n": len(positions)}


def summarize_episode(episode, source_line=None, duplicate_rows=0):
    """Return one flat scalar-only row; never confuse final grading with a tool result."""
    warnings = []
    provider, repository, repetition = (episode.get(key) for key in ("provider", "repository_id", "repetition"))
    row = _base(provider, repository, repetition)
    row.update(trial_id=episode.get("trial_id"), record_state="recorded_terminal", source_line=source_line,
               duplicate_identity_rows_n=duplicate_rows)
    raw_responses = episode.get("responses")
    raw_trace = episode.get("trace")
    if not isinstance(raw_responses, list):
        warnings.append("responses is missing or not a list")
        raw_responses = []
    if not isinstance(raw_trace, list):
        warnings.append("trace is missing or not a list")
        raw_trace = []
    responses = [r for r in raw_responses if isinstance(r, dict)]
    trace = [r for r in raw_trace if isinstance(r, dict)]
    if len(responses) != len(raw_responses):
        warnings.append("nondictionary response entries ignored")
    if len(trace) != len(raw_trace):
        warnings.append("nondictionary trace entries ignored")
    if not responses:
        warnings.append("terminal episode has no recorded model responses")

    # Response list order is actual invocation order. Turn metadata maps executed
    # tools to the invocation that emitted them. Missing metadata uses the
    # runner's zero-based position convention, with an explicit warning.
    response_position_by_turn = {}
    for position, response in enumerate(responses):
        metadata = response.get("metadata")
        turn = metadata.get("turn") if isinstance(metadata, dict) else None
        if not integer(turn):
            turn = position
            warnings.append(f"response {position} missing turn metadata; used response position")
        if turn in response_position_by_turn:
            warnings.append(f"duplicate response turn {turn}; event timing is ambiguous")
            response_position_by_turn[turn] = None
        else:
            response_position_by_turn[turn] = position

    total = _wait_stats(responses, list(range(len(responses))))
    row.update(model_responses=len(responses), response_complete_n=sum(r.get("complete") is True for r in responses),
               response_incomplete_n=sum(r.get("complete") is False for r in responses),
               response_complete_unknown_n=sum(type(r.get("complete")) is not bool for r in responses),
               response_deadline_hit_n=sum(bool(r.get("deadline_hit")) for r in responses),
               response_wait_total_seconds=total["seconds"], response_wait_known_seconds=total["known_seconds"],
               response_wait_unknown_n=total["unknown_n"],
               requested_tool_calls_n=sum(len(r["tool_calls"]) for r in responses if isinstance(r.get("tool_calls"), list)),
               recorded_tool_calls_n=len(trace))
    if not responses:
        row["response_wait_total_seconds"] = None
    counts = Counter(str(event.get("tool")) for event in trace)
    for tool in TOOLS:
        row[tool + "_calls_n"] = counts[tool]
    row.update(unknown_tool_calls_n=sum(count for tool, count in counts.items() if tool not in TOOLS),
               tool_error_calls_n=sum(bool(event.get("result", {}).get("error")) for event in trace if isinstance(event.get("result"), dict)))

    writes = [(index, event) for index, event in enumerate(trace) if event.get("tool") == "write_file"]
    successful_writes = [(index, event) for index, event in writes if _successful_write(event)]
    tests = [(index, event) for index, event in enumerate(trace) if event.get("tool") == "run_tests"]
    passing = [(index, event) for index, event in tests if _test_outcome(event) is True]
    row.update(successful_write_calls_n=len(successful_writes), failed_write_calls_n=len(writes)-len(successful_writes),
               run_tests_passed_n=sum(_test_outcome(event) is True for index, event in tests),
               run_tests_failed_n=sum(_test_outcome(event) is False for index, event in tests),
               run_tests_unknown_n=sum(_test_outcome(event) is None for index, event in tests),
               run_tests_error_n=sum(bool(event.get("result", {}).get("error")) for index, event in tests if isinstance(event.get("result"), dict)))
    if writes:
        row["first_write_attempt_trace_index"], event = writes[0]
        row["first_write_attempt_turn"] = event.get("turn")

    def event_wait(event_pair, label):
        if event_pair is None:
            return None
        trace_index, event = event_pair
        turn = event.get("turn")
        row["first_" + label + "_trace_index"] = trace_index
        row["first_" + label + "_turn"] = turn
        position = response_position_by_turn.get(turn) if integer(turn) else None
        if position is None:
            warnings.append(f"first {label} has no unambiguous matching response turn")
            return None
        return position

    write_position = event_wait(successful_writes[0] if successful_writes else None, "write")
    pass_position = event_wait(passing[0] if passing else None, "passed_test")
    if write_position is not None:
        wait = _wait_stats(responses, list(range(write_position + 1)))
        row.update(response_wait_until_first_write_seconds=wait["seconds"],
                   response_wait_until_first_write_known_seconds=wait["known_seconds"],
                   response_wait_until_first_write_unknown_n=wait["unknown_n"], responses_through_first_write_n=wait["response_n"])
    if passing:
        first_index = passing[0][0]
        row.update(writes_before_first_passed_test_n=sum(index < first_index for index, event in writes),
                   successful_writes_before_first_passed_test_n=sum(index < first_index for index, event in successful_writes),
                   writes_after_first_passed_test_n=sum(index > first_index for index, event in writes),
                   successful_writes_after_first_passed_test_n=sum(index > first_index for index, event in successful_writes),
                   failed_tests_after_first_passed_test_n=sum(index > first_index and _test_outcome(event) is False for index, event in tests))
    if pass_position is not None:
        through = _wait_stats(responses, list(range(pass_position + 1)))
        after = _wait_stats(responses, list(range(pass_position + 1, len(responses))))
        row.update(response_wait_until_first_passed_test_seconds=through["seconds"],
                   response_wait_until_first_passed_test_known_seconds=through["known_seconds"],
                   response_wait_until_first_passed_test_unknown_n=through["unknown_n"],
                   responses_through_first_passed_test_n=through["response_n"],
                   response_wait_after_first_passed_test_seconds=after["seconds"],
                   response_wait_after_first_passed_test_known_seconds=after["known_seconds"],
                   response_wait_after_first_passed_test_unknown_n=after["unknown_n"],
                   responses_after_first_passed_test_n=after["response_n"])

    final_grade = episode.get("grade") if isinstance(episode.get("grade"), dict) else {}
    last_tests = _test_outcome(tests[-1][1]) if tests else None
    final_pass = boolean(final_grade.get("passed"))
    passed_checks = final_grade.get("passed_checks")
    if not integer(passed_checks) and isinstance(final_grade.get("checks"), list):
        passed_checks = sum(isinstance(check, dict) and check.get("ok") is True for check in final_grade["checks"])
    row.update(source_pass=boolean(episode.get("source_pass")), final_grade_pass=final_pass,
               final_grade_passed_checks=passed_checks if integer(passed_checks) else None,
               final_grade_total_checks=final_grade.get("total") if integer(final_grade.get("total")) else None,
               episode_success=boolean(episode.get("episode_success")), termination=episode.get("termination"),
               censored=boolean(episode.get("censored")), turn_cap=episode.get("termination") == "turn_cap",
               last_run_tests_pass=last_tests,
               final_grade_vs_last_tests_agree=(final_pass == last_tests if final_pass is not None and last_tests is not None else None))
    recorded = episode.get("seconds")
    row["recorded_episode_seconds"] = recorded if numeric(recorded) and recorded >= 0 else None
    if numeric(recorded) and total["seconds"] is not None:
        row["recorded_minus_derived_seconds"] = recorded - total["seconds"]
        if abs(row["recorded_minus_derived_seconds"]) > .01:
            warnings.append("recorded episode seconds differ from summed response waits by > 0.01 s")
    if responses:
        row.update(final_response_complete=boolean(responses[-1].get("complete")),
                   final_response_has_tool_calls=bool(responses[-1].get("tool_calls")),
                   first_response_started=responses[0].get("started"), last_response_ended=responses[-1].get("ended"))
    row["response_failure_classes"] = " | ".join(sorted({str(r["failure_class"]) for r in responses if r.get("failure_class")}))
    row["response_finish_reason_counts_json"] = scalar_json(dict(Counter(str(r.get("finish_reason")) for r in responses)))
    row["episode_warning_n"] = len(warnings)
    row["episode_warnings_json"] = scalar_json(warnings)
    return row


def _summary(episodes, provider, repository):
    rows = [r for r in episodes if r["provider"] == provider and r["repository_id"] == repository and r["record_state"] == "recorded_terminal"]
    summary = {"provider": provider, "repository_id": repository, "planned_episodes": 3,
               "recorded_episodes": len(rows), "unrecorded_episodes": 3-len(rows),
               "source_passed_n": sum(r["source_pass"] is True for r in rows),
               "episode_succeeded_n": sum(r["episode_success"] is True for r in rows),
               "turn_cap_n": sum(r["turn_cap"] is True for r in rows),
               "response_incomplete_n": sum(r["response_incomplete_n"] or 0 for r in rows),
               "episodes_with_passed_run_tests_n": sum((r["run_tests_passed_n"] or 0) > 0 for r in rows)}
    for name in ("model_responses", "list_files_calls_n", "read_file_calls_n", "write_file_calls_n", "run_tests_calls_n",
                 "run_tests_passed_n", "run_tests_failed_n", "writes_before_first_passed_test_n", "responses_after_first_passed_test_n"):
        known = [r[name] for r in rows if numeric(r.get(name))]
        summary[name + "_known_n"] = len(known)
        summary[name + "_sum"] = sum(known) if known else None
        summary[name + "_mean"] = statistics.mean(known) if known else None
    for name in ("response_wait_total_seconds", "response_wait_until_first_write_seconds",
                 "response_wait_until_first_passed_test_seconds", "response_wait_after_first_passed_test_seconds"):
        known = [r[name] for r in rows if numeric(r.get(name))]
        summary[name + "_known_n"] = len(known)
        summary[name + "_mean"] = statistics.mean(known) if known else None
        summary[name + "_median"] = statistics.median(known) if known else None
        summary[name + "_sum"] = sum(known) if known else None
    return summary


def build(raw, source_path="tool-results.jsonl"):
    parsed, warnings = parse_snapshot(raw)
    by_identity = {}
    identities_seen = Counter()
    for line, episode in parsed:
        identity = (episode.get("provider"), episode.get("trial_id"))
        identities_seen[identity] += 1
        by_identity[identity] = (line, episode)
    planned = {(provider, f"{repo}-r{rep}") for provider in PROVIDERS for repo in REPOSITORIES for rep in REPETITIONS}
    episodes = []
    for repo in REPOSITORIES:
        for rep in REPETITIONS:
            for provider in PROVIDERS:
                identity = (provider, f"{repo}-r{rep}")
                if identity not in by_identity:
                    episodes.append(_base(provider, repo, rep))
                    continue
                line, episode = by_identity[identity]
                if episode.get("repository_id") != repo or episode.get("repetition") != rep:
                    warnings.append({"kind": "cohort_metadata_mismatch", "line": line, "provider": provider, "trial_id": identity[1]})
                episodes.append(summarize_episode(episode, line, identities_seen[identity]-1))
    unplanned = []
    for identity in sorted(set(by_identity)-planned, key=str):
        line, episode = by_identity[identity]
        warnings.append({"kind": "unplanned_episode", "line": line, "identity": list(identity)})
        unplanned.append(summarize_episode(episode, line, identities_seen[identity]-1))
    for identity, n in identities_seen.items():
        if n > 1:
            warnings.append({"kind": "duplicate_episode_identity", "identity": list(identity), "rows": n, "selection": "last valid JSONL row"})
    recorded = sum(r["record_state"] == "recorded_terminal" for r in episodes)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "source_path": str(source_path), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw), "source_valid_rows": len(parsed), "planned_episodes": 12,
        "recorded_episodes": recorded, "unrecorded_episodes": 12-recorded,
        "partial_data": recorded < 12 or bool(warnings),
        "definitions": {
            "response_wait_units": "Recorded model response total_ms / 1000 summed in actual response order; not elapsed human wall time. Excludes local tool execution/grading, gaps and scheduling.",
            "until_event": "Includes the entire model response that emitted the first qualifying tool event. This is observable only at response completion, not exact streamed tool-call onset.",
            "first_write": "First successful write_file result with a written path and no error. First attempted write is separately retained.",
            "first_passed_test": "First executed run_tests event whose result.passed is exactly true with no error. Final hidden source grading is stored separately.",
            "after_first_passed_test": "Only model responses strictly later than the response emitting the first passing test. Tools later in the same response add zero response wait but retain their trace-order counts.",
            "tool_counts": "Executed recorded trace entries; requested_tool_calls_n separately counts response tool calls, including calls not executed after an incomplete response.",
            "write_counts_before_test": "Trace order, not turn order; includes all write attempts. Successful writes have a separate count.",
            "test_failures": "result.passed=false or an error; run_tests_error_n is a subset. Missing/nonboolean passed without error is unknown.",
            "missing_waits": "Unknown total_ms makes that sum null; known partial sums and unknown counts are retained. Missing events yield null timing/count-to-event fields.",
            "pending": "Missing planned episodes have record_state=not_recorded and null counts/times. They may be in flight; absence is not failure.",
            "aggregation": "Summary means/medians use observed terminal episodes and report known denominators; no unrecorded episode is zero-imputed.",
        },
        "warnings": warnings,
        "episodes": episodes,
        "summaries": [_summary(episodes, provider, repo) for repo in REPOSITORIES for provider in PROVIDERS],
        "unplanned_episodes": unplanned,
    }


def self_check():
    """Hand-calculated traces, no model calls, files, subprocesses or clocks."""
    def episode(waits, trace, source=True, termination="final"):
        responses = [{"metadata": {"turn": turn}, "total_ms": None if seconds is None else seconds*1000,
                      "complete": True, "tool_calls": [], "finish_reason": "tool_calls"} for turn, seconds in enumerate(waits)]
        return {"provider": "go", "repository_id": "inventory_idempotency", "repetition": 0,
                "trial_id": "inventory_idempotency-r0", "responses": responses, "trace": trace,
                "source_pass": source, "grade": {"passed": source, "passed_checks": 40 if source else 39, "total": 40},
                "episode_success": source and termination == "final", "termination": termination,
                "censored": termination == "turn_cap", "seconds": sum(w for w in waits if w is not None)}

    def event(turn, tool, result):
        return {"turn": turn, "tool": tool, "result": result}

    e = episode([1, 2, 3, 4, 5], [event(0, "list_files", {}), event(1, "read_file", {}),
                                   event(2, "write_file", {"written": "a.py"}), event(2, "run_tests", {"passed": False}),
                                   event(3, "write_file", {"written": "b.py"}), event(3, "run_tests", {"passed": True})])
    r = summarize_episode(e)
    assert r["response_wait_total_seconds"] == 15
    assert r["response_wait_until_first_write_seconds"] == 6
    assert r["response_wait_until_first_passed_test_seconds"] == 10
    assert r["response_wait_after_first_passed_test_seconds"] == 5
    assert r["writes_before_first_passed_test_n"] == 2
    assert r["run_tests_passed_n"] == r["run_tests_failed_n"] == 1

    e = episode([2, 3], [event(0, "write_file", {"written": "a.py"}), event(0, "run_tests", {"passed": True}),
                          event(0, "write_file", {"written": "a.py"}), event(0, "run_tests", {"passed": False})], source=False)
    r = summarize_episode(e)
    assert r["response_wait_until_first_passed_test_seconds"] == 2 and r["response_wait_after_first_passed_test_seconds"] == 3
    assert r["writes_before_first_passed_test_n"] == 1 and r["writes_after_first_passed_test_n"] == 1
    assert r["failed_tests_after_first_passed_test_n"] == 1
    assert r["source_pass"] is False and r["run_tests_passed_n"] == 1

    e = episode([5], [], source=False, termination="transport_error")
    e["responses"][0].update(complete=False, failure_class="transport_error", tool_calls=[{"function": {"name": "write_file"}}])
    r = summarize_episode(e)
    assert r["requested_tool_calls_n"] == 1 and r["recorded_tool_calls_n"] == 0
    assert r["first_write_turn"] is None and r["response_incomplete_n"] == 1
    assert r["response_failure_classes"] == "transport_error"

    e = episode([1]*12, [event(11, "run_tests", {"passed": True})], termination="turn_cap")
    r = summarize_episode(e)
    assert r["response_wait_until_first_passed_test_seconds"] == 12 and r["response_wait_after_first_passed_test_seconds"] == 0
    assert r["source_pass"] is True and r["episode_success"] is False and r["turn_cap"] is True

    e = episode([None, 2], [event(1, "write_file", {"written": "a.py"})])
    r = summarize_episode(e)
    assert r["response_wait_total_seconds"] is None and r["response_wait_known_seconds"] == 2
    assert r["response_wait_until_first_write_seconds"] is None and r["response_wait_until_first_write_unknown_n"] == 1

    parsed, warnings = parse_snapshot(b'{"provider":"go"}\n{"provider":')
    assert len(parsed) == 1 and warnings[0]["kind"] == "truncated_trailing_line"
    partial = build((json.dumps(e)+"\n").encode())
    assert len(partial["episodes"]) == 12 and partial["recorded_episodes"] == 1
    assert partial["episodes"][1]["model_responses"] is None
    assert all(not isinstance(value, (list, dict)) for row in partial["episodes"] for value in row.values())
    return {"self_check": "passed", "hand_trace_cases": 5, "partial_input_cases": 2, "planned_cohort_rows": 12}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT/"tool-results.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT/"tool-trajectory.json")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        print(scalar_json(self_check()))
        return
    raw = args.input.read_bytes() if args.input.exists() else b""
    result = build(raw, args.input)
    if not args.input.exists():
        result["warnings"].append({"kind": "missing_input_file", "path": str(args.input)})
        result["partial_data"] = True
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(scalar_json({"output": str(args.output), "recorded_episodes": result["recorded_episodes"],
                       "planned_episodes": 12, "partial_data": result["partial_data"], "warnings": len(result["warnings"])}))


if __name__ == "__main__":
    main()
