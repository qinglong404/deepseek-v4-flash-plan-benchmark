"""Independent deterministic quantity arithmetic/coverage/provenance checks."""
import copy
import hashlib
import importlib.util
import io
import json
import math
from contextlib import redirect_stdout
from pathlib import Path
import sys
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('quantity_for_audit',ROOT/'quantity.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
checks=[]
def close(actual,expected):assert actual is not None and math.isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-11),(actual,expected)
def okay(name,detail=None):checks.append({'id':name,'ok':True,'detail':detail})
def stage(cost):
    # Synthetic off-peak costs use only uncached input: $0.15 per million.
    return {'input_tokens':round(cost/.15*1_000_000),'cached_tokens':0,'output_tokens':0,'estimated_list_equivalent_usd':cost}
def row(p,task,rep,cost,strict,sem,norm_first,first_cost=None,repair=False):
    first_cost=cost if first_cost is None else first_cost
    first=stage(first_cost);second=stage(cost-first_cost) if repair else {}
    r={'provider':p,'task_id':task,'trial_id':f'{task}-r{rep}','repetition':rep,'workflow_terminal':True,'solved':strict,'workflow_after_conservative_extraction_solved':sem,'first_after_conservative_extraction_pass':norm_first,'repair_attempted':repair,'first_attempt_id':f'{p}-{task}-{rep}-first','repair_attempt_id':f'{p}-{task}-{rep}-repair' if repair else None,'first_seconds':3,'workflow_seconds':9 if repair else 3,'auto_strip_seconds':3 if norm_first is True else 9 if repair else 3,'workflow_estimated_list_equivalent_usd':cost}
    r.update({'first_'+k:v for k,v in first.items()});r.update({'repair_'+k:v for k,v in second.items()})
    return r
def get(summary,p='go',endpoint='actual_strict',pricing='observed_start_period',effort='high'):
    return next(r for r in summary['tables']['quantity_summaries'] if (r['provider'],r['endpoint'],r['pricing'],r['effort'])==(p,endpoint,pricing,effort))
analysis={'generated_at':'AUDIT-SNAPSHOT-A','partial_data':True,'tables':{'core_trials':[],'low_core_trials':[],'request_records':[]},'requests':{'raw_unreturned_attempts':[]}}
for p,mult in [('go',1),('goat',2)]:
    analysis['tables']['core_trials'] += [row(p,'A',0,.15*mult,True,True,True),row(p,'A',1,.30*mult,False,True,True,.15*mult,True),row(p,'A',2,.45*mult,True,True,True),row(p,'B',0,.60*mult,False,False,False)]
out=q.build(analysis,100,1000)
s=get(out);n=get(out,endpoint='actual_conservative_extracted');cf=get(out,endpoint='counterfactual_conservative')
close(s['task_macro_cost_per_workflow'],.45);close(s['task_macro_success_rate'],1/3);close(s['modeled_correct_workflows_per_allowance'],100*(1/3)/.45)
close(n['modeled_correct_workflows_per_allowance'],100*.5/.45)
close(cf['task_macro_cost_per_workflow'],.425);close(cf['modeled_correct_workflows_per_allowance'],100*.5/.425)
assert s['eligible_workflows']==4 and s['eligible_tasks']==2
record=next(r for r in out['tables']['workflow_cost_records'] if r['provider']=='go' and r['trial_id']=='A-r1')
close(record['actual_workflow_observed_cost'],.30);close(record['actual_workflow_seconds'],9)
close(record['observed_start_period_counterfactual_cost'],.15);close(record['counterfactual_auto_strip_seconds'],3)
okay('README_handcase_ratio_of_task_macro_means_includes_failed_costs',{'strict':s['modeled_correct_workflows_per_allowance'],'conservative':n['modeled_correct_workflows_per_allowance'],'counterfactual':cf['modeled_correct_workflows_per_allowance'],'macro_actual_cost':.45,'macro_counterfactual_cost':.425})

for p in ['go','goat']:
    for endpoint in ['actual_strict','actual_conservative_extracted','counterfactual_conservative']:
        off=get(out,p,endpoint,'uniform_off_peak');peak=get(out,p,endpoint,'uniform_peak')
        close(peak['task_macro_cost_per_workflow'],off['task_macro_cost_per_workflow']*2)
        close(peak['modeled_correct_workflows_per_allowance'],off['modeled_correct_workflows_per_allowance']/2)
        for field in ['ci_low','ci_high']:
            if off[field] is not None:close(peak[field],off[field]/2)
for ratio in out['tables']['paired_quantity_ratios']:
    if ratio['effort']=='high':close(ratio['ratio_goat_over_go'],.5)
okay('uniform_peak_halves_quantity_and_CI_same_bootstrap_draws_matched_provider_double_cost_ratio_half')

