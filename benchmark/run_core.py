import concurrent.futures
import hashlib
import importlib.util
import json
import random
import sys
from pathlib import Path
from client import ROOT,call,append
from grading import grade,feedback

SYSTEM='''You are a precise software engineer. Implement the complete requested contract in Python 3.12. Output only the full source file, no Markdown. No filesystem, network or process access. Standard-library imports allowed: collections, heapq, re, json, codecs, typing, datetime, math, bisect, functools, decimal, itertools, copy, dataclasses, enum, fractions, unicodedata. The deterministic grader allows 15 seconds CPU, 20 seconds wall time and 768 MiB memory. Do not run external tools; implement the general behavior.'''

def load_bank():
    spec=importlib.util.spec_from_file_location('contract_bank',ROOT/'contracts/bank.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def rows(path):
    if not path.exists():return []
    out=[]
    for s in path.read_text().splitlines():
        try:out.append(json.loads(s))
        except json.JSONDecodeError:continue
    return out

def excluded_attempts():
    p=ROOT/'collector-interruptions.json'
    return set(json.loads(p.read_text()).get('excluded_attempt_ids',[])) if p.exists() else set()

def one(task,rep,provider):
    trial=f"{task['id']}-r{rep}"
    previous=[r for r in rows(ROOT/'core-results.jsonl') if r['trial_id']==trial and r['provider']==provider]
    if previous:return previous[-1]
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':task['prompt']+f'\nEvaluation trial: {rep}. The behavioral contract is unchanged.'}]
    excluded=excluded_attempts()
    existing=[r for r in rows(ROOT/'requests.jsonl') if r['phase']=='core_first' and r['trial_id']==trial and r['provider']==provider and r['attempt_id'] not in excluded]
    r=existing[-1] if existing else call(provider,messages,trial_id=trial,phase='core_first',metadata={'task_id':task['id'],'repetition':rep,'concurrency_per_provider':2})
    g=grade('code',task['id'],source=r['content']) if r['complete'] else {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':r.get('failure_class'),'failure_class':r.get('failure_class')}
    result={'provider':provider,'task_id':task['id'],'trial_id':trial,'repetition':rep,'first':r,'first_grade':g,'repair':None,'repair_grade':None}
    # Initial outcomes are persisted immediately before any potential repair.
    append(ROOT/'core-first-grades.jsonl',{'provider':provider,'task_id':task['id'],'trial_id':trial,'attempt_id':r['attempt_id'],'grade':g})
    if not g.get('passed'):
        fm=feedback(g,r)
        repair_messages=messages+([{'role':'assistant','content':r['content']}] if r['content'].strip() else [])+[{'role':'user','content':fm}]
        prior=[x for x in rows(ROOT/'requests.jsonl') if x['phase']=='core_repair' and x['trial_id']==trial and x['provider']==provider and x['attempt_id'] not in excluded]
        rr=prior[-1] if prior else call(provider,repair_messages,trial_id=trial,phase='core_repair',session=r['session'],metadata={'task_id':task['id'],'repetition':rep,'concurrency_per_provider':2,'feedback':fm})
        gg=grade('code',task['id'],source=rr['content']) if rr['complete'] else {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':rr.get('failure_class'),'failure_class':rr.get('failure_class')}
        result.update(repair=rr,repair_grade=gg)
    result['solved']=bool(g.get('passed') or (result['repair_grade'] or {}).get('passed'))
    result['total_seconds']=(r['total_ms']+(result['repair'] or {}).get('total_ms',0))/1000
    append(ROOT/'core-results.jsonl',result)
    print(json.dumps({'event':'core_grade','provider':provider,'task':task['id'],'rep':rep,'first_pass':g.get('passed'),'solved':result['solved'],'seconds':round(result['total_seconds'],1)}),flush=True)
    return result

def run():
    tasks=load_bank().tasks();assert len(tasks)==12
    (ROOT/'core-tasks.json').write_text(json.dumps(tasks,ensure_ascii=False,indent=2))
    rng=random.Random(51987)
    spec=[(t,rep) for rep in range(3) for t in tasks];rng.shuffle(spec)
    (ROOT/'core-order.json').write_text(json.dumps([{'task_id':t['id'],'rep':rep} for t,rep in spec],indent=2))
    frozen={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'PLAN.md',ROOT/'client.py',ROOT/'worker.py',ROOT/'grading.py',ROOT/'run_core.py',*sorted((ROOT/'contracts').glob('*.py')),*sorted((ROOT/'contracts').glob('*.json'))]}
    (ROOT/'freeze-core.json').write_text(json.dumps(frozen,indent=2))
    for start in range(0,len(spec),2):
        batch=spec[start:start+2];jobspec=[]
        for i,(task,rep) in enumerate(batch):
            for p in (['go','goat'] if (start+i)%2==0 else ['goat','go']):jobspec.append((task,rep,p))
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            jobs=[ex.submit(one,*x) for x in jobspec]
            for f in concurrent.futures.as_completed(jobs):f.result()

if __name__=='__main__':run()
