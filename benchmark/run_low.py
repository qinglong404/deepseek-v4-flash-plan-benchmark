import concurrent.futures
import hashlib
import json
import random
from client import ROOT,call,append
from grading import grade,feedback
from run_core import SYSTEM,load_bank,rows

def one(task,rep,provider):
    trial=f"low-{task['id']}-r{rep}";target=ROOT/'low-core-results.jsonl'
    if any(r['trial_id']==trial and r['provider']==provider for r in rows(target)):return
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':task['prompt']+f'\nEvaluation trial: {rep}. The behavioral contract is unchanged.'}]
    existing=[r for r in rows(ROOT/'requests.jsonl') if r['phase']=='low_core_first' and r['trial_id']==trial and r['provider']==provider]
    r=existing[-1] if existing else call(provider,messages,trial_id=trial,phase='low_core_first',effort='low',metadata={'task_id':task['id'],'repetition':rep,'concurrency_per_provider':2})
    g=grade('code',task['id'],source=r['content']) if r['complete'] else {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':r.get('failure_class'),'failure_class':r.get('failure_class')}
    result={'provider':provider,'task_id':task['id'],'trial_id':trial,'repetition':rep,'first':r,'first_grade':g,'repair':None,'repair_grade':None}
    append(ROOT/'low-core-first-grades.jsonl',{'provider':provider,'task_id':task['id'],'trial_id':trial,'attempt_id':r['attempt_id'],'grade':g})
    if not g.get('passed'):
        fm=feedback(g,r);repair_messages=messages+([{'role':'assistant','content':r['content']}] if r['content'].strip() else [])+[{'role':'user','content':fm}]
        prior=[x for x in rows(ROOT/'requests.jsonl') if x['phase']=='low_core_repair' and x['trial_id']==trial and x['provider']==provider]
        rr=prior[-1] if prior else call(provider,repair_messages,trial_id=trial,phase='low_core_repair',effort='low',session=r['session'],metadata={'task_id':task['id'],'repetition':rep,'concurrency_per_provider':2,'feedback':fm})
        gg=grade('code',task['id'],source=rr['content']) if rr['complete'] else {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':rr.get('failure_class'),'failure_class':rr.get('failure_class')}
        result.update(repair=rr,repair_grade=gg)
    result['solved']=bool(g.get('passed') or (result['repair_grade'] or {}).get('passed'))
    result['total_seconds']=(r['total_ms']+(result['repair'] or {}).get('total_ms',0))/1000
    append(target,result)
    print(json.dumps({'event':'low_core_grade','provider':provider,'task':task['id'],'rep':rep,'first_pass':g.get('passed'),'solved':result['solved'],'seconds':round(result['total_seconds'],1)}),flush=True)

def run():
    tasks=load_bank().tasks();assert len(tasks)==12
    spec=[(task,rep) for rep in range(2) for task in tasks];random.Random(191737).shuffle(spec)
    (ROOT/'low-order.json').write_text(json.dumps([{'task_id':t['id'],'rep':rep} for t,rep in spec]))
    paths=[ROOT/p for p in ['LOW_EFFORT_ADDENDUM.md','client.py','grading.py','worker.py','run_low.py','contracts/bank.py','contracts/fixtures.json']]
    (ROOT/'freeze-low.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},indent=2))
    for start in range(0,len(spec),2):
        jobspec=[(t,rep,p) for i,(t,rep) in enumerate(spec[start:start+2]) for p in (['go','goat'] if (start+i)%2==0 else ['goat','go'])]
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            jobs=[ex.submit(one,*a) for a in jobspec]
            for f in concurrent.futures.as_completed(jobs):f.result()

if __name__=='__main__':run()