# Unknown first usage cannot be priced as a known repair-only workflow.
extended=copy.deepcopy(analysis)
unknown=row('go','C',0,.30,False,False,False,.15,True)
unknown['first_input_tokens']=None;unknown['first_estimated_list_equivalent_usd']=None;unknown['workflow_estimated_list_equivalent_usd']=None
extended['tables']['core_trials'].append(unknown)
# Known cost but pending conservative grade excludes both actual endpoints.
semantic_pending=row('go','D',0,.90,True,None,None)
extended['tables']['core_trials'].append(semantic_pending)
# Unknown actual repair cost, but valid normalized first source: CF may use first.
cf_only=row('go','E',0,.30,False,True,True,.15,True)
cf_only['repair_input_tokens']=None;cf_only['repair_estimated_list_equivalent_usd']=None;cf_only['workflow_estimated_list_equivalent_usd']=None
extended['tables']['core_trials'].append(cf_only)
ext=q.build(extended,100,500)
strict=get(ext);semantic=get(ext,endpoint='actual_conservative_extracted');counter=get(ext,endpoint='counterfactual_conservative')
assert strict['eligible_workflows']==semantic['eligible_workflows']==4
assert strict['eligible_tasks']==semantic['eligible_tasks']==2
close(strict['task_macro_cost_per_workflow'],.45)
assert counter['eligible_workflows']==5 and counter['eligible_tasks']==3
u=next(r for r in ext['tables']['workflow_cost_records'] if r['task_id']=='C')
assert not u['whole_usage_known'] and u['actual_workflow_observed_cost'] is None
assert not any(u[p+'_actual_common_eligible'] for p in q.PRICING)
e=next(r for r in ext['tables']['workflow_cost_records'] if r['task_id']=='E')
assert not e['observed_start_period_actual_common_eligible'] and e['observed_start_period_counterfactual_eligible']
assert e['actual_workflow_observed_cost'] is None;close(e['observed_start_period_counterfactual_cost'],.15)
okay('whole_unknown_stage_exclusion_common_actual_population_and_separate_CF_eligibility')

# Provider summaries can differ, but direct ratios must use identical trial IDs.
provider_only=row('go','ONLY_GO',0,.001,True,True,True)
extended['tables']['core_trials'].append(provider_only)
matched=q.build(extended,100,500)
for ratio in matched['tables']['paired_quantity_ratios']:
    if ratio['effort']=='high':
        assert ratio['n_paired_tasks']==2 and ratio['n_paired_workflows']==4
        close(ratio['ratio_goat_over_go'],.5)
okay('matched_known_provider_trial_cohorts_ignore_unpaired_cheap_success')

# Repricing known usage with unknown timestamp is possible, observed cost is not.
missing_time=row('go','TIME',0,.15,True,True,True)
missing_time['first_estimated_list_equivalent_usd']=None;missing_time['workflow_estimated_list_equivalent_usd']=None
t=q.workflow_rows({'tables':{'core_trials':[missing_time]}})[0]
assert not t['observed_start_period_actual_common_eligible'] and t['uniform_off_peak_actual_common_eligible']
close(t['uniform_off_peak_actual_cost'],.15)
cache_case={'usage_known':True,'observed_cost':None,'input_tokens':1000,'cached_tokens':400,'output_tokens':200}
close(q.derived_cost(cache_case,'uniform_off_peak'),.0002112)
okay('unknown_original_time_can_be_uniformly_repriced_cache_subtracted_output_charged_once')

# Missing raw/admin usage is never treated as free. Raw cost outside chosen
# terminal workflows is retained in separate accounting rather than model cost.
acct=copy.deepcopy(analysis)
acct['tables']['request_records']=[{'provider':'go','phase':'core_first','attempt_id':'admin-old','estimated_list_equivalent_usd':.20,'administratively_invalidated':True}]
acct['requests']['raw_unreturned_attempts']=[{'provider':'go','phase':'core_repair','state':'administratively_resolved_collector_interruption'},{'provider':'goat','phase':'core_first','state':'in_flight_or_interrupted_unknown'}]
account=q.request_accounting(acct,q.workflow_rows(acct))
go=next(r for r in account if r['provider']=='go' and r['effort']=='high')
close(go['whole_observed_cost_known_subtotal'],1.5);close(go['raw_known_estimated_cost_subtotal'],.20)
assert go['administratively_invalidated_terminal_requests']==1 and go['administratively_resolved_missing_client_finals']==1 and go['missing_client_finals']==1
okay('actual_selected_cost_vs_all_raw_admin_request_subtotals_and_unknown_counts')

def edge_analysis(go_success,goat_success,go_cost=.15,goat_cost=.15):
    return {'tables':{'core_trials':[row(p,task,0,cost,success,success,success) for task in ['X','Y'] for p,success,cost in [('go',go_success,go_cost),('goat',goat_success,goat_cost)]]}}
