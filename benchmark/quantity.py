"""Model correct coding workflows per $100 of list-equivalent allowance.

Read analysis.json only; no API/client/config imports. Actual strict, actual
conservatively extracted, and deterministic auto-strip scenarios stay separate.
Run: python quantity.py [--root DIR] [--draws 10000] [--allowance 100]
"""
from __future__ import annotations
import argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

PROVIDERS=('go','goat')
PRICING=('observed_start_period','uniform_off_peak','uniform_peak')
RATES={'uniform_off_peak':(.15,.003,.60),'uniform_peak':(.30,.006,1.20)}
SEED=2026110523


def numeric(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) else None


def avg(values):
    values=[v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def percentile(values,p):
    values=sorted(values)
    if not values:return None
    index=(len(values)-1)*p;lo=math.floor(index);hi=math.ceil(index)
    return values[lo]+(values[hi]-values[lo])*(index-lo)


def divide(numerator,denominator):
    return numerator/denominator if numerator is not None and denominator is not None and denominator>0 else None


def rate_state(numerator,denominator):
    if numerator is None or denominator is None:return 'no_eligible_data'
    if denominator==0:return 'positive_infinity' if numerator>0 else 'undefined_zero_over_zero'
    if denominator<0:return 'invalid_negative_denominator'
    return 'finite'


def derived_cost(components,pricing):
    if not components['usage_known']:return None
    if pricing=='observed_start_period':return components['observed_cost']
    inp,cache,out=RATES[pricing]
    return ((components['input_tokens']-components['cached_tokens'])*inp+components['cached_tokens']*cache+components['output_tokens']*out)/1_000_000


def stage_components(row,stage):
    inp=numeric(row.get(stage+'_input_tokens'));cache=numeric(row.get(stage+'_cached_tokens'));out=numeric(row.get(stage+'_output_tokens'))
    known=all(v is not None and v>=0 for v in (inp,cache,out)) and cache<=inp
    cost=numeric(row.get(stage+'_estimated_list_equivalent_usd'))
    return {'usage_known':known,'input_tokens':inp,'cached_tokens':cache,'output_tokens':out,
            'observed_cost':cost if known and cost is not None and cost>=0 else None}


def combined_components(parts):
    known=bool(parts) and all(p['usage_known'] for p in parts)
    cost_known=known and all(p['observed_cost'] is not None for p in parts)
    return {'usage_known':known,
            'input_tokens':sum(p['input_tokens'] for p in parts) if known else None,
            'cached_tokens':sum(p['cached_tokens'] for p in parts) if known else None,
            'output_tokens':sum(p['output_tokens'] for p in parts) if known else None,
            'observed_cost':sum(p['observed_cost'] for p in parts) if cost_known else None}


def workflow_rows(analysis):
    records=[]
    for effort,key in [('high','core_trials'),('low','low_core_trials')]:
        for row in analysis.get('tables',{}).get(key,[]):
            first=stage_components(row,'first')
            parts=[first]
            if row.get('repair_attempted'):parts.append(stage_components(row,'repair'))
            whole=combined_components(parts)
            terminal=bool(row.get('workflow_terminal'))
            strict=row.get('solved') if type(row.get('solved')) is bool else None
            semantic=row.get('workflow_after_conservative_extraction_solved') if type(row.get('workflow_after_conservative_extraction_solved')) is bool else None
            norm_first=row.get('first_after_conservative_extraction_pass')
            if norm_first is True:
                counter=first;counter_solved=True;counter_basis='measured first attempt only; normalized first source passes'
            elif norm_first is False and terminal:
                counter=whole;counter_solved=semantic;counter_basis='recorded whole workflow; normalized first source fails'
            else:
                counter={'usage_known':False,'input_tokens':None,'cached_tokens':None,'output_tokens':None,'observed_cost':None}
                counter_solved=None;counter_basis='counterfactual policy unresolved'
            rec={'provider':row.get('provider'),'effort':effort,'task_id':row.get('task_id'),'trial_id':row.get('trial_id'),
                 'repetition':row.get('repetition'),'workflow_terminal':terminal,'repair_attempted':bool(row.get('repair_attempted')),
                 'first_attempt_id':row.get('first_attempt_id'),'repair_attempt_id':row.get('repair_attempt_id'),
                 'strict_solved':strict,'conservative_solved':semantic,'normalized_first_pass':norm_first,
                 'whole_usage_known':whole['usage_known'] if terminal else False,
                 'whole_observed_cost_known':bool(terminal and whole['observed_cost'] is not None),
                 'actual_first_seconds':numeric(row.get('first_seconds')),'actual_workflow_seconds':numeric(row.get('workflow_seconds')),
                 'actual_first_observed_cost':first['observed_cost'],'actual_workflow_observed_cost':whole['observed_cost'] if terminal else None,
                 'counterfactual_solved':counter_solved,'counterfactual_cost_basis':counter_basis,
                 'counterfactual_auto_strip_seconds':numeric(row.get('auto_strip_seconds')),
                 'whole_input_tokens':whole['input_tokens'] if terminal else None,
                 'whole_cached_tokens':whole['cached_tokens'] if terminal else None,
                 'whole_output_tokens':whole['output_tokens'] if terminal else None}
            reported=numeric(row.get('workflow_estimated_list_equivalent_usd'))
            rec['reported_workflow_cost_matches_stages']=(math.isclose(reported,whole['observed_cost'],rel_tol=1e-10,abs_tol=1e-12) if terminal and reported is not None and whole['observed_cost'] is not None else None)
            for pricing in PRICING:
                actual_cost=derived_cost(whole,pricing) if terminal else None
                cf_cost=derived_cost(counter,pricing)
                reasons=[]
                if not terminal:reasons.append('workflow_pending')
                if terminal and not whole['usage_known']:reasons.append('whole_workflow_usage_unknown')
                if terminal and whole['usage_known'] and actual_cost is None:reasons.append('whole_workflow_cost_unknown')
                if strict is None:reasons.append('strict_outcome_unknown')
                if semantic is None:reasons.append('conservative_outcome_unknown')
                common=terminal and actual_cost is not None and strict is not None and semantic is not None
                cf_reasons=[]
                if counter_solved is None:cf_reasons.append('counterfactual_outcome_unknown')
                if not counter['usage_known']:cf_reasons.append('selected_counterfactual_usage_unknown')
                elif cf_cost is None:cf_reasons.append('selected_counterfactual_cost_unknown')
                rec[pricing+'_actual_cost']=actual_cost
                rec[pricing+'_actual_common_eligible']=bool(common)
                rec[pricing+'_actual_exclusion']='; '.join(reasons) if not common else None
                rec[pricing+'_counterfactual_cost']=cf_cost
                rec[pricing+'_counterfactual_eligible']=bool(counter_solved is not None and cf_cost is not None)
                rec[pricing+'_counterfactual_exclusion']='; '.join(cf_reasons) if cf_reasons else None
            records.append(rec)
    return records


def sampling_interval(values,total_draws):
    finite=[v for v in values if v is not None and math.isfinite(v)]
    result={'ci_low':None,'ci_high':None,'bootstrap_draws_valid':len(finite),'bootstrap_draws_requested':total_draws,
            'bootstrap_draws_undefined':total_draws-len(finite)}
    if len(finite)==total_draws:
        result.update(ci_low=percentile(finite,.025),ci_high=percentile(finite,.975))
    else:
        result.update(conditional_finite_ci_low=percentile(finite,.025),conditional_finite_ci_high=percentile(finite,.975),
                      ci_note='Nominal CI suppressed because some draws are undefined. Conditional finite quantiles are diagnostics only.')
    return result


def bootstrap_provider(points,allowance,name,draws):
    """Points are complete task means; no resampling individual assertions/trials."""
    fields=('strict_success_rate','conservative_success_rate')
    mean_cost=avg([p['mean_cost'] for p in points])
    output={}
    for field in fields:
        success=avg([p[field] for p in points])
        output[field]={'mean_cost':mean_cost,'success_rate':success,
                       'correct_workflows_per_allowance':divide(None if success is None else allowance*success,mean_cost),
                       'estimate_state':rate_state(success,mean_cost),'ci_low':None,'ci_high':None,
                       'bootstrap_draws_valid':0,'bootstrap_draws_requested':draws,'bootstrap_draws_undefined':0}
    if len(points)<2:
        for result in output.values():result['ci_note']='At least two eligible task clusters required.'
        return output
    salt=int.from_bytes(hashlib.sha256(name.encode()).digest()[:8],'big')
    rng=random.Random(SEED+salt)
    samples={field:[] for field in fields}
    for _ in range(draws):
        sample=[points[rng.randrange(len(points))] for _ in points]
        cost=avg([p['mean_cost'] for p in sample])
        for field in fields:
            success=avg([p[field] for p in sample])
            samples[field].append(divide(allowance*success,cost))
    for field in fields:output[field].update(sampling_interval(samples[field],draws))
    return output


def provider_estimates(records,effort,provider,pricing,allowance,draws,counterfactual=False):
    population=[r for r in records if r['effort']==effort and r['provider']==provider]
    eligible=[r for r in population if r[pricing+('_counterfactual_eligible' if counterfactual else '_actual_common_eligible')]]
    groups=defaultdict(list)
    for row in eligible:groups[row['task_id']].append(row)
    task_rows=[]
    for task,rows in sorted(groups.items()):
        cost=avg([r[pricing+('_counterfactual_cost' if counterfactual else '_actual_cost')] for r in rows])
        strict=avg([r['counterfactual_solved'] if counterfactual else r['strict_solved'] for r in rows])
        sem=avg([r['counterfactual_solved'] if counterfactual else r['conservative_solved'] for r in rows])
        task_rows.append({'effort':effort,'provider':provider,'pricing':pricing,'scenario':'auto_strip_counterfactual' if counterfactual else 'actual_recorded_workflow',
                          'task_id':task,'n_eligible_workflows':len(rows),'mean_cost':cost,'strict_success_rate':strict,'conservative_success_rate':sem,
                          'strict_correct_workflows_observed':sum(r['counterfactual_solved'] if counterfactual else r['strict_solved'] for r in rows),
                          'conservative_correct_workflows_observed':sum(r['counterfactual_solved'] if counterfactual else r['conservative_solved'] for r in rows)})
    boot=bootstrap_provider(task_rows,allowance,effort+'-'+provider+('-counterfactual' if counterfactual else '-actual'),draws)
    observed_tasks={r['task_id'] for r in population};eligible_tasks=set(groups)
    common={'effort':effort,'provider':provider,'pricing':pricing,'allowance_usd':allowance,'planned_tasks':12,'planned_workflows':36 if effort=='high' else 24,
            'observed_workflows':len(population),'terminal_workflows':sum(r['workflow_terminal'] for r in population),
            'whole_usage_known_terminal_workflows':sum(r['workflow_terminal'] and r['whole_usage_known'] for r in population),
            'whole_observed_cost_known_terminal_workflows':sum(r['whole_observed_cost_known'] for r in population),
            'eligible_workflows':len(eligible),'excluded_workflows':len(population)-len(eligible),
            'eligible_tasks':len(eligible_tasks),'observed_tasks':len(observed_tasks),'missing_tasks_vs_planned':12-len(eligible_tasks),
            'excluded_observed_task_ids':' | '.join(sorted(observed_tasks-eligible_tasks)),
            'strict_conservative_share_population':not counterfactual,
            'population':'counterfactual selected-cost-known workflows' if counterfactual else 'terminal whole-cost-known workflows with both strict and conservative outcomes known',
            'cost_scope':'inferred policy cost, not actual spend' if counterfactual else 'all measured first and needed repair cost, including failures',
            'analysis_status':'posthoc deterministic counterfactual' if counterfactual else 'measured workflow list-equivalent model; extracted endpoint posthoc',
            'bootstrap_unit':'whole task cluster; equal task means; repetitions retained within task','bootstrap_seed':SEED}
    summaries=[]
    endpoints=[('counterfactual_conservative','conservative_success_rate')] if counterfactual else [('actual_strict','strict_success_rate'),('actual_conservative_extracted','conservative_success_rate')]
    for endpoint,field in endpoints:
        result=boot[field]
        summaries.append({**common,'endpoint':endpoint,
                          'task_macro_cost_per_workflow':result['mean_cost'],'task_macro_success_rate':result['success_rate'],
                          'modeled_correct_workflows_per_allowance':result['correct_workflows_per_allowance'],'estimate_state':result['estimate_state'],
                          'correct_workflows_observed':sum(r['counterfactual_solved'] if counterfactual else r['strict_solved'] if field=='strict_success_rate' else r['conservative_solved'] for r in eligible),
                          **{k:v for k,v in result.items() if k.startswith('ci_') or k.startswith('conditional_') or k.startswith('bootstrap_')}})
    exclusions=[]
    reasonkey=pricing+('_counterfactual_exclusion' if counterfactual else '_actual_exclusion')
    for reason,count in Counter(r[reasonkey] for r in population if r not in eligible).items():
        exclusions.append({'effort':effort,'provider':provider,'pricing':pricing,'scenario':'auto_strip_counterfactual' if counterfactual else 'actual_recorded_workflow','reason':reason,'n_workflows':count})
    if counterfactual:
        for row in task_rows:
            row['counterfactual_success_rate']=row['conservative_success_rate']
            row['counterfactual_correct_workflows_observed']=row['conservative_correct_workflows_observed']
            row['strict_success_rate']=None
            row['strict_correct_workflows_observed']=None
    return summaries,task_rows,exclusions


def paired_quantity_ratios(records,effort,pricing,allowance,draws,counterfactual=False):
    eligibility=pricing+('_counterfactual_eligible' if counterfactual else '_actual_common_eligible')
    cost_key=pricing+('_counterfactual_cost' if counterfactual else '_actual_cost')
    lookup=defaultdict(dict)
    for row in records:
        if row['effort']==effort and row[eligibility]:lookup[row['trial_id']][row['provider']]=row
    pairs=[p for _,p in sorted(lookup.items()) if all(provider in p for provider in PROVIDERS)]
    groups=defaultdict(list)
    for pair in pairs:groups[pair['go']['task_id']].append(pair)
    points=[]
    for task,rows in sorted(groups.items()):
        point={'task_id':task}
        for provider in PROVIDERS:
            point[provider+'_cost']=avg([r[provider][cost_key] for r in rows])
            point[provider+'_strict']=avg([r[provider]['counterfactual_solved'] if counterfactual else r[provider]['strict_solved'] for r in rows])
            point[provider+'_conservative']=avg([r[provider]['counterfactual_solved'] if counterfactual else r[provider]['conservative_solved'] for r in rows])
        points.append(point)
    def statistic(data,field):
        success={p:avg([r[p+'_'+field] for r in data]) for p in PROVIDERS}
        cost={p:avg([r[p+'_cost'] for r in data]) for p in PROVIDERS}
        if any(success[p] is None or cost[p] is None for p in PROVIDERS):
            return None,'no_eligible_data'
        if all(cost[p]>0 for p in PROVIDERS):
            # Preserve the ordinary positive-cost arithmetic exactly.
            quantities={p:divide(success[p],cost[p]) for p in PROVIDERS}
            return divide(quantities['goat'],quantities['go']),rate_state(quantities['goat'],quantities['go'])
        if any(cost[p]==0 and success[p]==0 for p in PROVIDERS):
            return None,'undefined_provider_efficiency_zero_over_zero'
        if all(cost[p]==0 for p in PROVIDERS):
            return None,'undefined_infinity_over_infinity'
        numerator=success['goat']*cost['go']
        denominator=success['go']*cost['goat']
        return divide(numerator,denominator),rate_state(numerator,denominator)
    fields=['conservative'] if counterfactual else ['strict','conservative']
    output=[]
    salt=int.from_bytes(hashlib.sha256((effort+('-paired-counterfactual' if counterfactual else '-paired-actual')).encode()).digest()[:8],'big')
    for field in fields:
        estimate,state=statistic(points,field)
        endpoint='counterfactual_conservative' if counterfactual else 'actual_strict' if field=='strict' else 'actual_conservative_extracted'
        record={'effort':effort,'pricing':pricing,'endpoint':endpoint,
                'ratio_goat_over_go':estimate,'estimate_state':state,'direction':'above one means more modeled correct workflows per equal allowance for GOAT',
                'n_paired_tasks':len(points),'n_paired_workflows':len(pairs),'allowance_usd_each':allowance,
                'ci_low':None,'ci_high':None,'bootstrap_draws_requested':draws,'bootstrap_draws_valid':0,'bootstrap_draws_undefined':0,
                'population':'same eligible trial identities in both providers; same pricing/scenario/outcome rule',
                'bootstrap_unit':'paired whole task cluster','analysis_status':'posthoc inferred counterfactual' if counterfactual else 'known-cost matched subset; no arbitrary overall winner'}
        if len(points)>=2:
            rng=random.Random(SEED+salt)
            samples=[statistic([points[rng.randrange(len(points))] for _ in points],field)[0] for _ in range(draws)]
            record.update(sampling_interval(samples,draws))
        else:record['ci_note']='At least two paired eligible task clusters required.'
        output.append(record)
    return output


def request_accounting(analysis,records):
    result=[]
    requests=analysis.get('tables',{}).get('request_records',[])
    missing=analysis.get('requests',{}).get('raw_unreturned_attempts',[])
    for effort in ('high','low'):
        phases=('core_first','core_repair') if effort=='high' else ('low_core_first','low_core_repair')
        for provider in PROVIDERS:
            workflows=[r for r in records if r['provider']==provider and r['effort']==effort]
            selected={r['first_attempt_id'] for r in workflows if r['workflow_terminal']}
            selected|={r['repair_attempt_id'] for r in workflows if r['workflow_terminal'] and r['repair_attempted']}
            selected.discard(None)
            raw=[r for r in requests if r.get('provider')==provider and r.get('phase') in phases]
            wholeknown=[r for r in workflows if r['whole_observed_cost_known']]
            missing_rows=[r for r in missing if r.get('provider')==provider and r.get('phase') in phases]
            costvalues=[numeric(r.get('estimated_list_equivalent_usd')) for r in raw]
            result.append({'effort':effort,'provider':provider,'terminal_workflows':sum(r['workflow_terminal'] for r in workflows),
                           'pending_workflows':sum(not r['workflow_terminal'] for r in workflows),
                           'whole_usage_known_workflows':sum(r['whole_usage_known'] for r in workflows),
                           'whole_observed_cost_known_workflows':len(wholeknown),
                           'unknown_whole_observed_cost_terminal_workflows':sum(r['workflow_terminal'] and not r['whole_observed_cost_known'] for r in workflows),
                           'whole_observed_cost_known_subtotal':sum(r['actual_workflow_observed_cost'] for r in wholeknown) if wholeknown else None,
                           'raw_terminal_requests':len(raw),'raw_known_cost_requests':sum(v is not None for v in costvalues),
                           'raw_unknown_cost_requests':sum(v is None for v in costvalues),
                           'raw_known_estimated_cost_subtotal':sum(v for v in costvalues if v is not None) if any(v is not None for v in costvalues) else None,
                           'raw_terminal_requests_outside_selected_terminal_workflows':sum(r.get('attempt_id') not in selected for r in raw),
                           'administratively_invalidated_terminal_requests':sum(bool(r.get('administratively_invalidated')) for r in raw),
                           'missing_client_finals':len(missing_rows),
                           'administratively_resolved_missing_client_finals':sum(r.get('state')=='administratively_resolved_collector_interruption' for r in missing_rows),
                           'cost_note':'Known list-equivalent subtotals only; omitted unknown usage may have incurred cost. Raw request subtotal may include pending/superseded/administrative attempts, unlike selected workflow model.'})
    return result


def build(analysis,allowance=100,draws=10000):
    if allowance<=0 or not math.isfinite(allowance):raise ValueError('allowance must be finite and positive')
    if draws<1:raise ValueError('draws must be positive')
    records=workflow_rows(analysis)
    summaries=[];tasks=[];exclusions=[];ratios=[]
    for effort in ('high','low'):
        for pricing in PRICING:
            for provider in PROVIDERS:
                for counterfactual in (False,True):
                    a,b,c=provider_estimates(records,effort,provider,pricing,allowance,draws,counterfactual)
                    summaries.extend(a);tasks.extend(b);exclusions.extend(c)
            for counterfactual in (False,True):ratios.extend(paired_quantity_ratios(records,effort,pricing,allowance,draws,counterfactual))
    return {'schema_version':'magpie-quantity-v1','generated_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'source_analysis_generated_at':analysis.get('generated_at'),'source_analysis_partial_data':analysis.get('partial_data',True),
            'allowance_usd':allowance,'bootstrap_draws':draws,'bootstrap_seed':SEED,
            'formula':'modeled correct workflows per allowance = allowance * mean_task(mean_eligible_trial(correct)) / mean_task(mean_eligible_trial(whole_workflow_list_equivalent_cost))',
            'paired_ratio_formula':'same eligible trial pairs/task clusters: (macro_success_GOAT/macro_cost_GOAT)/(macro_success_Go/macro_cost_Go)',
            'pricing':{'observed_start_period':'sum first+repair measured per-request list-equivalent estimates from analysis; mixed periods remain mixed',
                       'uniform_off_peak':'reprice every known uncached input/cache/output component at USD0.15/0.003/0.60 per million',
                       'uniform_peak':'reprice every known uncached input/cache/output component at USD0.30/0.006/1.20 per million'},
            'interpretation':[
                'A workload model using the same nominal dollar allowance; not exact billing, subscription deductions, guaranteed purchasable tasks or residual quota.',
                'Task clusters have equal weight; compute ratio of macro means, not mean of per-task success/cost ratios. Repetitions/check assertions are not independent task samples.',
                'Every measured first+needed-repair cost is included for actual workflows, even failures. Missing any stage usage/cache/cost stays unknown; unknown whole workflow costs are not reconstructed from known repair-only costs.',
                'Actual strict and actual conservative-extracted endpoints share exactly the same eligible known-cost/known-outcome workflows within provider/effort/pricing. Strict-only known costs excluded for pending semantic diagnostics remain visible.',
                'Provider summaries can have different known-cost subsets; use matched-provider ratio rows for direct comparison. Coverage and exclusions may be informative and can bias a known-usage-only model.',
                'Auto-strip is a separate posthoc deterministic counterfactual: first cost if normalized first passes, else actual whole-workflow cost; no new API billing/speed measurement and no change to actual spent cost or wait.',
                'Uniform repricing holds measured token/cache/repair behavior fixed; it does not predict a different peak/off-peak model behavior or cache policy. Completion tokens include reasoning and are charged once.',
                'Monthly models do not simulate 5-hour/weekly limits, subscription discounts/allowance multipliers, changing cache hits or a different real workload. No arbitrary weighted overall winner is selected.',
                'Unknown administrative/interrupted usage remains outside known-cost totals and is explicitly counted; gateway zeros never become free work.'
            ],
            'tables':{'workflow_cost_records':records,'quantity_summaries':summaries,'task_cost_summaries':tasks,'exclusion_summaries':exclusions,
                      'paired_quantity_ratios':ratios,'request_workflow_accounting':request_accounting(analysis,records)}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument('--draws',type=int,default=10000)
    parser.add_argument('--allowance',type=float,default=100)
    args=parser.parse_args()
    source=args.root/'analysis.json'
    source_bytes=source.read_bytes()
    analysis=json.loads(source_bytes)
    result=build(analysis,args.allowance,args.draws)
    result['source_analysis_sha256']=hashlib.sha256(source_bytes).hexdigest()
    destination=args.root/'quantity.json'
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'written':str(destination),'source_partial':result['source_analysis_partial_data'],
                      'workflow_records':len(result['tables']['workflow_cost_records']),'quantity_rows':len(result['tables']['quantity_summaries']),
                      'paired_ratio_rows':len(result['tables']['paired_quantity_ratios'])},ensure_ascii=False))

if __name__=='__main__':main()
