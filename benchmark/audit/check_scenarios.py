"""Independent, local acceptance of scenario bank; no model calls or credentials."""
import copy
import hashlib
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'scenarios' / 'bank.py'
spec = importlib.util.spec_from_file_location('scenario_bank_for_audit', SOURCE)
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)

def independent_answer(records, focus):
    # Canonical serialization makes JSON type distinctions explicit. This
    # implementation applies retained events in sorted order, rather than
    # constructing winner maps as the bank's oracle does.
    groups = {}
    for r in records:
        groups.setdefault(r['event_id'], []).append(r)
    conflicts = sorted(eid for eid, rs in groups.items() if len({json.dumps(r, sort_keys=True, separators=(',', ':')) for r in rs}) > 1 and any(r['tenant'] == focus for r in rs))
    retained = [rs[0] for rs in groups.values() if len({json.dumps(r, sort_keys=True, separators=(',', ':')) for r in rs}) == 1 and rs[0]['tenant'] == focus]
    state = {}
    winners = {}
    for r in sorted(retained, key=lambda x: (x['seq'], x['event_id'])):
        values = state.setdefault(r['sku'], {})
        winners[r['sku'], r['field']] = r['seq']
        if r['op'] == 'del':
            values.pop(r['field'], None)
        else:
            values[r['field']] = r['value']
    active = sorted(k for k, v in state.items() if v.get('active') is True)
    units = {k: max(state[k].get('stock', 0) - state[k].get('reserved', 0), 0) for k in active}
    values = {k: units[k] * state[k].get('price_cents', 0) for k in active}
    return {'active_skus': active, 'available_units': sum(units.values()), 'available_value_cents': sum(values.values()), 'highest_value_sku': sorted(active, key=lambda k: (-values[k], k))[0] if active else None, 'over_reserved_skus': [k for k in active if state[k].get('reserved', 0) > state[k].get('stock', 0)], 'owners': {k: state[k].get('owner') for k in active}, 'restock_needed': sum(max(state[k].get('reorder', 0) - units[k], 0) for k in active), 'most_recent_winner_seq': max(winners.values(), default=0), 'excluded_conflicting_event_ids': conflicts}