zero=q.build(edge_analysis(False,False),100,100)
z=get(zero);close(z['modeled_correct_workflows_per_allowance'],0)
zp=next(r for r in zero['tables']['paired_quantity_ratios'] if r['effort']=='high' and r['pricing']=='observed_start_period' and r['endpoint']=='actual_strict')
assert zp['ratio_goat_over_go'] is None and 'zero' in zp['estimate_state']
inf=q.build(edge_analysis(False,True),100,100)
ip=next(r for r in inf['tables']['paired_quantity_ratios'] if r['effort']=='high' and r['pricing']=='observed_start_period' and r['endpoint']=='actual_strict')
assert ip['ratio_goat_over_go'] is None and ip['estimate_state']=='positive_infinity'
mixed=edge_analysis(True,True)
mixed['tables']['core_trials'][2]['solved']=False;mixed['tables']['core_trials'][2]['workflow_after_conservative_extraction_solved']=False
mb=q.build(mixed,100,1000)
bp=next(r for r in mb['tables']['paired_quantity_ratios'] if r['effort']=='high' and r['pricing']=='observed_start_period' and r['endpoint']=='actual_strict')
close(bp['ratio_goat_over_go'],2)
assert 0<bp['bootstrap_draws_valid']<1000 and bp['ci_low'] is None and bp['ci_high'] is None
okay('zero_success_infinity_and_mixed_undefined_ratio_bootstrap_suppresses_nominal_CI',{'undefined_draws':bp['bootstrap_draws_undefined'],'finite_draws':bp['bootstrap_draws_valid']})

free=q.build(edge_analysis(True,True,go_cost=0,goat_cost=.15),100,100)
fp=next(r for r in free['tables']['paired_quantity_ratios'] if r['effort']=='high' and r['pricing']=='observed_start_period' and r['endpoint']=='actual_strict')
free_ok=fp['ratio_goat_over_go']==0 and fp['estimate_state']=='finite'
checks.append({'id':'known_zero_cost_positive_success_provider_has_ratio_zero_not_no_data','ok':free_ok,'detail':fp})
assert free_ok,fp

# CLI provenance race: alter source file after it was consumed but before main()
# hashes it. The stored source hash must still identify the modeled bytes A.
race=HERE/'quantity-provenance-race';race.mkdir(exist_ok=True)
sourceA=json.dumps(analysis).encode();sourceB=json.dumps(dict(analysis,generated_at='AUDIT-SNAPSHOT-B')).encode()
(race/'analysis.json').write_bytes(sourceA)
original_build=q.build
def racing_build(parsed,*args,**kwargs):
    assert parsed['generated_at']=='AUDIT-SNAPSHOT-A'
    (race/'analysis.json').write_bytes(sourceB)
    return original_build(parsed,*args,**kwargs)
with patch.object(q,'build',side_effect=racing_build),patch.object(sys,'argv',['quantity.py','--root',str(race),'--draws','50']),redirect_stdout(io.StringIO()):q.main()
raceout=json.loads((race/'quantity.json').read_text())
assert raceout['source_analysis_sha256']==hashlib.sha256(sourceA).hexdigest()
assert raceout['source_analysis_sha256']!=hashlib.sha256((race/'analysis.json').read_bytes()).hexdigest()
assert raceout['source_analysis_generated_at']=='AUDIT-SNAPSHOT-A'
okay('source_analysis_hash_uses_exact_consumed_buffer_under_mocked_live_regeneration')

# Execute CLI on an immutable copy of the live partial analysis; writes audit only.
live=HERE/'quantity-live-snapshot';live.mkdir(exist_ok=True)
livebytes=(ROOT/'analysis.json').read_bytes();(live/'analysis.json').write_bytes(livebytes)
with patch.object(sys,'argv',['quantity.py','--root',str(live),'--draws','500']),redirect_stdout(io.StringIO()):q.main()
liveq=json.loads((live/'quantity.json').read_text())
assert liveq['source_analysis_sha256']==hashlib.sha256(livebytes).hexdigest()
assert liveq['source_analysis_partial_data']==json.loads(livebytes)['partial_data']
okay('live_model_cli_retains_source_label_and_hash',{'workflow_rows':len(liveq['tables']['workflow_cost_records']),'source_sha256':liveq['source_analysis_sha256'],'partial':liveq['source_analysis_partial_data']})
result={'quantity_py_sha256':hashlib.sha256((ROOT/'quantity.py').read_bytes()).hexdigest(),'no_API_calls':True,'no_credential_reads':True,'checks':checks}
(HERE/'quantity-acceptance-results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps(result,indent=2,allow_nan=False))
