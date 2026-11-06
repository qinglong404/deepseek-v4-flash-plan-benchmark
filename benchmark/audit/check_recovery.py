"""Synthetic full-cohort administrative accounting check; no model execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('recovery_stats_for_audit',ROOT/'analysis.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
FOLDER=HERE/'synthetic-recovery-cohort';FOLDER.mkdir(exist_ok=True)
logs={n:[] for n in ['requests.jsonl','attempt-journal.jsonl','core-results.jsonl','core-first-grades.jsonl','low-core-results.jsonl','low-core-first-grades.jsonl','core-extracted-grades.jsonl','baseline-results.jsonl','batch-times.jsonl','context-results.jsonl','tool-results.jsonl']}

def response(p,trial,phase,task=None,rep=0,aid=None,seconds=1):
    return {'attempt_id':aid or f'{p}-{phase}-{trial}','provider':p,'trial_id':trial,'phase':phase,'content':'def f(): pass\n','complete':True,'total_ms':seconds*1000,'first_visible_ms':100,'first_event_ms':50,'started':'2026-11-05T09:00:00+08:00','ended':f'2026-11-05T09:00:{seconds:02d}+08:00','usage':{'prompt_tokens':1000,'completion_tokens':200,'prompt_tokens_details':{'cached_tokens':400}},'metadata':{'task_id':task,'repetition':rep,'concurrency_per_provider':2},'route_verified':True,'status':200,'done':True,'finish_reason':'stop','effort_requested':'low' if phase.startswith('low_') else 'high','response_headers':{'x-magpie-provider':'opencode-go' if p=='go' else 'commandcode-plan'}}
def grade(passed=True,error=None):return {'passed':passed,'passed_checks':1 if passed else 0,'total':1,'checks':[{'name':'synthetic','ok':passed,'error':error}],'error':error,'failure_class':None if passed else 'semantic'}
def retain(row):
    logs['requests.jsonl'].append(row)
    start={k:row[k] for k in ['attempt_id','provider','phase','trial_id','started']}
    logs['attempt-journal.jsonl'] += [dict(event='started',**start),{'event':'terminal','attempt_id':row['attempt_id'],'provider':row['provider']}]
for effort,reps,prefix,fileprefix in [('high',3,'core','core'),('low',2,'low_core','low-core')]:
    for taskno in range(12):
        task=f'task{taskno:02d}'
        for rep in range(reps):
            trial=f'{task}-r{rep}' if effort=='high' else f'low-{task}-r{rep}'
            for p in ['go','goat']:
                row=response(p,trial,prefix+'_first',task,rep)
                retain(row)
                logs[fileprefix+'-first-grades.jsonl'].append({'provider':p,'task_id':task,'trial_id':trial,'attempt_id':row['attempt_id'],'grade':grade()})
                logs[fileprefix+'-results.jsonl'].append({'provider':p,'task_id':task,'trial_id':trial,'repetition':rep,'first':row,'first_grade':grade(),'repair':None,'repair_grade':None,'solved':True,'total_seconds':1})
for i in range(12):
    for p in ['go','goat']:
        row=response(p,f'serial-{i:02d}','serial')
        row['metadata'].update(concurrency_per_provider=1,fixture_index=i)
        row['grade']=grade();retain(row);logs['baseline-results.jsonl'].append(row)
for c in [1,2,4]:
    for rep in range(2):
        logs['batch-times.jsonl'].append({'batch':f'c{c}-r{rep}','wall_seconds':1,'new_requests':2*c})
        for slot in range(c):
            for p in ['go','goat']:
                row=response(p,f'c{c}-r{rep}-s{slot}','concurrency',rep=rep)
                row['metadata'].update(concurrency_per_provider=c,fixture_index=100+slot)
                row['grade']=grade();retain(row);logs['baseline-results.jsonl'].append(row)
for size in ['16K','64K','160K','320K']:
    for seed in range(3):
        for p in ['go','goat']:
            row=response(p,f'context-{size}-{seed}','context')
            row['metadata'].update(size_label=size,seed=seed,estimated_tokens=16000)
            row['grade']=grade();retain(row);logs['context-results.jsonl'].append(row)
for repo in ['repo0','repo1']:
    for rep in range(3):
        for p in ['go','goat']:
            trial=f'{repo}-r{rep}';row=response(p,trial+'-t00','tools');retain(row)
            logs['tool-results.jsonl'].append({'provider':p,'trial_id':trial,'repository_id':repo,'repetition':rep,'responses':[row],'trace':[],'grade':grade(),'source_pass':True,'episode_success':True,'termination':'final','censored':False,'seconds':1})

original=response('go','task00-r0','core_first','task00',aid='original-go-first',seconds=20)
retain(original)
bad=grade(False,'ValueError: dunder attribute access not permitted')
# Deliberately append excluded old grade/workflow AFTER the replacement: filtering
# must happen before latest-row selection or this would corrupt the primary.
logs['core-first-grades.jsonl'].append({'provider':'go','task_id':'task00','trial_id':'task00-r0','attempt_id':'original-go-first','grade':bad})
logs['core-results.jsonl'].append({'provider':'go','task_id':'task00','trial_id':'task00-r0','repetition':0,'first':original,'first_grade':bad,'repair':None,'repair_grade':None,'solved':False,'total_seconds':20})
events=[]
for aid,p,phase in [('interrupted-go-repair','go','core_repair'),('interrupted-goat-first','goat','core_first')]:
    event={'attempt_id':aid,'provider':p,'phase':phase,'trial_id':'task00-r0','started':'2026-11-05T09:00:00+08:00','collector_exit_code':143,'cause':'SIGTERM_source_unknown','administratively_invalidated':True,'gateway_evidence':{'status':499,'ms':1000,'in':0,'out':0,'cache_read':0}}
    events.append(event);logs['attempt-journal.jsonl'].append(dict(event='started',**event))
manifest={'events':events,'invalidated_trial':'task00-r0','excluded_attempt_ids':['original-go-first','interrupted-go-repair','interrupted-goat-first'],'recovery':'repeat whole pair'}
for name,rows in logs.items():(FOLDER/name).write_text(''.join(json.dumps(r)+'\n' for r in rows))
(FOLDER/'collector-interruptions.json').write_text(json.dumps(manifest))
out=a.build(FOLDER,100)
assert out['partial_data'] is False
assert out['requests']['raw_unreturned_attempts_n']==2
assert out['requests']['administrative_missing_client_finals_n']==2
assert out['requests']['unresolved_unreturned_attempts_n']==0
assert len(out['tables']['request_records'])==209
original_record=next(r for r in out['tables']['request_records'] if r['attempt_id']=='original-go-first')
assert original_record['input_tokens']==1000 and original_record['output_tokens']==200 and original_record['total_seconds']==20
assert original_record['administratively_invalidated']
primary=next(r for r in out['tables']['core_trials'] if r['provider']=='go' and r['trial_id']=='task00-r0')
assert primary['first_attempt_id']!='original-go-first' and primary['first_pass'] is True
excluded=out['tables']['administratively_excluded_code_attempts']
assert len(excluded)==1 and excluded[0]['normalized_failure_class']=='restriction' and excluded[0]['raw_passed'] is False
for row in out['tables']['administratively_resolved_missing_client_attempts']:
    assert all(row[k] is None for k in ['client_total_seconds','input_tokens','cached_tokens','output_tokens','reasoning_tokens','estimated_list_equivalent_usd'])
    assert row['gateway_status']==499 and row['gateway_elapsed_seconds']==1
assert out['administrative_recovery']['sensitivity_drop_recovered_pair']['paired_first_trials']==35
assert out['administrative_recovery']['sensitivity_drop_recovered_pair']['paired_workflows']==35
assert out['administrative_recovery']['sensitivity_drop_recovered_pair']['metrics']['first_pass_difference_goat_minus_go']['n_clusters']==12
summary=a.compact_summary(out)
assert 'administrative replacements retained' in summary and 'usage/time unknown' in summary
assert out['requests']['provider_totals'][0]['unknown_usage_including_missing_client_n']==1
assert out['requests']['provider_totals'][1]['unknown_usage_including_missing_client_n']==1

# An extra unexplained start must still block completion.
extra={'event':'started','attempt_id':'new-unexplained','provider':'go','phase':'core_first','trial_id':'unknown-r0','started':'2026-11-05T09:00:00+08:00'}
with (FOLDER/'attempt-journal.jsonl').open('a') as f:f.write(json.dumps(extra)+'\n')
pending=a.build(FOLDER,100)
assert pending['partial_data'] is True and pending['requests']['unresolved_unreturned_attempts_n']==1

result={'analysis_sha256':hashlib.sha256((ROOT/'analysis.py').read_bytes()).hexdigest(),'synthetic_returned_attempts_retained':209,'raw_missing_client_finals':2,'resolved_administrative':2,'unresolved':0,'cohort_complete_with_resolved_admin_records':not out['partial_data'],'extra_unresolved_start_blocks_completion':pending['partial_data'],'original_completed_restriction_failure_retained':True,'excluded_old_grade_after_new_does_not_override_primary':True,'gateway_zero_tokens_remain_unknown':True,'drop_recovered_pair_pairs':35,'drop_recovered_pair_task_clusters':12,'no_API_calls':True,'no_credentials_read':True}
(HERE/'administrative-recovery-results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
