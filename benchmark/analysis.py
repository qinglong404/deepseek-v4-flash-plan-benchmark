"""Read-only analysis of frozen Magpie v2 result logs; no client/API imports.

Run: python analysis.py [--root RESULT_DIRECTORY] [--draws 10000]
Writes only analysis.json and analysis-summary.txt in the selected directory.
See ANALYSIS_README.md for estimands, pairing, missingness and table schemas.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

PROVIDERS = ('go', 'goat')
LOCAL_TZ = timezone(timedelta(hours=8))
DEFAULT_DRAWS = 10000
SEED = 2026110517
RESTRICTIONS = ('not permitted', 'unsupported',
                'restricted', 'allowlist', 'forbidden', 'blocked', 'disallow', 'not allowed')


def mean(values):
    values = [x for x in values if x is not None]
    return statistics.fmean(values) if values else None


def quantile(values, probability):
    values = sorted(x for x in values if x is not None)
    if not values:
        return None
    index = (len(values)-1)*probability
    lo = math.floor(index)
    hi = math.ceil(index)
    return values[lo] + (values[hi]-values[lo])*(index-lo)


def safe_ratio(numerator, denominator):
    return numerator/denominator if numerator is not None and denominator is not None and denominator > 0 else None


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def seconds(row, key='total_ms'):
    value = number(row.get(key))
    return value/1000 if value is not None else None


def grouped(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k) for k in keys)].append(row)
    return groups


def unique_latest(rows, keys):
    return list({tuple(row.get(k) for k in keys): row for row in rows}.values())


def summarize_numbers(values, prefix):
    known = [x for x in values if x is not None]
    return {prefix+'_n': len(known), prefix+'_missing': len(values)-len(known),
            prefix+'_mean': mean(known), prefix+'_p50': quantile(known,.5),
            prefix+'_p90': quantile(known,.9), prefix+'_p95': quantile(known,.95),
            prefix+'_min': min(known) if known else None,
            prefix+'_max': max(known) if known else None,
            prefix+'_sum': sum(known) if known else None}


def latency_summary(rows, prefix=''):
    out = {}
    for field in ('total_seconds','first_visible_seconds','first_event_seconds'):
        out.update(summarize_numbers([r.get(field) for r in rows], prefix+field))
    return out


def token_summary(rows, prefix=''):
    out = {}
    for field in ('input_tokens','cached_tokens','output_tokens','reasoning_tokens','reasoning_chars','estimated_list_equivalent_usd'):
        values = [r.get(field) for r in rows]
        known = [v for v in values if v is not None]
        out[prefix+field+'_known_sum'] = sum(known) if known else None
        out[prefix+field+'_mean'] = mean(known)
        out[prefix+field+'_unknown_n'] = len(values)-len(known)
    return out


def bootstrap(clusters, statistic, name, draws=DEFAULT_DRAWS):
    """Resample entire paired clusters, preserving within-cluster repeated trials."""
    keys = sorted(clusters)
    data = [clusters[k] for k in keys]
    estimate = statistic(data) if data else None
    result = {'estimate': estimate, 'ci_low': None, 'ci_high': None,
              'n_clusters': len(keys), 'n_pairs': sum(len(x) for x in data),
              'draws_requested': draws, 'draws_valid': 0,
              'resampling_unit': 'whole paired task/dataset cluster', 'seed': SEED}
    if len(keys) < 2:
        result['ci_note'] = 'At least two observed clusters required; no CI reported.'
        return result
    salt = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], 'big')
    rng = random.Random(SEED+salt)
    samples = []
    for _ in range(draws):
        sampled = [data[rng.randrange(len(data))] for _ in data]
        value = statistic(sampled)
        if value is not None and math.isfinite(value):
            samples.append(value)
    result.update(ci_low=quantile(samples,.025), ci_high=quantile(samples,.975), draws_valid=len(samples),
                  undefined_draws_n=draws-len(samples))
    if len(samples) < draws:
        result.update(conditional_finite_ci_low=result['ci_low'],conditional_finite_ci_high=result['ci_high'],ci_low=None,ci_high=None)
        result['ci_note'] = 'Nominal CI suppressed because some resamples are undefined. Conditional finite quantiles are diagnostic only, not an unconditional 95% interval.'
    return result


def quality_difference(data, field):
    # Equal task weight, then equal observed repetitions within task.
    return mean([mean([float(p['goat'][field])-float(p['go'][field]) for p in cluster]) for cluster in data])


def geometric_latency_ratio(data, time_field):
    means = [mean([math.log(p['goat'][time_field]/p['go'][time_field]) for p in cluster]) for cluster in data]
    average = mean(means)
    return math.exp(average) if average is not None else None


def throughput_ratio(data, success_field='solved', time_field='workflow_seconds'):
    flat = [pair for cluster in data for pair in cluster]
    rates = {}
    for provider in PROVIDERS:
        good = sum(p[provider][success_field] for p in flat)
        duration = sum(p[provider][time_field] for p in flat)
        rates[provider] = safe_ratio(good,duration)
    return safe_ratio(rates.get('goat'),rates.get('go'))


def throughput_state(data,success_field='solved',time_field='workflow_seconds'):
    flat=[p for cluster in data for p in cluster]
    if not flat:
        return 'no_matched_data'
    good={p:sum(pair[p][success_field] for pair in flat) for p in PROVIDERS}
    duration={p:sum(pair[p][time_field] for pair in flat) for p in PROVIDERS}
    if not all(duration[p]>0 for p in PROVIDERS):
        return 'undefined_time_denominator'
    if good['go']==0:
        return 'positive_infinity_GOAT_positive_Go_zero' if good['goat']>0 else 'undefined_both_zero_correct'
    return 'finite'


def add_direction(result, direction, formula):
    return dict(result, direction=direction, formula=formula)


def load_jsonl(root, name, warnings):
    path = root/name
    if not path.exists():
        return []
    rows = []
    for index,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row,dict):
                raise ValueError('not an object')
            rows.append(row)
        except (ValueError,TypeError) as exc:
            warnings.append(f'{name}:{index}: skipped unreadable/incomplete JSONL row ({type(exc).__name__}).')
    return rows


def load_object(root,name,warnings):
    path=root/name
    if not path.exists():
        return {}
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict):
            raise ValueError('not an object')
        return value
    except (ValueError,TypeError) as exc:
        warnings.append(f'{name}: unreadable JSON object ({type(exc).__name__}); no administrative exclusions inferred.')
        return {}


def normalize_grade(grade, response=None):
    if not grade:
        return None, None
    raw = grade.get('failure_class')
    if grade.get('passed'):
        return raw, None
    if response and not response.get('complete'):
        return raw, request_record(response)['failure_class_normalized']
    diagnostics = [str(grade.get('error') or '')]
    diagnostics += [str(c.get('error') or '') for c in grade.get('checks',[]) if not c.get('ok')]
    text = '\n'.join(diagnostics).lower()
    if any(term in text for term in RESTRICTIONS):
        return raw, 'restriction'
    if raw in ('resource','grader_error'):
        return raw, raw
    if 'syntaxerror' in text or 'indentationerror' in text or 'taberror' in text:
        if response and whole_fenced_source(response.get('content','')) is not None:
            return raw, 'format'
        return raw, 'syntax'
    return raw, raw or 'semantic'


def whole_fenced_source(content):
    """Detect the exact conservative extraction rule; do not execute/regrade."""
    match = re.fullmatch(r'\s*```(?:python|py)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*\s*',content)
    if not match or re.search(r'(?m)^[ \t]*```',match.group(1)):
        return None
    return match.group(1)


def usage_fields(row):
    usage = row.get('usage') or {}
    prompt_details = usage.get('prompt_tokens_details') or {}
    completion_details = usage.get('completion_tokens_details') or {}
    opencode = usage.get('opencode') or {}
    secondary = opencode.get('tokens') or {}
    def pick(*values):
        return next((number(v) for v in values if number(v) is not None),None)
    inp = pick(usage.get('prompt_tokens'),usage.get('input_tokens'),secondary.get('input'))
    out = pick(usage.get('completion_tokens'),usage.get('output_tokens'),secondary.get('output'))
    cached = pick(prompt_details.get('cached_tokens'),usage.get('prompt_cache_hit_tokens'),secondary.get('cache_read'))
    reasoning = pick(completion_details.get('reasoning_tokens'),usage.get('reasoning_tokens'),secondary.get('reasoning'))
    return {'input_tokens':inp,'cached_tokens':cached,'uncached_input_tokens':inp-cached if inp is not None and cached is not None and 0 <= cached <= inp else None,
            'output_tokens':out,'reasoning_tokens':reasoning,
            'cache_fraction':safe_ratio(cached,inp),
            'usage_known':bool(inp is not None and out is not None),
            'cost_usage_known':bool(inp is not None and out is not None and cached is not None and 0 <= cached <= inp),
            'cache_state':'unknown' if cached is None else ('reported_cache_hit' if cached>0 else 'reported_zero_cache')}


def parse_time(text):
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace('Z','+00:00'))
        return parsed.replace(tzinfo=LOCAL_TZ) if parsed.tzinfo is None else parsed.astimezone(LOCAL_TZ)
    except (ValueError,TypeError,AttributeError):
        return None


def request_record(row):
    usage = usage_fields(row)
    stamp = parse_time(row.get('started'))
    peak = stamp is not None and stamp.weekday()<5 and (9<=stamp.hour<12 or 14<=stamp.hour<18)
    period = ('peak' if peak else 'off_peak') if stamp is not None else 'unknown'
    rates = (.30,.006,1.20) if peak else (.15,.003,.60)
    cost = None
    if stamp is not None and usage['cost_usage_known']:
        cost = (usage['uncached_input_tokens']*rates[0]+usage['cached_tokens']*rates[1]+usage['output_tokens']*rates[2])/1_000_000
    metadata = row.get('metadata') or {}
    headers = row.get('response_headers') or {}
    if row.get('complete'):
        normalized_failure=None
    elif row.get('deadline_hit'):
        normalized_failure='deadline'
    elif isinstance(row.get('status'),int) and row['status']>=400:
        normalized_failure='http_error'
    elif row.get('error') or row.get('stream_error'):
        normalized_failure='transport'
    else:
        normalized_failure=row.get('failure_class') or 'incomplete_protocol'
    return {'attempt_id':row.get('attempt_id'),'provider':row.get('provider'),'phase':row.get('phase'),
            'trial_id':row.get('trial_id'),'started':row.get('started'),'ended':row.get('ended'),
            'effort':row.get('effort_requested'),'concurrency_per_provider':metadata.get('concurrency_per_provider'),
            'complete':bool(row.get('complete')),'failure_class_raw':row.get('failure_class'),
            'failure_class_normalized':normalized_failure,
            'status':row.get('status'),'finish_reason':row.get('finish_reason'),'done':bool(row.get('done')),
            'route_verified':bool(row.get('route_verified')),'route_provider':headers.get('x-magpie-provider'),
            'model_requested':row.get('model_requested'),'route_model':headers.get('x-magpie-model'),
            'models_seen':' | '.join(row.get('models_seen') or []),
            'deadline_hit':bool(row.get('deadline_hit')),'malformed_events':row.get('malformed_events',0),
            'stream_error':bool(row.get('stream_error')),'first_visible_seconds':seconds(row,'first_visible_ms'),
            'first_event_seconds':seconds(row,'first_event_ms'),'first_text_seconds':seconds(row,'first_text_ms'),
            'total_seconds':seconds(row),'reasoning_chars':number(row.get('reasoning_chars')),
            'pricing_period':period,'local_started':stamp.isoformat() if stamp else None,
            'estimated_list_equivalent_usd':cost, **usage}


def paired_rows(rows, key):
    by_trial = defaultdict(dict)
    for row in rows:
        by_trial[row[key]][row['provider']] = row
    return [pair for _,pair in sorted(by_trial.items()) if all(p in pair for p in PROVIDERS)]


def summarize_core(results, first_grades, raw_requests, draws, extraction_diagnostics=None, phase_prefix='core', planned_trials=36):
    requests = {(r.get('provider'),r.get('trial_id'),r.get('phase')):r for r in raw_requests}
    workflows = {(r.get('provider'),r.get('trial_id')):r for r in results}
    starts = {(r.get('provider'),r.get('trial_id')):r for r in first_grades}
    extraction = {r.get('attempt_id'):r for r in (extraction_diagnostics or [])}
    terminal_first_ids={(r.get('provider'),r.get('trial_id')) for r in raw_requests if r.get('phase')==phase_prefix+'_first'}
    identities = sorted(set(workflows)|set(starts)|terminal_first_ids)
    trials=[]
    for identity in identities:
        row=workflows.get(identity); initial=starts.get(identity)
        provider,trial=identity
        first=(row or {}).get('first') or requests.get((provider,trial,phase_prefix+'_first')) or {}
        fg=(row or {}).get('first_grade') or (initial or {}).get('grade')
        repair=(row or {}).get('repair') or requests.get((provider,trial,phase_prefix+'_repair'))
        rg=(row or {}).get('repair_grade')
        first_pass=bool(fg.get('passed')) if fg is not None else None
        terminal=bool(row) or first_pass is True
        solved=bool(row['solved']) if row else (True if first_pass else None)
        raw_first,norm_first=normalize_grade(fg,first)
        raw_repair,norm_repair=normalize_grade(rg,repair)
        first_req=request_record(first)
        repair_req=request_record(repair) if repair else None
        task=(row or initial or {}).get('task_id') or (first.get('metadata') or {}).get('task_id')
        repetition=(row or {}).get('repetition',(first.get('metadata') or {}).get('repetition'))
        out={'provider':provider,'trial_id':trial,'task_id':task,'repetition':repetition,
             'first_attempt_id':first.get('attempt_id'),'first_pass':first_pass,'first_complete':bool(first.get('complete')),
             'first_failure_raw':raw_first,'first_failure_normalized':norm_first,
             'first_seconds':seconds(first),'first_visible_seconds':seconds(first,'first_visible_ms'),
             'first_event_seconds':seconds(first,'first_event_ms'),'first_grade_checks':fg.get('total') if fg else None,
             'first_passed_checks':fg.get('passed_checks') if fg else None,
             'repair_attempted':bool(repair),'repair_attempt_id':(repair or {}).get('attempt_id'),
             'repair_pass':bool(rg.get('passed')) if rg is not None else None,
             'repair_complete':bool(repair.get('complete')) if repair else None,
             'repair_failure_raw':raw_repair,'repair_failure_normalized':norm_repair,
             'repair_seconds':seconds(repair) if repair else None,
             'workflow_terminal':terminal,'solved':solved,
             'workflow_seconds':number(row.get('total_seconds')) if row else (seconds(first) if first_pass else None)}
        out.update(first_pricing_period=first_req['pricing_period'],first_cache_state=first_req['cache_state'],
                   first_effort=first_req['effort'],first_concurrency_per_provider=first_req['concurrency_per_provider'])
        secondary = []
        for stage,response,primary in [('first',first,first_pass),('repair',repair,out['repair_pass'])]:
            diagnostic=extraction.get((response or {}).get('attempt_id'),{})
            detected=bool(response and whole_fenced_source(response.get('content','')) is not None)
            extracted_grade=diagnostic.get('extracted_code_grade') if detected and diagnostic.get('extraction_rule')=='single_whole_fenced_block_v1' else None
            extracted_pass=bool(extracted_grade.get('passed')) if extracted_grade is not None else None
            after=extracted_pass if detected else primary
            out[stage+'_extraction_detected']=detected
            out[stage+'_extraction_rule']=diagnostic.get('extraction_rule')
            out[stage+'_extracted_pass']=extracted_pass
            out[stage+'_after_conservative_extraction_pass']=after
            out[stage+'_extracted_failure_normalized']=normalize_grade(extracted_grade)[1]
            out[stage+'_extracted_passed_checks']=extracted_grade.get('passed_checks') if extracted_grade else None
            out[stage+'_extracted_total_checks']=extracted_grade.get('total') if extracted_grade else None
            if response:
                secondary.append(after)
        out['workflow_after_conservative_extraction_solved']=(True if any(x is True for x in secondary) else False if terminal and all(x is not None for x in secondary) else None)
        norm_first=out['first_after_conservative_extraction_pass']
        out['auto_strip_solved']=(True if norm_first is True else out['workflow_after_conservative_extraction_solved'] if norm_first is False and terminal else None)
        out['auto_strip_seconds']=(out['first_seconds'] if norm_first is True else out['workflow_seconds'] if norm_first is False and terminal else None)
        for field in ('input_tokens','cached_tokens','output_tokens','reasoning_tokens','reasoning_chars','estimated_list_equivalent_usd'):
            out['first_'+field]=first_req[field]
            out['repair_'+field]=repair_req[field] if repair_req else None
            amounts=[first_req[field]]+([repair_req[field]] if repair_req else [])
            out['workflow_'+field]=sum(amounts) if terminal and all(v is not None for v in amounts) else None
        trials.append(out)
    task_rows=[]
    for (task,provider),rows in sorted(grouped(trials,['task_id','provider']).items()):
        first=[r for r in rows if r['first_pass'] is not None]
        terminal=[r for r in rows if r['workflow_terminal']]
        repaired=[r for r in rows if r['repair_pass'] is not None]
        record={'task_id':task,'provider':provider,'n_trials_observed':len(rows),'n_first_graded':len(first),
                'n_workflows_terminal':len(terminal),'n_workflows_pending':len(rows)-len(terminal),
                'first_passed':sum(r['first_pass'] for r in first),'first_pass_rate':mean([r['first_pass'] for r in first]),
                'solved':sum(bool(r['solved']) for r in terminal),'solved_rate':mean([r['solved'] for r in terminal]),
                'repair_attempts':sum(r['repair_attempted'] for r in rows),'repair_graded':len(repaired),
                'repair_passed':sum(r['repair_pass'] for r in repaired),'repair_success_rate':mean([r['repair_pass'] for r in repaired]),
                'first_seconds_mean':mean([r['first_seconds'] for r in first]),
                'first_seconds_p50':quantile([r['first_seconds'] for r in first],.5),
                'workflow_seconds_mean':mean([r['workflow_seconds'] for r in terminal]),
                'workflow_seconds_sum':sum(r['workflow_seconds'] for r in terminal if r['workflow_seconds'] is not None),
                'first_complete_rate':mean([r['first_complete'] for r in first])}
        record.update(first_after_extraction_known_n=sum(r['first_after_conservative_extraction_pass'] is not None for r in first),
                      first_after_extraction_pass_rate=mean([r['first_after_conservative_extraction_pass'] for r in first]),
                      solved_after_extraction_known_n=sum(r['workflow_after_conservative_extraction_solved'] is not None for r in terminal),
                      solved_after_extraction_rate=mean([r['workflow_after_conservative_extraction_solved'] for r in terminal]))
        counterfactual=[r for r in rows if r['auto_strip_solved'] is not None and r['auto_strip_seconds'] is not None]
        record.update(auto_strip_known_n=len(counterfactual),auto_strip_solved_rate=mean([r['auto_strip_solved'] for r in counterfactual]),
                      auto_strip_seconds_mean=mean([r['auto_strip_seconds'] for r in counterfactual]))
        for label in ('first','workflow'):
            pop=first if label=='first' else terminal
            for field in ('input_tokens','cached_tokens','output_tokens','reasoning_tokens','reasoning_chars','estimated_list_equivalent_usd'):
                values=[r.get(label+'_'+field) for r in pop]
                record[label+'_'+field+'_known_sum']=sum(v for v in values if v is not None) if any(v is not None for v in values) else None
                record[label+'_'+field+'_unknown_n']=sum(v is None for v in values)
        task_rows.append(record)
    summaries=[]
    for provider in PROVIDERS:
        rows=[r for r in trials if r['provider']==provider]
        tasks=[r for r in task_rows if r['provider']==provider]
        first=[r for r in rows if r['first_pass'] is not None]
        done=[r for r in rows if r['workflow_terminal']]
        summaries.append({'provider':provider,'planned_tasks':12,'planned_trials':planned_trials,'observed_tasks':len(tasks),
                          'first_graded_trials':len(first),'workflow_terminal_trials':len(done),'workflow_pending_trials':len(rows)-len(done),
                          'first_pass_macro':mean([r['first_pass_rate'] for r in tasks]),
                          'solved_macro':mean([r['solved_rate'] for r in tasks]),
                          'first_passed_trials':sum(r['first_pass'] for r in first),
                          'solved_trials':sum(bool(r['solved']) for r in done),
                          'first_mean_seconds_macro':mean([r['first_seconds_mean'] for r in tasks]),
                          'workflow_mean_seconds_macro':mean([r['workflow_seconds_mean'] for r in tasks]),
                          'workflow_total_seconds':sum(r['workflow_seconds'] for r in done if r['workflow_seconds'] is not None),
                          'workflow_correct_per_minute':safe_ratio(sum(bool(r['solved']) for r in done)*60,sum(r['workflow_seconds'] for r in done if r['workflow_seconds'] is not None)),
                          'repair_attempts':sum(r['repair_attempted'] for r in rows),
                          'repair_graded':sum(r['repair_pass'] is not None for r in rows),
                          'repair_successes':sum(r['repair_pass'] is True for r in rows)})
        summaries[-1].update(first_after_extraction_macro=mean([r['first_after_extraction_pass_rate'] for r in tasks]),
                             solved_after_extraction_macro=mean([r['solved_after_extraction_rate'] for r in tasks]),
                             first_after_extraction_known_trials=sum(r['first_after_conservative_extraction_pass'] is not None for r in first),
                             first_fenced_trials=sum(r['first_extraction_detected'] for r in first),
                             first_fenced_diagnostics_available=sum(r['first_extracted_pass'] is not None for r in first))
    all_pairs=paired_rows(trials,'trial_id')
    first_pairs=[p for p in all_pairs if all(p[x]['first_pass'] is not None for x in PROVIDERS)]
    workflow_pairs=[p for p in all_pairs if all(p[x]['workflow_terminal'] and p[x]['workflow_seconds'] is not None and p[x]['workflow_seconds']>0 for x in PROVIDERS)]
    def clusters(pairs):
        out=defaultdict(list)
        for pair in pairs:out[pair['go']['task_id']].append(pair)
        return dict(out)
    first_clusters=clusters(first_pairs);workflow_clusters=clusters(workflow_pairs)
    first_correct=clusters([p for p in first_pairs if all(p[x]['first_pass'] and p[x]['first_seconds'] is not None and p[x]['first_seconds']>0 for x in PROVIDERS)])
    workflow_correct=clusters([p for p in workflow_pairs if all(p[x]['solved'] for x in PROVIDERS)])
    metrics={
        'first_pass_difference_goat_minus_go':add_direction(bootstrap(first_clusters,lambda d:quality_difference(d,'first_pass'),'core-first',draws),'positive favors GOAT','mean_task(mean_rep(pass_GOAT-pass_Go))'),
        'solved_difference_goat_minus_go':add_direction(bootstrap(workflow_clusters,lambda d:quality_difference(d,'solved'),'core-solved',draws),'positive favors GOAT','mean_task(mean_rep(solved_GOAT-solved_Go))'),
        'first_correct_latency_ratio_goat_over_go':add_direction(bootstrap(first_correct,lambda d:geometric_latency_ratio(d,'first_seconds'),'core-first-time',draws),'above 1 favors Go','exp(mean_task(mean_rep(log(first_seconds_GOAT/first_seconds_Go)))); both first attempts correct'),
        'workflow_correct_latency_ratio_goat_over_go':add_direction(bootstrap(workflow_correct,lambda d:geometric_latency_ratio(d,'workflow_seconds'),'core-workflow-time',draws),'above 1 favors Go','exp(mean_task(mean_rep(log(workflow_seconds_GOAT/workflow_seconds_Go)))); both workflows solved'),
        'useful_throughput_ratio_goat_over_go':add_direction(bootstrap(workflow_clusters,throughput_ratio,'core-throughput',draws),'above 1 favors GOAT','(sum solved_GOAT/sum seconds_GOAT)/(sum solved_Go/sum seconds_Go), matched terminal workflows including failures')}
    metrics['useful_throughput_ratio_goat_over_go']['estimate_state']=throughput_state(list(workflow_clusters.values()))
    normalized_first_pairs=[p for p in all_pairs if all(p[x]['first_after_conservative_extraction_pass'] is not None for x in PROVIDERS)]
    normalized_solved_pairs=[p for p in all_pairs if all(p[x]['workflow_terminal'] and p[x]['workflow_after_conservative_extraction_solved'] is not None for x in PROVIDERS)]
    normalized_correct_pairs=[p for p in normalized_first_pairs if all(p[x]['first_after_conservative_extraction_pass'] and p[x]['first_seconds'] is not None and p[x]['first_seconds']>0 for x in PROVIDERS)]
    auto_pairs=[p for p in all_pairs if all(p[x]['auto_strip_solved'] is not None and p[x]['auto_strip_seconds'] is not None and p[x]['auto_strip_seconds']>0 for x in PROVIDERS)]
    auto_clusters=clusters(auto_pairs)
    secondary_metrics={
        'first_after_extraction_difference_goat_minus_go':add_direction(bootstrap(clusters(normalized_first_pairs),lambda d:quality_difference(d,'first_after_conservative_extraction_pass'),'secondary-first',draws),'positive favors GOAT','posthoc: task-macro normalized first-source correctness difference'),
        'solved_after_extraction_difference_goat_minus_go':add_direction(bootstrap(clusters(normalized_solved_pairs),lambda d:quality_difference(d,'workflow_after_conservative_extraction_solved'),'secondary-solved',draws),'positive favors GOAT','posthoc: task-macro normalized source solved difference after recorded repair'),
        'first_source_correct_latency_ratio_goat_over_go':add_direction(bootstrap(clusters(normalized_correct_pairs),lambda d:geometric_latency_ratio(d,'first_seconds'),'secondary-first-time',draws),'above 1 favors Go','posthoc: geometric mean paired first-call latency, both first sources correct after one conservative wrapper strip'),
        'auto_strip_useful_throughput_ratio_goat_over_go':add_direction(bootstrap(auto_clusters,lambda d:throughput_ratio(d,'auto_strip_solved','auto_strip_seconds'),'counterfactual-throughput',draws),'above 1 favors GOAT','deterministic counterfactual: first-call time when normalized first passes; otherwise recorded workflow time; sum solved/sum seconds'),
        'auto_strip_correct_latency_ratio_goat_over_go':add_direction(bootstrap(clusters([p for p in auto_pairs if all(p[x]['auto_strip_solved'] for x in PROVIDERS)]),lambda d:geometric_latency_ratio(d,'auto_strip_seconds'),'counterfactual-time',draws),'above 1 favors Go','deterministic counterfactual: paired completion latency, both normalized workflows solved')}
    for result in secondary_metrics.values():
        result['analysis_status']='posthoc secondary diagnostic; strict primary unchanged'
    auto_metric=secondary_metrics['auto_strip_useful_throughput_ratio_goat_over_go']
    auto_metric['estimate_state']=throughput_state(list(auto_clusters.values()),'auto_strip_solved','auto_strip_seconds')
    auto_loo=[throughput_ratio([v for k,v in auto_clusters.items() if k!=excluded],'auto_strip_solved','auto_strip_seconds') for excluded in auto_clusters]
    auto_finite=[x for x in auto_loo if x is not None]
    auto_metric.update(leave_one_task_out_min=min(auto_finite) if auto_finite else None,leave_one_task_out_max=max(auto_finite) if auto_finite else None,
                       leave_one_task_out_defined_n=len(auto_finite),leave_one_task_out_total_n=len(auto_loo))
    ltoo=[]
    for excluded in sorted(workflow_clusters):
        subset=[v for k,v in workflow_clusters.items() if k!=excluded]
        ltoo.append({'excluded_task':excluded,'ratio_goat_over_go':throughput_ratio(subset)})
    values=[r['ratio_goat_over_go'] for r in ltoo if r['ratio_goat_over_go'] is not None]
    metrics['useful_throughput_ratio_goat_over_go'].update(leave_one_task_out_min=min(values) if values else None,leave_one_task_out_max=max(values) if values else None)
    metrics['useful_throughput_ratio_goat_over_go'].update(leave_one_task_out_defined_n=len(values),leave_one_task_out_total_n=len(ltoo))
    failures=[]
    for (provider,task),rows in grouped(trials,['provider','task_id']).items():
        for stage in ('first','repair'):
            counter=Counter((r.get(stage+'_failure_raw'),r.get(stage+'_failure_normalized')) for r in rows if r.get(stage+'_failure_normalized'))
            failures += [{'provider':provider,'task_id':task,'stage':stage,'raw':raw,'normalized':norm,'count':count} for (raw,norm),count in counter.items()]
    return {'summary':summaries,'metrics':metrics,'secondary_metrics':secondary_metrics,'paired_first_trials':len(first_pairs),'paired_workflows':len(workflow_pairs),
            'n_task_clusters_first':len(first_clusters),'n_task_clusters_workflow':len(workflow_clusters),
            'effort_stratum':'low supplementary posthoc' if phase_prefix=='low_core' else 'high frozen primary',
            'note':f'Partial-data macro rates use observed task clusters only. Missing/pending trials are not imputed as failures. Stratum design is 12 tasks x {planned_trials//12} trials/provider; case assertions are diagnostic only. Effort strata are never pooled.',
            'extraction_note':'Primary grades, repair inputs and primary CIs remain strict. Secondary after-conservative-extraction fields use externally graded single_whole_fenced_block_v1 only, with no multiple-block selection. Pending wrapper diagnostics are unknown; nonfenced attempts retain their raw grade. Secondary metrics were requested after observing a wrapper violation and are explicitly posthoc. Auto-strip times are deterministic counterfactuals using already measured first-call times when normalized first passes, otherwise recorded workflow times; no new API speed measurement, actual wait unchanged.'}, trials,task_rows,failures,ltoo


def metric_pair_comparison(rows,time_field,name,draws):
    pairs=paired_rows(rows,'trial_id')
    pairs=[p for p in pairs if all(p[x].get(time_field) is not None and p[x][time_field]>0 for x in PROVIDERS)]
    wins=Counter('go' if p['go'][time_field]<p['goat'][time_field] else 'goat' if p['goat'][time_field]<p['go'][time_field] else 'tie' for p in pairs)
    clusters={p['go']['trial_id']:[p] for p in pairs}
    result=bootstrap(clusters,lambda d:geometric_latency_ratio(d,time_field),name,draws)
    result.update(go_wins=wins['go'],goat_wins=wins['goat'],ties=wins['tie'],resampling_unit='serial paired trial',direction='ratio above 1 favors Go')
    return result


def summarize_baseline(results, batch_times, draws):
    rows=[]
    for result in results:
        row=request_record(result);metadata=result.get('metadata') or {}
        row.update(fixture_pass=bool((result.get('grade') or {}).get('passed')),
                   repetition=metadata.get('repetition'),fixture_index=metadata.get('fixture_index'))
        rows.append(row)
    summaries=[]
    for (phase,concurrency,provider),population in sorted(grouped(rows,['phase','concurrency_per_provider','provider']).items(),key=lambda x:str(x[0])):
        summaries.append({'phase':phase,'concurrency_per_provider':concurrency,'provider':provider,'n_requests':len(population),
                          'fixture_passed':sum(r['fixture_pass'] for r in population),'fixture_pass_rate':mean([r['fixture_pass'] for r in population]),
                          'complete_n':sum(r['complete'] for r in population),**latency_summary(population),**token_summary(population)})
    serial=[r for r in rows if r['phase']=='serial']
    serial_pass=[r for r in serial if r['fixture_pass']]
    metrics={}
    for field in ('total_seconds','first_visible_seconds'):
        metrics[field+'_ratio_all_terminal']=metric_pair_comparison(serial,field,'serial-'+field,draws)
        metrics[field+'_ratio_both_fixture_pass']=metric_pair_comparison(serial_pass,field,'serial-pass-'+field,draws)
    pair_rows=[]
    for pair in paired_rows(rows,'trial_id'):
        out={'trial_id':pair['go']['trial_id'],'phase':pair['go']['phase'],
             'concurrency_per_provider':pair['go']['concurrency_per_provider'],
             'go_fixture_pass':pair['go']['fixture_pass'],'goat_fixture_pass':pair['goat']['fixture_pass']}
        for field in ('total_seconds','first_visible_seconds'):
            a,b=pair['go'].get(field),pair['goat'].get(field)
            out['go_'+field]=a;out['goat_'+field]=b;out[field+'_ratio_goat_over_go']=safe_ratio(b,a)
            out[field+'_winner']=None if a is None or b is None else ('go' if a<b else 'goat' if b<a else 'tie')
        pair_rows.append(out)
    batches=[];batch_lookup={r['batch']:r for r in batch_times}
    concurrent=[r for r in rows if r['phase']=='concurrency']
    for (concurrency,repetition,provider),population in sorted(grouped(concurrent,['concurrency_per_provider','repetition','provider']).items(),key=lambda x:str(x[0])):
        start=[parse_time(r.get('started')) for r in population];end=[parse_time(r.get('ended')) for r in population]
        complete_times=all(v is not None for v in start+end)
        wall=(max(end)-min(start)).total_seconds() if complete_times else None
        batch=f'c{concurrency}-r{repetition}'
        shared=batch_lookup.get(batch,{})
        good=sum(r['fixture_pass'] for r in population)
        batches.append({'batch':batch,'provider':provider,'concurrency_per_provider':concurrency,'repetition':repetition,
                        'n_requests':len(population),'fixture_passed':good,'provider_observed_span_seconds':wall,
                        'shared_batch_wall_seconds':shared.get('wall_seconds'),'new_requests_in_shared_record':shared.get('new_requests'),
                        'fixture_correct_per_minute_provider_span':safe_ratio(good*60,wall),**latency_summary(population)})
    return {'summary':summaries,'serial_metrics':metrics,'planned_serial_pairs':12,
            'planned_concurrency_requests_per_provider':14,'planned_concurrency_batches_per_level':2,
            'note':'Serial denotes one stream/provider; the two providers share a paired block/link. Distribution includes all terminal requests; missing visible time is excluded only from that percentile and counted. These baseline times are not pooled into code/context/tool times.'},rows,pair_rows,batches


def summarize_context(results,draws):
    rows=[];fields=[]
    for result in results:
        row=request_record(result);meta=result.get('metadata') or {};grade=result.get('grade') or {}
        row.update(size_label=meta.get('size_label'),seed=meta.get('seed'),estimated_tokens=meta.get('estimated_tokens'),
                   full_json_pass=bool(grade.get('passed')),passed_fields=grade.get('passed_checks'),total_fields=grade.get('total'),
                   json_parse_error=bool(grade.get('error')))
        rows.append(row)
        for check in grade.get('checks',[]):
            fields.append({'trial_id':row['trial_id'],'provider':row['provider'],'size_label':row['size_label'],'seed':row['seed'],
                           'field':check['name'],'semantic_field_pass':bool(check.get('ok')),
                           'complete_field_pass':bool(row['complete'] and check.get('ok')),'response_complete':row['complete']})
    summaries=[]
    for (size,provider),population in sorted(grouped(rows,['size_label','provider']).items(),key=lambda x:str(x[0])):
        subset=[r for r in fields if r['size_label']==size and r['provider']==provider]
        summaries.append({'size_label':size,'provider':provider,'n_datasets':len(population),'full_json_passed':sum(r['full_json_pass'] for r in population),
                          'full_json_pass_rate':mean([r['full_json_pass'] for r in population]),'complete_n':sum(r['complete'] for r in population),
                          'semantic_field_pass_rate':mean([r['semantic_field_pass'] for r in subset]),
                          'complete_field_pass_rate':mean([r['complete_field_pass'] for r in subset]),
                          **summarize_numbers([r['estimated_tokens'] for r in population],'planned_estimated_tokens'),
                          **latency_summary(population),**token_summary(population),
                          **summarize_numbers([r['input_tokens'] for r in population],'actual_input_tokens')})
    field_summaries=[]
    for (size,provider,field),pop in sorted(grouped(fields,['size_label','provider','field']).items(),key=lambda x:str(x[0])):
        field_summaries.append({'size_label':size,'provider':provider,'field':field,'n':len(pop),
                                'semantic_pass_rate':mean([r['semantic_field_pass'] for r in pop]),
                                'complete_pass_rate':mean([r['complete_field_pass'] for r in pop])})
    paired=[];metrics={}
    for size in ['16K','64K','160K','320K']:
        population=[r for r in rows if r['size_label']==size]
        pairs=paired_rows(population,'trial_id')
        clusters={p['go']['trial_id']:[p] for p in pairs}
        quality=bootstrap(clusters,lambda d:quality_difference(d,'full_json_pass'),'context-'+size,draws)
        quality.update(direction='positive favors GOAT',resampling_unit='paired dataset seed')
        times=[p for p in pairs if all(p[x]['total_seconds'] is not None and p[x]['total_seconds']>0 for x in PROVIDERS)]
        latency=bootstrap({p['go']['trial_id']:[p] for p in times},lambda d:geometric_latency_ratio(d,'total_seconds'),'context-time-'+size,draws)
        latency.update(direction='above 1 favors Go',resampling_unit='paired dataset seed; all terminal requests')
        metrics[size]={'full_json_difference_goat_minus_go':quality,'total_latency_ratio_goat_over_go':latency}
        for p in pairs:
            paired.append({'size_label':size,'trial_id':p['go']['trial_id'],'seed':p['go']['seed'],
                           'go_pass':p['go']['full_json_pass'],'goat_pass':p['goat']['full_json_pass'],
                           'go_input_tokens':p['go']['input_tokens'],'goat_input_tokens':p['goat']['input_tokens'],
                           'go_seconds':p['go']['total_seconds'],'goat_seconds':p['goat']['total_seconds'],
                           'latency_ratio_goat_over_go':safe_ratio(p['goat']['total_seconds'],p['go']['total_seconds'])})
    return {'summary':summaries,'metrics_by_size':metrics,'planned_sizes':['16K','64K','160K','320K'],'planned_datasets_per_size':3,
            'note':'Size labels are frozen planned bins, never reassigned from observed token usage. Field checks are correlated diagnostics, not independent samples. Full JSON success additionally requires protocol completeness and exact schema.'},rows,fields,field_summaries,paired


def summarize_tools(results):
    rows=[]
    for result in results:
        response_rows=[request_record(r) for r in result.get('responses',[])]
        grade=result.get('grade') or {};raw,norm=normalize_grade(grade)
        row={'provider':result.get('provider'),'trial_id':result.get('trial_id'),'repository_id':result.get('repository_id'),
             'repetition':result.get('repetition'),'source_pass':bool(result.get('source_pass')),
             'episode_success':bool(result.get('episode_success')),'termination':result.get('termination'),
             'censored':bool(result.get('censored')),'turns':len(response_rows),'tool_calls':len(result.get('trace',[])),
             'tool_errors':result.get('tool_errors',0),'total_seconds':number(result.get('seconds')),
             'transport_incomplete_turns':sum(not r['complete'] for r in response_rows),
             'grade_failure_raw':raw,'grade_failure_normalized':norm,'grade_passed_checks':grade.get('passed_checks'),
             'grade_total_checks':grade.get('total')}
        row.update(token_summary(response_rows))
        rows.append(row)
    summaries=[]
    for (repo,provider),population in sorted(grouped(rows,['repository_id','provider']).items(),key=lambda x:str(x[0])):
        summaries.append({'repository_id':repo,'provider':provider,'n_episodes':len(population),
                          'source_passed':sum(r['source_pass'] for r in population),'source_pass_rate':mean([r['source_pass'] for r in population]),
                          'episode_succeeded':sum(r['episode_success'] for r in population),'episode_success_rate':mean([r['episode_success'] for r in population]),
                          'censored_n':sum(r['censored'] for r in population),'tool_errors_sum':sum(r['tool_errors'] for r in population),
                          'tool_calls_sum':sum(r['tool_calls'] for r in population),
                          **summarize_numbers([r['turns'] for r in population],'turns'),
                          **summarize_numbers([r['total_seconds'] for r in population],'total_seconds')})
    return {'summary':summaries,'planned_repositories':2,'planned_episodes_per_provider':6,
            'note':'source_pass is final hidden semantic grading; episode_success additionally requires a final model response before cap/transport failure. Turn cap is censored, never silently promoted to episode success. Tool times sum model-call times and exclude local tool/grader runtime, matching runner measurement.'},rows


def summarize_requests(raw_requests, journal, draws, interruptions=None):
    interruptions=interruptions or {}
    events={r.get('attempt_id'):r for r in interruptions.get('events',[]) if r.get('administratively_invalidated')}
    excluded=set(interruptions.get('excluded_attempt_ids') or [])|set(events)
    rows=[request_record(r) for r in raw_requests]
    for row in rows:
        row['administratively_invalidated']=row['attempt_id'] in excluded
        row['included_in_primary_workflows']=not row['administratively_invalidated']
        row['administrative_reason']=('collector interruption: '+str(events[row['attempt_id']].get('cause')) if row['attempt_id'] in events else 'paired trial invalidated after collector interruption') if row['administratively_invalidated'] else None
        if row['administratively_invalidated'] and not row['complete']:
            row['failure_class_normalized']='administrative_collector_interruption'
    counter_rows=[]
    for dimension in ['failure_class_normalized','status','route_provider','route_verified','finish_reason','cache_state','pricing_period','administratively_invalidated']:
        counts=Counter((r['provider'],r['phase'],str(r.get(dimension))) for r in rows)
        counter_rows += [{'provider':p,'phase':phase,'dimension':dimension,'value':value,'count':count} for (p,phase,value),count in sorted(counts.items(),key=str)]
    summaries=[]
    for (provider,phase),population in sorted(grouped(rows,['provider','phase']).items(),key=lambda x:str(x[0])):
        summaries.append({'provider':provider,'phase':phase,'n_requests':len(population),'complete_n':sum(r['complete'] for r in population),
                          'failure_n':sum(not r['complete'] and not r['administratively_invalidated'] for r in population),
                          'raw_incomplete_n':sum(not r['complete'] for r in population),
                          'administratively_invalidated_n':sum(r['administratively_invalidated'] for r in population),
                          'route_unverified_n':sum(not r['route_verified'] for r in population),
                          'unknown_usage_n':sum(not r['usage_known'] for r in population),
                          'unknown_cost_usage_n':sum(not r['cost_usage_known'] for r in population),
                          'unknown_cost_estimate_n':sum(r['estimated_list_equivalent_usd'] is None for r in population),
                          **latency_summary(population),**token_summary(population)})
    strata=[]
    for (provider,phase,effort,period,concurrency),population in sorted(grouped(rows,['provider','phase','effort','pricing_period','concurrency_per_provider']).items(),key=lambda x:str(x[0])):
        strata.append({'provider':provider,'phase':phase,'effort':effort,'pricing_period':period,'concurrency_per_provider':concurrency,
                       'n_requests':len(population),'complete_n':sum(r['complete'] for r in population),
                       **latency_summary(population),**token_summary(population)})
    terminal_ids={r.get('attempt_id') for r in raw_requests}
    journal_terminals={r.get('attempt_id') for r in journal if r.get('event')=='terminal'}
    starts={r.get('attempt_id'):r for r in journal if r.get('event')=='started'}
    for attempt_id,event in events.items():
        starts.setdefault(attempt_id,event)
    pending=[];resolved=[]
    for attempt_id,row in starts.items():
        if attempt_id not in terminal_ids:
            out={'attempt_id':attempt_id,'provider':row.get('provider'),'phase':row.get('phase'),'trial_id':row.get('trial_id'),
                 'started':row.get('started'),'journal_terminal_present':attempt_id in journal_terminals,
                 'client_terminal_record_present':False,'client_total_seconds':None,'input_tokens':None,'cached_tokens':None,
                 'output_tokens':None,'reasoning_tokens':None,'estimated_list_equivalent_usd':None}
            if attempt_id in excluded:
                event=events.get(attempt_id,{})
                gateway=event.get('gateway_evidence') or {}
                out.update(state='administratively_resolved_collector_interruption',cause=event.get('cause'),
                           collector_exit_code=event.get('collector_exit_code'),gateway_status=gateway.get('status'),
                           gateway_elapsed_seconds=number(gateway.get('ms'))/1000 if number(gateway.get('ms')) is not None else None,
                           gateway_first_event_seconds=number(gateway.get('ttft_ms'))/1000 if number(gateway.get('ttft_ms')) is not None else None,
                           usage_note='Client usage and timing unknown. Gateway duration/status are separate evidence; gateway zero-token fields are not accepted as measured zero usage.')
                resolved.append(out)
            else:
                out['state']='terminal_result_missing' if attempt_id in journal_terminals else 'in_flight_or_interrupted_unknown'
                pending.append(out)
    overall=[]
    for provider in PROVIDERS:
        population=[r for r in rows if r['provider']==provider]
        overall.append({'provider':provider,'n_terminal_requests':len(population),'complete_n':sum(r['complete'] for r in population),
                        'n_attempts_including_journal_starts':len({r['attempt_id'] for r in population}|{attempt_id for attempt_id,row in starts.items() if row.get('provider')==provider}),
                        'unknown_usage_n':sum(not r['usage_known'] for r in population),
                        'administratively_invalidated_client_terminal_n':sum(r['administratively_invalidated'] for r in population),
                        'administratively_resolved_missing_client_terminal_n':sum(r['provider']==provider for r in resolved),
                        'all_missing_client_terminal_n':sum(r['provider']==provider for r in resolved+pending),
                        'unknown_usage_including_missing_client_n':sum(not r['usage_known'] for r in population)+sum(r['provider']==provider for r in resolved+pending),
                        'unknown_cost_estimate_n':sum(r['estimated_list_equivalent_usd'] is None for r in population),
                        'unknown_cost_estimate_including_missing_client_n':sum(r['estimated_list_equivalent_usd'] is None for r in population)+sum(r['provider']==provider for r in resolved+pending),
                        'unreturned_journal_attempts_n':sum(r['provider']==provider for r in pending),
                        **token_summary(population)})
    return {'provider_totals':overall,'summary':summaries,'unreturned_attempts':pending,
            'raw_unreturned_attempts':pending+resolved,'raw_unreturned_attempts_n':len(pending)+len(resolved),
            'unresolved_unreturned_attempts_n':len(pending),
            'administratively_resolved_missing_client_attempts':resolved,
            'administrative_missing_client_finals_n':len(resolved),'administratively_excluded_attempt_ids':sorted(excluded),
            'administrative_note':'Only explicitly listed interrupted-pair attempt IDs are excluded from primary code workflows; their raw terminal calls and unknown-usage journal starts remain in all-attempt accounting. Administrative collector interruptions are not provider failures. Gateway status/duration never substitute for missing client protocol, latency or usage.',
            'cost_note':'Usage-based USD list-equivalent estimate only, not exact billing or subscription deductions. Request start in Asia/Shanghai selects weekday peak 09:00–12:00 and 14:00–18:00, else off-peak. Per-million input/cache/output: peak 0.30/0.006/1.20, off 0.15/0.003/0.60. Prompt tokens include cached tokens: subtract cache before uncached rate. Completion tokens already include reasoning; never add reasoning a second time. Missing usage/cache/time leaves estimate unknown. Unreturned/interrupted usage can remain unknown.'},rows,counter_rows,strata


def overlapping_failures(rows):
    """Candidates for common disruption; temporal overlap does not establish cause."""
    failures=[r for r in rows if not r['complete']]
    candidates=[]
    for i,a in enumerate(failures):
        for b in failures[i+1:]:
            if a['provider']==b['provider']:
                continue
            sa,ea,sb,eb=[parse_time(t) for t in (a.get('started'),a.get('ended'),b.get('started'),b.get('ended'))]
            if not all((sa,ea,sb,eb)) or max(sa,sb)>min(ea,eb):
                continue
            candidates.append({'attempt_id_a':a['attempt_id'],'provider_a':a['provider'],'phase_a':a['phase'],'failure_a':a['failure_class_normalized'],
                               'attempt_id_b':b['attempt_id'],'provider_b':b['provider'],'phase_b':b['phase'],'failure_b':b['failure_class_normalized'],
                               'overlap_seconds':(min(ea,eb)-max(sa,sb)).total_seconds(),
                               'interpretation':'overlapping incomplete calls; common network cause unproven'})
    return candidates


def observed_concurrency(rows):
    """Timestamp reconstruction over recorded terminal calls, a lower bound while live."""
    intervals=[(i,parse_time(r.get('started')),parse_time(r.get('ended'))) for i,r in enumerate(rows)]
    valid=[(i,start,end) for i,start,end in intervals if start is not None and end is not None and end>start]
    for index,start,end in intervals:
        row=rows[index]
        for scope in ('global','provider'):
            selected=[(i,s,e) for i,s,e in valid if scope=='global' or rows[i]['provider']==row['provider']]
            prefix='observed_recorded_'+scope
            row[prefix+'_streams_at_start']=sum(s<=start<e for _,s,e in selected) if start is not None else None
            if start is None or end is None or end<=start:
                row[prefix+'_max_streams_during_request']=None
                continue
            events=[]
            for _,s,e in selected:
                lo,hi=max(s,start),min(e,end)
                if lo<hi:
                    events.extend([(lo,1),(hi,-1)])
            active=maximum=0
            for _,delta in sorted(events,key=lambda event:(event[0],event[1])):
                active+=delta;maximum=max(maximum,active)
            row[prefix+'_max_streams_during_request']=maximum
    summaries=[]
    for (provider,phase),population in grouped(rows,['provider','phase']).items():
        record={'provider':provider,'phase':phase,'n_requests':len(population)}
        for scope in ('global','provider'):
            key='observed_recorded_'+scope+'_max_streams_during_request'
            record.update(summarize_numbers([r[key] for r in population],key))
        summaries.append(record)
    return summaries


def mix_analysis(core_tasks,context_rows,tool_rows,counterfactual=False):
    """Task-count fractions, not time/token/cost shares. No baseline in this mix."""
    strata=[]
    for provider in PROVIDERS:
        code=[r for r in core_tasks if r['provider']==provider and r['auto_strip_known_n' if counterfactual else 'n_workflows_terminal']]
        context=[r for r in context_rows if r['provider']==provider]
        tools=[r for r in tool_rows if r['provider']==provider]
        for phase,task_rows,pass_field,time_field,cluster in [
            ('code',code,'auto_strip_solved_rate' if counterfactual else 'solved_rate','auto_strip_seconds_mean' if counterfactual else 'workflow_seconds_mean',None),
            ('context',context,'full_json_pass','total_seconds','trial_id'),
            ('tools',tools,'episode_success','total_seconds','repository_id')]:
            if cluster:
                groups=grouped(task_rows,[cluster])
                pass_rate=mean([mean([r[pass_field] for r in group]) for group in groups.values()])
                duration=mean([mean([r[time_field] for r in group]) for group in groups.values()])
                nclusters=len(groups)
            else:
                pass_rate=mean([r[pass_field] for r in task_rows]);duration=mean([r[time_field] for r in task_rows]);nclusters=len(task_rows)
            strata.append({'provider':provider,'stratum':phase,'n_clusters':nclusters,'pass_rate':pass_rate,'mean_seconds':duration})
    lookup={(r['provider'],r['stratum']):r for r in strata}
    grid=[]
    for a in range(0,101,25):
        for b in range(0,101-a,25):
            c=100-a-b;weights={'code':a/100,'context':b/100,'tools':c/100}
            row={'code_weight_pct':a,'context_weight_pct':b,'tools_weight_pct':c}
            for provider in PROVIDERS:
                available=all(weight==0 or (lookup[provider,phase]['pass_rate'] is not None and lookup[provider,phase]['mean_seconds'] is not None) for phase,weight in weights.items())
                good=sum(weight*lookup[provider,phase]['pass_rate'] for phase,weight in weights.items() if weight) if available else None
                duration=sum(weight*lookup[provider,phase]['mean_seconds'] for phase,weight in weights.items() if weight) if available else None
                row[provider+'_weighted_pass_rate']=good;row[provider+'_weighted_mean_seconds']=duration
                row[provider+'_correct_tasks_per_minute']=safe_ratio(None if good is None else 60*good,duration)
            row['throughput_ratio_goat_over_go']=safe_ratio(row['goat_correct_tasks_per_minute'],row['go_correct_tasks_per_minute'])
            grid.append(row)
    return {'formula':'expected_correct_tasks_per_minute = 60 * sum(task_count_weight_s * pass_rate_s) / sum(task_count_weight_s * mean_total_seconds_s)',
            'code_policy':'posthoc deterministic auto-strip counterfactual: use first-call time when conservatively extracted first source passes, otherwise actual workflow time' if counterfactual else 'one initial attempt plus one repair if needed; task-macro solved rate and mean workflow time',
            'context_policy':'one request; exact full-JSON success; dataset-macro rate/time',
            'tools_policy':'one episode; episode_success; repository-macro rate/time',
            'direction':'GOAT/Go throughput > 1 favors GOAT','counterfactual':counterfactual,
            'note':'Sensitivity analysis, not an arbitrary overall winner. Weights are expected task-count fractions, not runtime/token shares. Censored/deadline workflows retain measured capped time and failure. Baseline and prior v1 are excluded. Partial availability is explicit; no uncertainty interval is asserted for this grid. Auto-strip alternative, if selected, is posthoc and deterministic; it does not change actual measured wait.'},strata,grid


def core_pair_tables(trials):
    pairs=[]
    for pair in paired_rows(trials,'trial_id'):
        a,b=pair['go'],pair['goat']
        row={'trial_id':a['trial_id'],'task_id':a['task_id'],'repetition':a['repetition'],
             'go_first_pass':a['first_pass'],'goat_first_pass':b['first_pass'],
             'go_solved':a['solved'],'goat_solved':b['solved'],
             'first_pass_difference':None if a['first_pass'] is None or b['first_pass'] is None else int(b['first_pass'])-int(a['first_pass']),
             'solved_difference':None if a['solved'] is None or b['solved'] is None else int(b['solved'])-int(a['solved']),
             'both_first_correct':a['first_pass'] is True and b['first_pass'] is True,
             'both_workflows_solved':a['solved'] is True and b['solved'] is True}
        for field in ('first_seconds','workflow_seconds'):
            row['go_'+field]=a[field];row['goat_'+field]=b[field]
            row[field+'_ratio_goat_over_go']=safe_ratio(b[field],a[field])
        pairs.append(row)
    summaries=[]
    for (task,),population in sorted(grouped(pairs,['task_id']).items()):
        first=mean([r['first_pass_difference'] for r in population]);solved=mean([r['solved_difference'] for r in population])
        summaries.append({'task_id':task,'n_pairs':len(population),
                          'first_pass_difference_goat_minus_go':first,'solved_difference_goat_minus_go':solved,
                          'first_quality_winner':None if first is None else 'goat' if first>0 else 'go' if first<0 else 'tie',
                          'solved_quality_winner':None if solved is None else 'goat' if solved>0 else 'go' if solved<0 else 'tie',
                          'paired_first_seconds_ratio_geomean':math.exp(mean([math.log(r['first_seconds_ratio_goat_over_go']) for r in population if r['first_seconds_ratio_goat_over_go'] is not None and r['first_seconds_ratio_goat_over_go']>0])) if any(r['first_seconds_ratio_goat_over_go'] is not None and r['first_seconds_ratio_goat_over_go']>0 for r in population) else None})
    return pairs,summaries


def baseline_pair_summaries(pairs):
    out=[]
    for (phase,concurrency),population in sorted(grouped(pairs,['phase','concurrency_per_provider']).items(),key=lambda x:str(x[0])):
        row={'phase':phase,'concurrency_per_provider':concurrency,'n_pairs':len(population),
             'both_fixture_pass_n':sum(r['go_fixture_pass'] and r['goat_fixture_pass'] for r in population)}
        for field in ('total_seconds','first_visible_seconds'):
            wins=Counter(r.get(field+'_winner') for r in population)
            row.update({field+'_'+p+'_wins':wins[p] for p in PROVIDERS})
            row[field+'_ties']=wins['tie'];row[field+'_missing_pairs']=wins[None]
        out.append(row)
    return out


def effort_comparison(high_tasks,low_tasks,draws):
    configurations=[]
    all_rows=[]
    def enrich(row):
        row=dict(row)
        for field in ('reasoning_tokens','output_tokens','input_tokens'):
            row['first_'+field+'_mean']=safe_ratio(row.get('first_'+field+'_known_sum'),row['n_first_graded']-row.get('first_'+field+'_unknown_n',0))
        return row
    enriched={'high':[enrich(r) for r in high_tasks],'low':[enrich(r) for r in low_tasks]}
    for effort,task_rows in enriched.items():
        for provider in PROVIDERS:
            pop=[r for r in task_rows if r['provider']==provider]
            record={'provider':provider,'effort':effort,'n_tasks':len(pop),
                    'n_first_trials':sum(r['n_first_graded'] for r in pop),'n_workflows':sum(r['n_workflows_terminal'] for r in pop),
                    'strict_first_pass_macro':mean([r['first_pass_rate'] for r in pop]),'strict_solved_macro':mean([r['solved_rate'] for r in pop]),
                    'after_extraction_first_pass_macro':mean([r['first_after_extraction_pass_rate'] for r in pop]),
                    'after_extraction_solved_macro':mean([r['solved_after_extraction_rate'] for r in pop]),
                    'first_seconds_mean':mean([r['first_seconds_mean'] for r in pop]),
                    'workflow_seconds_mean':mean([r['workflow_seconds_mean'] for r in pop]),
                    'auto_strip_seconds_mean':mean([r['auto_strip_seconds_mean'] for r in pop]),
                    'first_reasoning_tokens_mean':mean([r['first_reasoning_tokens_mean'] for r in pop]),
                    'first_output_tokens_mean':mean([r['first_output_tokens_mean'] for r in pop]),
                    'analysis_status':'frozen primary high' if effort=='high' else 'hypothesis-driven supplementary low added after early high observations'}
            configurations.append(record)
    lookup={effort:{(r['provider'],r['task_id']):r for r in rows} for effort,rows in enriched.items()}
    fields=('first_pass_rate','solved_rate','first_after_extraction_pass_rate','solved_after_extraction_rate',
            'first_seconds_mean','workflow_seconds_mean','auto_strip_seconds_mean','first_reasoning_tokens_mean','first_output_tokens_mean')
    for provider,task in sorted(set(lookup['high']) & set(lookup['low'])):
        high,low=lookup['high'][provider,task],lookup['low'][provider,task]
        out={'provider':provider,'task_id':task,'high_first_trials':high['n_first_graded'],'low_first_trials':low['n_first_graded']}
        for field in fields:
            out['high_'+field]=high.get(field);out['low_'+field]=low.get(field)
            if field.endswith('rate'):
                out[field+'_low_minus_high']=low[field]-high[field] if low[field] is not None and high[field] is not None else None
            else:
                out[field+'_ratio_low_over_high']=safe_ratio(low[field],high[field])
        all_rows.append(out)
    metrics={}
    for provider in PROVIDERS:
        population=[r for r in all_rows if r['provider']==provider]
        metrics[provider]={}
        for field in fields:
            key=field+('_low_minus_high' if field.endswith('rate') else '_ratio_low_over_high')
            eligible=[r for r in population if r.get(key) is not None and (field.endswith('rate') or r[key]>0)]
            clusters={r['task_id']:[r] for r in eligible}
            def statistic(data, column=key,quality=field.endswith('rate')):
                values=[r[column] for cluster in data for r in cluster]
                center=mean(values if quality else [math.log(v) for v in values])
                return center if quality or center is None else math.exp(center)
            metric=bootstrap(clusters,statistic,'effort-'+provider+'-'+key,draws)
            metric.update(direction='positive favors low quality' if field.endswith('rate') else 'below one means low uses less time/tokens',
                          resampling_unit='whole task, comparing high(3 rep) and low(2 rep) task means',analysis_status='supplementary posthoc; effort and calendar order confounded')
            metrics[provider][key]=metric
    return {'metrics_by_provider':metrics,'planned_tasks':12,'high_planned_trials_per_provider':36,'low_planned_trials_per_provider':24,
            'note':'Descriptive paired-task setting comparison; never pooled into the high primary result. All tasks enter low, not only high failures. High has three repetitions and low two, at later calendar times; settings, cache, load and time can be confounded. Equal nominal effort is not proof of equal reasoning budget. Compare observed quality and measured token/time distributions when choosing a channel configuration; equal observed quality is not statistical equivalence.'},configurations,all_rows


def flat_aggregates(sections):
    rows=[]
    def visit(path,value):
        if isinstance(value,dict):
            for key,item in value.items():visit(path+[str(key)],item)
        elif isinstance(value,(str,int,float,bool)) or value is None:
            rows.append({'metric_path':'.'.join(path),'numeric_value':value if isinstance(value,(int,float)) and not isinstance(value,bool) else None,
                         'text_value':value if isinstance(value,str) else None,'boolean_value':value if isinstance(value,bool) else None})
    for section,value in sections.items():visit([section],value)
    return rows


def build(root,draws=DEFAULT_DRAWS):
    warnings=[]
    names=['requests.jsonl','attempt-journal.jsonl','core-results.jsonl','core-first-grades.jsonl','low-core-results.jsonl','low-core-first-grades.jsonl','core-extracted-grades.jsonl','baseline-results.jsonl','batch-times.jsonl','context-results.jsonl','tool-results.jsonl']
    loaded={name:load_jsonl(root,name,warnings) for name in names}
    interruptions=load_object(root,'collector-interruptions.json',warnings)
    excluded=set(interruptions.get('excluded_attempt_ids') or [])|{r.get('attempt_id') for r in interruptions.get('events',[]) if r.get('administratively_invalidated')}
    def valid_workflow(row):
        return (row.get('first') or {}).get('attempt_id') not in excluded and (row.get('repair') or {}).get('attempt_id') not in excluded
    core=unique_latest([r for r in loaded['core-results.jsonl'] if valid_workflow(r)],['provider','trial_id'])
    first=unique_latest([r for r in loaded['core-first-grades.jsonl'] if r.get('attempt_id') not in excluded],['provider','trial_id'])
    low_core=unique_latest([r for r in loaded['low-core-results.jsonl'] if valid_workflow(r)],['provider','trial_id'])
    low_first=unique_latest([r for r in loaded['low-core-first-grades.jsonl'] if r.get('attempt_id') not in excluded],['provider','trial_id'])
    baseline=unique_latest(loaded['baseline-results.jsonl'],['provider','trial_id','phase'])
    context=unique_latest(loaded['context-results.jsonl'],['provider','trial_id'])
    tools=unique_latest(loaded['tool-results.jsonl'],['provider','trial_id'])
    # Preserve every request attempt, including attempts no longer chosen by a resumed workflow.
    all_code_rows=loaded['core-results.jsonl']+loaded['low-core-results.jsonl']
    embedded=baseline+context+[r['first'] for r in all_code_rows if r.get('first')]+[r['repair'] for r in all_code_rows if r.get('repair')]+[request for episode in tools for request in episode.get('responses',[])]
    requests=unique_latest(embedded+loaded['requests.jsonl'],['attempt_id'])
    requests=[r for r in requests if r.get('provider') in PROVIDERS]
    evaluable_requests=[r for r in requests if r.get('attempt_id') not in excluded]
    core_section,core_trials,core_tasks,core_failures,ltoo=summarize_core(core,first,evaluable_requests,draws,loaded['core-extracted-grades.jsonl'])
    low_section,low_trials,low_tasks,low_failures,low_ltoo=summarize_core(low_core,low_first,evaluable_requests,draws,loaded['core-extracted-grades.jsonl'],'low_core',24)
    effort_section,configurations,effort_task_rows=effort_comparison(core_tasks,low_tasks,draws)
    baseline_section,baseline_trials,baseline_pairs,baseline_batches=summarize_baseline(baseline,loaded['batch-times.jsonl'],draws)
    context_section,context_trials,context_fields,context_field_summaries,context_pairs=summarize_context(context,draws)
    tools_section,tool_trials=summarize_tools(tools)
    request_section,request_records,request_counters,request_strata=summarize_requests(requests,loaded['attempt-journal.jsonl'],draws,interruptions)
    concurrency_rows=observed_concurrency(request_records)
    request_section['observed_concurrency_note']='Timestamp reconstruction uses all recorded terminal calls across phases. It is a lower bound whenever in-flight/administratively interrupted calls lack client terminal times. Nominal concurrency_per_provider is runner metadata, not proof of total simultaneous link/provider load. Half-open intervals exclude calls ending exactly when another begins. Collector recovery metadata, not apparent journal overlap alone, determines administrative interpretation.'
    raw_by_id={r.get('attempt_id'):r for r in requests}
    excluded_grades=[]
    for row in loaded['core-first-grades.jsonl']+loaded['low-core-first-grades.jsonl']:
        if row.get('attempt_id') not in excluded:
            continue
        response=raw_by_id.get(row['attempt_id'],{})
        grade=row.get('grade') or {}
        raw_label,norm_label=normalize_grade(grade,response)
        excluded_grades.append({'attempt_id':row['attempt_id'],'provider':row.get('provider'),'trial_id':row.get('trial_id'),
                                'task_id':row.get('task_id'),'stage':'first','raw_passed':bool(grade.get('passed')),
                                'raw_failure_class':raw_label,'normalized_failure_class':norm_label,
                                'passed_checks':grade.get('passed_checks'),'total_checks':grade.get('total'),
                                'first_failure_diagnostic':next((str(c.get('error',''))[:1500] for c in grade.get('checks',[]) if not c.get('ok')),str(grade.get('error',''))[:1500]),
                                'exclusion_reason':'entire trial pair invalidated after administrative collector interruption; original observed grade retained, not converted to provider failure or success'})
    interrupted_trial=interruptions.get('invalidated_trial')
    recovery_section={'manifest_sha256':hashlib.sha256((root/'collector-interruptions.json').read_bytes()).hexdigest() if (root/'collector-interruptions.json').exists() else None,
                      'invalidated_trial':interrupted_trial,'excluded_attempt_ids':sorted(excluded),
                      'excluded_completed_first_grades':len(excluded_grades),
                      'missing_client_finals_administratively_resolved':request_section['administrative_missing_client_finals_n'],
                      'note':'Recovered fresh pair enters primary under original sampling identity; original returned source failure and all missing-client-final uncertainty remain separately visible. Administrative exclusion is not a provider failure. Sensitivity below drops the entire recovered trial pair to show potential selection influence.'}
    if interrupted_trial:
        sensitivity=summarize_core([r for r in core if r['trial_id']!=interrupted_trial],
                                   [r for r in first if r['trial_id']!=interrupted_trial],
                                   [r for r in evaluable_requests if r.get('trial_id')!=interrupted_trial],draws,loaded['core-extracted-grades.jsonl'])[0]
        recovery_section['sensitivity_drop_recovered_pair']={'summary':sensitivity['summary'],'metrics':sensitivity['metrics'],
                                                           'secondary_metrics':sensitivity['secondary_metrics'],
                                                           'paired_first_trials':sensitivity['paired_first_trials'],'paired_workflows':sensitivity['paired_workflows']}
    mix_section,mix_strata,mix_grid=mix_analysis(core_tasks,context_trials,tool_trials)
    counterfactual_mix,counterfactual_strata,counterfactual_grid=mix_analysis(core_tasks,context_trials,tool_trials,True)
    core_pairs,core_task_pairs=core_pair_tables(core_trials)
    low_pairs,low_task_pairs=core_pair_tables(low_trials)
    sections={'core':core_section,'low_core':low_section,'effort_comparison':effort_section,'baseline':baseline_section,'context':context_section,'tools':tools_section,'requests':request_section,'workload_mix':mix_section,
              'workload_mix_auto_strip_counterfactual':counterfactual_mix,'administrative_recovery':recovery_section}
    tables={'request_records':request_records,'request_counters':request_counters,'request_strata':request_strata,
            'administratively_invalidated_terminal_requests':[r for r in request_records if r['administratively_invalidated']],
            'administratively_resolved_missing_client_attempts':request_section['administratively_resolved_missing_client_attempts'],
            'administratively_excluded_code_attempts':unique_latest(excluded_grades,['attempt_id']),
            'observed_concurrency':concurrency_rows,
            'overlapping_failure_candidates':overlapping_failures(request_records),
            'core_trials':core_trials,'core_tasks':core_tasks,'core_pairs':core_pairs,'core_task_pairs':core_task_pairs,'core_failures':core_failures,'core_leave_one_task_out':ltoo,
            'low_core_trials':low_trials,'low_core_tasks':low_tasks,'low_core_pairs':low_pairs,'low_core_task_pairs':low_task_pairs,'low_core_failures':low_failures,'low_core_leave_one_task_out':low_ltoo,
            'code_configurations':configurations,'effort_task_comparisons':effort_task_rows,
            'baseline_trials':baseline_trials,'baseline_summaries':baseline_section['summary'],'baseline_pairs':baseline_pairs,'baseline_pair_summaries':baseline_pair_summaries(baseline_pairs),'baseline_batches':baseline_batches,
            'context_trials':context_trials,'context_fields':context_fields,'context_field_summaries':context_field_summaries,
            'context_summaries':context_section['summary'],'context_pairs':context_pairs,
            'tool_trials':tool_trials,'tool_summaries':tools_section['summary'],'mix_strata':mix_strata,'mix_grid':mix_grid,
            'mix_strata_auto_strip_counterfactual':counterfactual_strata,'mix_grid_auto_strip_counterfactual':counterfactual_grid,
            'aggregate_records':flat_aggregates(sections)}
    selected_ids={r.get('attempt_id') for r in embedded}
    tables['requests_without_terminal_workflow']=[r for r in request_records if r['attempt_id'] not in selected_ids]
    request_section['terminal_requests_without_terminal_workflow_n']=len(tables['requests_without_terminal_workflow'])
    request_section['nonadministrative_terminal_requests_without_terminal_workflow_n']=sum(not r['administratively_invalidated'] for r in tables['requests_without_terminal_workflow'])
    request_section['workflow_accounting_note']='Workflow throughput uses runner-recorded chosen first/repair or episode responses. Every terminal attempt remains in request totals. Requests not yet referenced by terminal workflows are separately listed; pending or abandoned state and any additional overhead require review, not automatic deletion.'
    tables['aggregate_records']=flat_aggregates(sections)
    tables['core_extraction_diagnostics']=[{k:v for k,v in r.items() if 'extraction' in k or k in ('provider','trial_id','task_id','repetition','first_pass','repair_pass','solved','first_extracted_pass','repair_extracted_pass')} for r in core_trials]
    tables['low_core_extraction_diagnostics']=[{k:v for k,v in r.items() if 'extraction' in k or k in ('provider','trial_id','task_id','repetition','first_pass','repair_pass','solved','first_extracted_pass','repair_extracted_pass')} for r in low_trials]
    source_counts={name:len(rows) for name,rows in loaded.items()}
    pending_extraction=sum(r[stage+'_extraction_detected'] and r[stage+'_extracted_pass'] is None for r in core_trials+low_trials for stage in ('first','repair'))
    complete=all(r['first_graded_trials']==36 and r['workflow_terminal_trials']==36 and r['observed_tasks']==12 for r in core_section['summary']) and all(r['first_graded_trials']==24 and r['workflow_terminal_trials']==24 and r['observed_tasks']==12 for r in low_section['summary']) and len(baseline)==52 and len(context)==24 and len(tools)==12 and not request_section['unreturned_attempts'] and pending_extraction==0
    return {'schema_version':'magpie-analysis-v2.1','generated_at':datetime.now(LOCAL_TZ).isoformat(),'partial_data':not complete,
            'bootstrap_draws':draws,'bootstrap_seed':SEED,'source_row_counts':source_counts,'warnings':warnings,
            'pending_extraction_diagnostics_n':pending_extraction,
            'interpretation':['Only this v2 run is included; prior v1 calls are never pooled.','Task count and trial count are separately reported; 589 contract checks are not independent samples.','Paired bootstrap CIs condition on observed matched clusters and are exploratory; no difference does not establish equivalence.','Core, baseline, context size, tool episodes, effort, concurrency and peak/off-peak strata are separately available.','Correct-completion latency ratios condition on both providers succeeding and must be read beside quality/failures; useful throughput includes failures.','Restriction/resource/format rejections are benchmark nonpasses, not demonstrated algorithm errors. Import/IO/resource rules were disclosed, but the full AST gate (including dunder attribute access restrictions) was not fully spelled out in the model prompt; interpret normalized restriction counts separately.'],
            **sections,'tables':tables}


def fmt(value,digits=3):
    return 'NA' if value is None else f'{value:.{digits}f}'


def compact_summary(analysis):
    status='PARTIAL / RUNNING' if analysis['partial_data'] else 'planned evaluable strata terminal; administrative replacements retained' if analysis['administrative_recovery']['excluded_attempt_ids'] else 'planned strata terminal'
    lines=[f"Magpie v2 analysis: {status}; generated {analysis['generated_at']}",
           'Only v2. Core sampling unit=task cluster, not hidden assertions. CI=paired cluster bootstrap.']
    for row in analysis['core']['summary']:
        lines.append(f"CORE {row['provider']}: tasks {row['observed_tasks']}/12, first graded {row['first_graded_trials']}/36, workflow terminal {row['workflow_terminal_trials']}/36, pass@1 macro {fmt(row['first_pass_macro'])}, solved macro {fmt(row['solved_macro'])}, useful/min {fmt(row['workflow_correct_per_minute'])}.")
        lines.append(f"SECONDARY {row['provider']}: first source pass after conservative strip={fmt(row['first_after_extraction_macro'])}, known {row['first_after_extraction_known_trials']}/{row['first_graded_trials']}; fenced diagnostics {row['first_fenced_diagnostics_available']}/{row['first_fenced_trials']}. Primary repair/wait unchanged.")
    for key,result in analysis['core']['metrics'].items():
        interval=f"95% CI [{fmt(result['ci_low'])}, {fmt(result['ci_high'])}]" if result['ci_low'] is not None and result['ci_high'] is not None else 'CI unavailable'
        lines.append(f"CORE {key}: {fmt(result['estimate'])}, {interval}, tasks={result['n_clusters']}, pairs={result['n_pairs']}, valid draws={result['draws_valid']}/{result['draws_requested']}; {result['direction']}; state={result.get('estimate_state','finite_or_no_data')}.")
    for key,result in analysis['core']['secondary_metrics'].items():
        interval=f"95% CI [{fmt(result['ci_low'])}, {fmt(result['ci_high'])}]" if result['ci_low'] is not None and result['ci_high'] is not None else 'CI unavailable'
        lines.append(f"POSTHOC {key}: {fmt(result['estimate'])}, {interval}, tasks={result['n_clusters']}, pairs={result['n_pairs']}; {result['direction']}. Auto-strip times are counterfactual, not newly measured.")
    for row in analysis['low_core']['summary']:
        lines.append(f"LOW SUPPLEMENT {row['provider']}: tasks {row['observed_tasks']}/12, first graded {row['first_graded_trials']}/24, workflow terminal {row['workflow_terminal_trials']}/24, strict first={fmt(row['first_pass_macro'])}, strict solved={fmt(row['solved_macro'])}, extracted first={fmt(row['first_after_extraction_macro'])}. Separate posthoc stratum.")
    for row in analysis['baseline']['summary']:
        lines.append(f"BASELINE {row['phase']} c={row['concurrency_per_provider']} {row['provider']}: n={row['n_requests']} exact={row['fixture_passed']}, visible p50/p90/p95={fmt(row['first_visible_seconds_p50'])}/{fmt(row['first_visible_seconds_p90'])}/{fmt(row['first_visible_seconds_p95'])}s; total={fmt(row['total_seconds_p50'])}/{fmt(row['total_seconds_p90'])}/{fmt(row['total_seconds_p95'])}s.")
    for row in analysis['context']['summary']:
        lines.append(f"CONTEXT {row['size_label']} {row['provider']}: n={row['n_datasets']}, full={row['full_json_passed']}, fields={fmt(row['complete_field_pass_rate'])}, actual input mean={fmt(row['actual_input_tokens_mean'],0)}, total p50={fmt(row['total_seconds_p50'])}s.")
    for row in analysis['tools']['summary']:
        lines.append(f"TOOLS {row['repository_id']} {row['provider']}: n={row['n_episodes']}, source={row['source_passed']}, episode={row['episode_succeeded']}, censored={row['censored_n']}, turn mean={fmt(row['turns_mean'])}, tool errors={row['tool_errors_sum']}.")
    for row in analysis['requests']['provider_totals']:
        lines.append(f"REQUESTS {row['provider']}: terminal={row['n_terminal_requests']} complete={row['complete_n']} unknown terminal usage={row['unknown_usage_n']} missing client finals admin-resolved={row['administratively_resolved_missing_client_terminal_n']} unresolved={row['unreturned_journal_attempts_n']}; known-usage list-equivalent subtotal=${fmt(row['estimated_list_equivalent_usd_known_sum'],6)} (not billing; unknown charges excluded).")
    if analysis['administrative_recovery']['excluded_attempt_ids']:
        lines.append(f"ADMINISTRATIVE RECOVERY: {len(analysis['administrative_recovery']['excluded_attempt_ids'])} excluded attempts retained; {analysis['requests']['administrative_missing_client_finals_n']} missing client finals administratively resolved, usage/time unknown. Original completed grades and drop-recovered-pair sensitivity are separate; no provider failure inferred from collector SIGTERM.")
    ltoo=analysis['core']['metrics']['useful_throughput_ratio_goat_over_go']
    lines.append(f"Convenience throughput ratio GOAT/Go leave-one-task-out range: {fmt(ltoo['leave_one_task_out_min'])}–{fmt(ltoo['leave_one_task_out_max'])}. See mix_grid for 15 task-count mixtures; no arbitrary weighted winner.")
    lines += ['Unknown/pending observations are explicit. See analysis.json tables for raw inputs, pair wins, token/cache/reasoning counts, normalized failure labels and cost uncertainty.']
    if analysis['warnings']:lines.append('Warnings: '+' | '.join(analysis['warnings']))
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--draws',type=int,default=DEFAULT_DRAWS)
    options=parser.parse_args()
    if options.draws<1:parser.error('--draws must be positive')
    result=build(options.root.resolve(),options.draws)
    (options.root/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    summary=compact_summary(result)
    (options.root/'analysis-summary.txt').write_text(summary,encoding='utf-8')
    print(summary,end='')

if __name__=='__main__':main()
