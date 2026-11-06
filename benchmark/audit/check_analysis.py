"""Non-author calculation checks; synthetic data and an immutable partial-log copy."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('stats_for_audit',ROOT/'analysis.py')
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
findings=[]
def okay(name,detail=None):findings.append({'id':name,'ok':True,'detail':detail})
def close(actual,expected):assert actual is not None and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12),(actual,expected)

def response(p,trial,phase='core_first',seconds=1,complete=True,content='def f(): pass\n',task='task',rep=0,attempt=None):
    return {'attempt_id':attempt or f'{p}-{trial}-{phase}','provider':p,'trial_id':trial,'phase':phase,'content':content,'complete':complete,'total_ms':seconds*1000,'first_visible_ms':seconds*100,'first_event_ms':seconds*50,'started':'2026-11-05T09:00:00+08:00','ended':'2026-11-05T09:00:01+08:00','usage':{'prompt_tokens':1000,'completion_tokens':200,'prompt_tokens_details':{'cached_tokens':400},'completion_tokens_details':{'reasoning_tokens':50}},'metadata':{'task_id':task,'repetition':rep,'concurrency_per_provider':2},'route_verified':True,'status':200,'done':True,'finish_reason':'stop','response_headers':{'x-magpie-provider':'opencode-go' if p=='go' else 'commandcode-plan'}}
def grade(passed):return {'passed':passed,'passed_checks':589 if passed else 0,'total':589,'checks':[],'failure_class':None if passed else 'semantic'}
def workflow(p,task,rep,first_pass,secs=1,repair_pass=None,fenced=False):
    trial=f'{task}-r{rep}'
    first=response(p,trial,seconds=secs,content='```python\ndef f(): pass\n```\n' if fenced else 'def f(): pass\n',task=task,rep=rep)
    repair=response(p,trial,'core_repair',seconds=2*secs,task=task,rep=rep) if repair_pass is not None else None
    return {'provider':p,'task_id':task,'trial_id':trial,'repetition':rep,'first':first,'first_grade':grade(first_pass),'repair':repair,'repair_grade':grade(repair_pass) if repair is not None else None,'solved':first_pass or repair_pass is True,'total_seconds':secs+(2*secs if repair is not None else 0)}

# Three repetitions of one task must not outweigh one repetition of another.
rows=[]
for rep in range(3):
    rows.extend([workflow('go','A',rep,False),workflow('goat','A',rep,True)])
rows.extend([workflow('go','B',0,True),workflow('goat','B',0,False)])
section,trials,tasks,_,_=a.summarize_core(rows,[],[],500)
close(section['metrics']['first_pass_difference_goat_minus_go']['estimate'],0)
assert section['metrics']['first_pass_difference_goat_minus_go']['n_clusters']==2
assert section['metrics']['first_pass_difference_goat_minus_go']['n_pairs']==4
assert section['summary'][0]['first_graded_trials']==4
okay('task_macro_quality_with_unequal_repetitions',{'expected_difference':0,'clusters':2,'pairs':4,'assertions_not_sampling_units':True})
clusters={'A':[{'go':{'t':1},'goat':{'t':4}} for _ in range(3)],'B':[{'go':{'t':4},'goat':{'t':1}}]}
close(a.bootstrap(clusters,lambda d:a.geometric_latency_ratio(d,'t'),'unequal',500)['estimate'],1)
okay('latency_log_ratio_equal_task_weight',{'expected_ratio':1})

# Positive numerator with zero baseline, both zero, and partly undefined draws.
pair=lambda go,goat:{'go':{'solved':go,'workflow_seconds':1},'goat':{'solved':goat,'workflow_seconds':1}}
assert a.throughput_ratio([[pair(False,True)]]) is None
assert a.throughput_state([[pair(False,True)]])=='positive_infinity_GOAT_positive_Go_zero'
assert a.throughput_state([[pair(False,False)]])=='undefined_both_zero_correct'
mixed={'A':[pair(True,True)],'B':[pair(False,True)]}
b=a.bootstrap(mixed,a.throughput_ratio,'zero-denominator-audit',1000)
close(b['estimate'],2)
assert 0<b['draws_valid']<1000
assert b['ci_low'] is None and b['ci_high'] is None
assert b['conditional_finite_ci_low'] is not None and b['undefined_draws_n']==1000-b['draws_valid']
okay('zero_success_and_undefined_bootstrap_draws',b)

# A failed first grade with repair pending is not an eventual failure or success.
first=response('go','pending-r0',task='pending')
pending=[{'provider':'go','task_id':'pending','trial_id':'pending-r0','attempt_id':first['attempt_id'],'grade':grade(False)}]
section,trials,_,_,_=a.summarize_core([],pending,[first],100)
assert trials[0]['first_pass'] is False and trials[0]['workflow_terminal'] is False and trials[0]['solved'] is None
assert section['summary'][0]['workflow_terminal_trials']==0 and section['summary'][0]['workflow_pending_trials']==1
assert section['summary'][0]['solved_macro'] is None
okay('pending_repair_not_imputed_as_terminal_result')
section,trials,_,_,_=a.summarize_core([],[],[first],100)
assert len(trials)==1 and trials[0]['first_pass'] is None and not trials[0]['workflow_terminal']
assert section['summary'][0]['first_graded_trials']==0 and section['summary'][0]['workflow_pending_trials']==1
okay('terminal_first_response_awaiting_grade_is_observed_pending')

# Wrapper normalization is diagnostic, post hoc, exact and keyed by attempt ID.
rows=[workflow(p,'fence',0,p=='go',secs=1 if p=='go' else 3,repair_pass=None if p=='go' else False,fenced=p=='goat') for p in ['go','goat']]
wrapped=rows[1]['first']
sidecar=[{'attempt_id':wrapped['attempt_id'],'extraction_rule':'single_whole_fenced_block_v1','extracted_code_grade':grade(True)}]
section,trials,_,_,_=a.summarize_core(rows,[],[],100,sidecar)
goat=[t for t in trials if t['provider']=='goat'][0]
assert goat['first_pass'] is False and goat['solved'] is False
assert goat['first_after_conservative_extraction_pass'] is True and goat['workflow_after_conservative_extraction_solved'] is True
close(goat['workflow_seconds'],9)
close(goat['auto_strip_seconds'],3)
assert 'posthoc' in section['secondary_metrics']['first_after_extraction_difference_goat_minus_go']['analysis_status']
assert a.whole_fenced_source('```python\nx=1\n```')=='x=1'
for text in ['before\n```python\nx=1\n```','```python\nx=1\n```\n```python\ny=2\n```','```javascript\nx=1\n```']:
    assert a.whole_fenced_source(text) is None
_,unknown,_,_,_=a.summarize_core(rows,[],[],100,[])
assert [t for t in unknown if t['provider']=='goat'][0]['first_after_conservative_extraction_pass'] is None
okay('posthoc_fence_sidecar_keeps_primary_actual_wait_and_unknown_diagnostics_separate')

# Calendar conversion, cached-input subtraction, and no reasoning double charge.
r=response('go','cost')
close(a.request_record(r)['estimated_list_equivalent_usd'],.0004224)
for stamp,expected in [('2026-11-05T01:00:00Z','peak'),('2026-11-04T17:00:00-08:00','peak'),('2026-11-05T12:00:00+08:00','off_peak'),('2026-11-05T14:00:00+08:00','peak'),('2026-11-05T18:00:00+08:00','off_peak'),('2026-11-07T09:00:00+08:00','off_peak')]:
    row=a.request_record(dict(r,started=stamp));assert row['pricing_period']==expected,(stamp,row)
    close(row['estimated_list_equivalent_usd'],.0004224 if expected=='peak' else .0002112)
unknown=copy.deepcopy(r);del unknown['usage']['prompt_tokens_details']
assert a.request_record(unknown)['estimated_list_equivalent_usd'] is None
assert a.request_record(dict(r,started=None))['estimated_list_equivalent_usd'] is None
okay('cost_calendar_cache_subtraction_reasoning_not_double_counted_unknowns_preserved')

# Baseline denominator is 12 serial pairs; concurrency workloads have six batches
# and 14 requests/provider, not 12 independent observations per concurrency level.
baseline=[];batches=[]
for i in range(12):
    for p in ['go','goat']:
        q=response(p,f'serial-{i}',phase='serial',seconds=1 if p=='go' else 2)
        q['metadata'].update(concurrency_per_provider=1,repetition=i,fixture_index=i)
        q['grade']={'passed':True};baseline.append(q)
for c in [1,2,4]:
    for rep in [0,1]:
        batches.append({'batch':f'c{c}-r{rep}','wall_seconds':2,'new_requests':2*c})
        for stream in range(c):
            for p in ['go','goat']:
                q=response(p,f'c{c}-r{rep}-s{stream}',phase='concurrency',seconds=1 if p=='go' else 2)
                q['metadata'].update(concurrency_per_provider=c,repetition=rep,fixture_index=100+stream)
                q['grade']={'passed':True};baseline.append(q)
base,_,_,batch_rows=a.summarize_baseline(baseline,batches,100)
assert base['serial_metrics']['total_seconds_ratio_all_terminal']['n_pairs']==12
close(base['serial_metrics']['total_seconds_ratio_all_terminal']['estimate'],2)
assert len(batch_rows)==12
assert sum(x['n_requests'] for x in batch_rows if x['provider']=='go')==14
assert {c:sum(x['concurrency_per_provider']==c and x['provider']=='go' for x in batch_rows) for c in [1,2,4]}=={1:2,2:2,4:2}
okay('baseline_12_serial_pairs_14_concurrent_requests_6_batches_per_provider')

# Source correctness cannot promote a capped or interrupted episode to success.
tools=[{'provider':'go','trial_id':'repo-r0','repository_id':'repo','source_pass':True,'episode_success':False,'termination':'turn_cap','censored':True,'seconds':10,'responses':[response('go','tool-turn',phase='tools')],'grade':grade(True),'trace':[]}]
ts,tr=a.summarize_tools(tools)
assert ts['summary'][0]['source_passed']==1 and ts['summary'][0]['episode_succeeded']==0 and ts['summary'][0]['censored_n']==1
okay('tool_source_correct_vs_valid_final_episode_kept_separate')

# Retain superseded attempts and unreturned journal attempts separately.
journal=[{'event':'started','attempt_id':'orphan','provider':'go','phase':'core_first','trial_id':'orphan','started':'2026-11-05T09:00:00+08:00'},{'event':'started','attempt_id':'missing-result','provider':'goat'},{'event':'terminal','attempt_id':'missing-result','provider':'goat'}]
reqs=[response('go','same',attempt='old'),response('go','same',attempt='new')]
rs,rr,_,_=a.summarize_requests(reqs,journal,100)
assert len(rr)==2 and len(rs['unreturned_attempts'])==2
assert {x['state'] for x in rs['unreturned_attempts']}=={'in_flight_or_interrupted_unknown','terminal_result_missing'}
okay('superseded_raw_attempts_and_orphans_retained')

# Supplementary low effort must remain outside the frozen high-effort primary.
high_rows=[workflow('go',task,rep,True,secs=8 if task=='A' else 4) for task in ['A','B'] for rep in range(3)]
low_rows=[workflow('go',task,rep,task=='A',secs=2) for task in ['A','B'] for rep in range(2)]
for row in low_rows:
    row['first']['phase']='low_core_first'
    row['first']['effort_requested']='low'
high_sec,_,high_tasks,_,_=a.summarize_core(high_rows,[],[],100)
low_sec,_,low_tasks,_,_=a.summarize_core(low_rows,[],[],100,phase_prefix='low_core',planned_trials=24)
effort,configurations,task_comparisons=a.effort_comparison(high_tasks,low_tasks,500)
assert high_sec['summary'][0]['planned_trials']==36 and low_sec['summary'][0]['planned_trials']==24
assert next(r for r in configurations if r['provider']=='go' and r['effort']=='high')['n_first_trials']==6
assert next(r for r in configurations if r['provider']=='go' and r['effort']=='low')['n_first_trials']==4
close(effort['metrics_by_provider']['go']['first_pass_rate_low_minus_high']['estimate'],-.5)
close(effort['metrics_by_provider']['go']['first_seconds_mean_ratio_low_over_high']['estimate'],math.sqrt(.125))
assert 'confounded' in effort['metrics_by_provider']['go']['first_seconds_mean_ratio_low_over_high']['analysis_status']
high_only,high_trials,_,_,_=a.summarize_core([],[],[low_rows[0]['first']],100)
assert not high_trials
okay('supplementary_low_effort_separate_3_vs_2_rep_task_macro_with_calendar_caveat')

# Cross-phase load uses half-open timestamp intervals, not nominal metadata.
def interval(p,phase,start,end):
    return {'provider':p,'phase':phase,'started':f'2026-11-05T18:00:0{start}+08:00','ended':f'2026-11-05T18:00:0{end}+08:00'}
load=[interval('go','core_first',0,2),interval('goat','core_first',1,3),interval('go','context',2,4),interval('go','tools',2.5,4.5)]
a.observed_concurrency(load)
assert load[0]['observed_recorded_global_max_streams_during_request']==2
assert load[2]['observed_recorded_global_streams_at_start']==2
assert load[2]['observed_recorded_provider_streams_at_start']==1
assert load[2]['observed_recorded_global_max_streams_during_request']==3
assert load[2]['observed_recorded_provider_max_streams_during_request']==2
okay('observed_cross_phase_concurrency_and_half_open_boundaries')

# Analyze a frozen, read-only copy of the currently partial experiment.
snapshot=HERE/'partial-statistics-snapshot';snapshot.mkdir(exist_ok=True)
names=['requests.jsonl','attempt-journal.jsonl','core-results.jsonl','core-first-grades.jsonl','low-core-results.jsonl','low-core-first-grades.jsonl','core-extracted-grades.jsonl','baseline-results.jsonl','batch-times.jsonl','context-results.jsonl','tool-results.jsonl','collector-interruptions.json']
source_hashes={}
for name in names:
    path=ROOT/name
    if path.exists():
        data=path.read_bytes();(snapshot/name).write_bytes(data);source_hashes[name]=hashlib.sha256(data).hexdigest()
partial=a.build(snapshot,500)
assert partial['partial_data'] is False
raw=[json.loads(line) for line in (snapshot/'requests.jsonl').read_text().splitlines() if line]
expected_ids={r['attempt_id'] for r in raw}
assert expected_ids<={r['attempt_id'] for r in partial['tables']['request_records']}
core=partial['tables']['core_trials']
for p in ['go','goat']:
    bytask={}
    for row in core:
        if row['provider']==p and row['first_pass'] is not None:bytask.setdefault(row['task_id'],[]).append(row['first_pass'])
    expected=sum(sum(v)/len(v) for v in bytask.values())/len(bytask) if bytask else None
    actual=next(r for r in partial['core']['summary'] if r['provider']==p)['first_pass_macro']
    assert actual==expected,(p,actual,expected)
(HERE/'partial-statistics-analysis.json').write_text(json.dumps(partial,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
okay('current_final_run_raw_attempt_retention_and_manual_task_macro_reproduction',{'source_hashes':source_hashes,'request_attempts':len(raw),'core_trials_observed':len(core),'core_task_clusters_first':partial['core']['n_task_clusters_first'],'orphan_count':len(partial['requests']['unreturned_attempts']),'partial':False})

result={'analysis_sha256':hashlib.sha256((ROOT/'analysis.py').read_bytes()).hexdigest(),'captured_at':datetime.now(timezone.utc).isoformat(),'checks':findings,'no_API_calls':True,'no_credential_reads':True}
(HERE/'statistics-acceptance-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
