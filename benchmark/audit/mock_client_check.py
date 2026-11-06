"""Pure local protocol checks. No network/config reads; request bodies are synthetic."""
import hashlib
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent / 'client.py'
spec = importlib.util.spec_from_file_location('audited_client', CLIENT)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

def data(delta=None, finish=None, **extra):
    item = {'choices': [{'delta': delta or {}, 'finish_reason': finish}], **extra}
    return 'data: ' + json.dumps(item)

def run_case(lines, deadline=600):
    clock = {'now': 0.0}
    records = []
    class Response:
        status_code = 200
        headers = {'x-magpie-provider': 'opencode-go'}
        def __enter__(self):
            clock['now'] = .01
            return self
        def __exit__(self, *args):
            pass
        def iter_lines(self):
            for elapsed, line in lines:
                clock['now'] = elapsed
                yield line
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def stream(self, *args, **kwargs):
            assert args[0] == 'POST'
            assert kwargs['json']['model'] == client.MODELS['go']
            return Response()
    cfg = json.dumps({'provider': {'magpie': {'options': {'baseURL': 'https://example.invalid', 'apiKey': 'FAKE'}}}})
    with patch.object(client.Path, 'read_text', return_value=cfg), patch.object(client.httpx, 'Client', FakeClient), patch.object(client.time, 'perf_counter', side_effect=lambda: clock['now']), patch.object(client, 'append', side_effect=lambda p, r: records.append(r.copy())), redirect_stdout(io.StringIO()):
        result = client.call('go', [{'role': 'user', 'content': 'synthetic'}], trial_id='audit-only', phase='audit-only', deadline=deadline)
    assert len(records) == 3
    assert records[0]['event'] == 'started'
    assert records[-1]['event'] == 'terminal'
    assert records[0]['attempt_id'] == result['attempt_id'] == records[-1]['attempt_id']
    return result

cases = {}
cases['normal'] = run_case([(1, data({'content': 'ok'})), (2, data(finish='stop')), (2.1, 'data: [DONE]')])
cases['missing_done'] = run_case([(1, data({'content': 'ok'})), (2, data(finish='stop'))])
cases['done_without_finish'] = run_case([(1, data({'content': 'ok'})), (2, 'data: [DONE]')])
cases['malformed_tool_args'] = run_case([(1, data({'tool_calls': [{'index': 0, 'id': 'call_1', 'function': {'name': 'read_file', 'arguments': '{'}}]})), (2, data(finish='tool_calls')), (2.1, 'data: [DONE]')])
cases['missing_tool_identity'] = run_case([(1, data({'tool_calls': [{'index': 0, 'function': {'arguments': '{}'}}]})), (2, data(finish='tool_calls')), (2.1, 'data: [DONE]')])
cases['malformed_event_then_valid_stop'] = run_case([(1, 'data: {INVALID'), (2, data({'content': 'ok'})), (3, data(finish='stop')), (3.1, 'data: [DONE]')])
cases['stream_error'] = run_case([(1, data({'content': 'ok'})), (2, data(finish='stop', error={'message': 'synthetic failure'})), (2.1, 'data: [DONE]')])
cases['deadline_literal'] = run_case([(2, data({'content': 'ok'}))], deadline=1)

assert cases['normal']['complete'] is True
assert cases['missing_done']['complete'] is False
assert cases['done_without_finish']['complete'] is False
assert cases['stream_error']['complete'] is False
summary = {
    'client_sha256': hashlib.sha256(CLIENT.read_bytes()).hexdigest(),
    'no_external_calls': True,
    'no_credential_reads': True,
    'cases': {k: {f: v.get(f) for f in ['complete', 'failure_class', 'error', 'malformed_events', 'total_ms']} for k, v in cases.items()},
    'findings': {
        'malformed_tool_args_accepted': cases['malformed_tool_args']['complete'],
        'missing_tool_identity_accepted': cases['missing_tool_identity']['complete'],
        'malformed_event_ignored': cases['malformed_event_then_valid_stop']['complete'],
        'deadline_message_hardcoded': cases['deadline_literal'].get('error') == 'application_deadline_600s',
    },
}
(HERE / 'mock-client-results-fixed.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
