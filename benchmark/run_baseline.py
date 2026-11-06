import concurrent.futures
import hashlib
import json
import random
import time
from pathlib import Path
from client import ROOT,call,append

SYSTEM='You are a precise coding assistant. Follow the requested code or JSON output contract.'
def fixture(index):
    return f'Create a coding-test fixture: output only a valid JSON array of exactly 64 objects with ids 1 through 64 in that order. Each object has exactly "id" (integer), "path" (string "/benchmark/v2/case{index}/items/" followed by id), and "enabled" (true for even ids, false for odd ids). No Markdown or explanation.'

def valid(r,index):
    try:
        exp=[{'id':n,'path':f'/benchmark/v2/case{index}/items/{n}','enabled':n%2==0} for n in range(1,65)]
        return bool(r['complete'] and json.loads(r['content'])==exp)
    except Exception:return False

def existing():
    p=ROOT/'baseline-results.jsonl'
    return {(r['phase'],r['trial_id'],r['provider']) for r in map(json.loads,p.read_text().splitlines())} if p.exists() else set()

def one(p,phase,trial,index,concurrency,rep):
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':fixture(index)}]
    r=call(p,messages,trial_id=trial,phase=phase,metadata={'concurrency_per_provider':concurrency,'repetition':rep,'fixture_index':index})
    r['grade']={'passed':valid(r,index),'total':1}
    append(ROOT/'baseline-results.jsonl',r)
    return r

def run():
    plan={'serial_pairs':12,'concurrency_levels':[1,2,4],'concurrency_repetitions':2,'output_objects':64,'effort':'high','max_tokens':65536,'created_before_calls':True}
    data=json.dumps(plan,sort_keys=True,indent=2);(ROOT/'baseline-plan.json').write_text(data)
    done=existing()
    for i in range(12):
        trial=f'serial-{i:02d}';order=['go','goat'] if i%2==0 else ['goat','go']
        with concurrent.futures.ThreadPoolExecutor(2) as ex:
            jobs=[ex.submit(one,p,'serial',trial,i,1,i) for p in order if ('serial',trial,p) not in done]
            for f in concurrent.futures.as_completed(jobs):f.result()
    rng=random.Random(8817)
    blocks=[(c,rep) for rep in range(2) for c in [1,2,4]];rng.shuffle(blocks)
    for concurrency,rep in blocks:
        phase='concurrency';trial=f'c{concurrency}-r{rep}'
        jobspec=[(p,i) for i in range(concurrency) for p in (['go','goat'] if (i+rep)%2==0 else ['goat','go'])]
        jobspec=[(p,i) for p,i in jobspec if (phase,f'{trial}-s{i}',p) not in done]
        start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(concurrency*2) as ex:
            jobs=[ex.submit(one,p,phase,f'{trial}-s{i}',100+rep*20+concurrency*4+i,concurrency,rep) for p,i in jobspec]
            for f in concurrent.futures.as_completed(jobs):f.result()
        append(ROOT/'batch-times.jsonl',{'phase':phase,'batch':trial,'concurrency_per_provider':concurrency,'repetition':rep,'wall_seconds':time.perf_counter()-start,'new_requests':len(jobspec)})

if __name__=='__main__':run()