results = {'bank_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'version': bank.VERSION, 'python': sys.version, 'no_external_calls': True, 'no_credential_reads': True, 'references': [], 'negative_controls': [], 'independent_repository_checks': [], 'context_checks': [], 'oracle_edges': []}
for control in bank.controls():
    rid = control['id']
    grade = bank.grade_repository(rid, control['reference_files'])
    assert grade['passed'] == grade['total'], (rid, grade)
    results['references'].append({'id': rid, 'passed': grade['passed'], 'total': grade['total']})
    for negative in control['negative_controls']:
        grade = bank.grade_repository(rid, negative['files'])
        assert grade['passed'] < grade['total'], (rid, negative['id'], grade)
        results['negative_controls'].append({'id': rid+'/'+negative['id'], 'passed': grade['passed'], 'total': grade['total'], 'failed': [c['name'] for c in grade['checks'] if not c['ok']]})

    # tests.py must not be executed or used as hidden evaluator input.
    files = copy.deepcopy(control['reference_files'])
    files['tests.py'] = 'raise RuntimeError("test source must not execute")'
    grade = bank.grade_repository(rid, files)
    assert grade['passed'] == grade['total']
    results['independent_repository_checks'].append({'id': rid+'/tests_py_ignored', 'ok': True})

    # Arbitrary imports are rejected, without consulting sys.path or disk.
    files = copy.deepcopy(control['reference_files'])
    target = 'service.py' if rid == 'inventory_idempotency' else 'settings.py'
    files[target] = 'import os\n' + files[target]
    grade = bank.grade_repository(rid, files)
    assert grade.get('error') and 'only repository imports' in grade['error']
    results['independent_repository_checks'].append({'id': rid+'/external_import_rejected', 'ok': True})

    # Public repository imports with conventional aliases are semantically valid.
    # Report loader limitations instead of changing the frozen grading contract.
    if rid == 'inventory_idempotency':
        files = copy.deepcopy(control['reference_files'])
        src = files['service.py']
        src = src.replace('from inventory import validate_identifier, validate_quantity, copy_stock, apply_reservation, apply_refund', 'import inventory as inv')
        for name in ['validate_identifier', 'validate_quantity', 'copy_stock', 'apply_reservation', 'apply_refund']:
            src = re.sub(r'\b'+name+r'\(', 'inv.'+name+'(', src)
        files['service.py'] = src
        grade = bank.grade_repository(rid, files)
        results['independent_repository_checks'].append({'id': rid+'/repository_import_alias', 'ok': grade['passed'] == grade['total'], 'grade': grade})

# Execute references directly through restricted loader and check additional
# valid input/aliasing/boundary behavior independent of the bank's assertions.
inv = bank._load_sources(bank.controls()[0]['reference_files'], ['inventory.py', 'ledger.py', 'service.py'])['service']
state = inv.new_state({' ': 100, 'a': 6})
for i in range(10):
    inv.reserve(state, f'r{i}', ' ', i+1)
for i in range(10):
    inv.refund(state, f'f{i}', f'r{i}', i+1)
assert state['stock'][' '] == 100
assert all(v['qty'] == v['refunded'] for v in state['reservations'].values())
snapshot = copy.deepcopy(state)
for i in range(10):
    inv.refund(state, f'f{i}', f'r{i}', i+1)['remaining'] = -99
assert state == snapshot
results['independent_repository_checks'].append({'id': 'inventory_idempotency/20_operation_full_refund_and_replay', 'ok': True})
cfg = bank._load_sources(bank.controls()[1]['reference_files'], ['parsing.py', 'overlay.py', 'settings.py'])['settings']
base = {'server': {'host': ['invalid'], 'port': None}, 'tags': {'a': None, 'b': ' '}}
layers = [{'server': {'host': ' fixed ', 'port': 80, 'tls': True}}, {'server': {'tls': False}, 'tags': {'a': 'restored', 'b': None}}]
before = copy.deepcopy((base, layers))
output = cfg.build_settings(base, layers, {'APP_WORKERS': ' 00064 ', 'APP_TIMEOUT_MS': ' 0100 '})
assert output == {'server': {'host': 'fixed', 'port': 80, 'tls': False}, 'worker': {'count': 64, 'timeout_ms': 100}, 'tags': {'a': 'restored'}}
assert (base, layers) == before
results['independent_repository_checks'].append({'id': 'configuration_overlay/repaired_types_tombstones_environment_boundary', 'ok': True})

for label in ['16K', '64K', '160K', '320K']:
    for seed in [0, 1, 2]:
        case = bank.context_case(label, seed)
        assert case == bank.context_case(label, seed)
        prompt = case['prompt']
        focus = re.search(r'Process only tenant ([^.]+)\.', prompt).group(1)
        log = prompt.split('BEGIN UNTRUSTED EVENT LOG\n', 1)[1].split('\nEND UNTRUSTED EVENT LOG', 1)[0]
        records = [json.loads(line) for line in log.splitlines()]
        expected = independent_answer(records, focus)
        assert expected == case['expected'], (case['id'], expected, case['expected'])
        shuffled = copy.deepcopy(records)
        random.Random(123).shuffle(shuffled)
        assert bank._context_answer(shuffled, focus) == expected
        results['context_checks'].append({'id': case['id'], 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'chars': len(prompt), 'estimated_tokens': case['estimated_tokens'], 'records': len(records), 'strict_independent_oracle_agrees': True, 'order_invariant': True})

edge = [{'event_id':'same', 'tenant':'focus', 'sku':'a', 'field':'active', 'seq':1, 'op':'set', 'value':True}, {'event_id':'same', 'tenant':'focus', 'sku':'a', 'field':'active', 'seq':1, 'op':'set', 'value':1}]
actual = bank._context_answer(edge, 'focus')
expected = independent_answer(edge, 'focus')
results['oracle_edges'].append({'id':'json_bool_integer_duplicate_distinction', 'ok': actual == expected, 'actual': actual, 'expected': expected, 'affects_generated_cases': False})
edge = [{'event_id':'x', 'tenant':'focus', 'sku':'a', 'field':'active', 'seq':1, 'op':'set', 'value':True}, {'event_id':'x', 'tenant':'other', 'sku':'a', 'field':'active', 'seq':1, 'op':'set', 'value':True}]
assert bank._context_answer(edge,'focus') == independent_answer(edge,'focus')
results['oracle_edges'].append({'id':'conflicting_cross_tenant_duplicate', 'ok': True})

(HERE/'scenario-acceptance-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({k:v for k,v in results.items() if k not in ['negative_controls','context_checks']}, ensure_ascii=False, indent=2))
print('negative controls rejected:', len(results['negative_controls']))
print('generated context cases checked:', len(results['context_checks']))
