import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import sys
import uuid
from client import ROOT,call,append
from grading import grade

TOOLS=[
 {'type':'function','function':{'name':'list_files','description':'List all paths in the isolated synthetic repository.','parameters':{'type':'object','properties':{},'additionalProperties':False}}},
 {'type':'function','function':{'name':'read_file','description':'Read one repository file.','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}}},
 {'type':'function','function':{'name':'write_file','description':'Replace one allowed source file with complete Python source. Tests are immutable.','parameters':{'type':'object','properties':{'path':{'type':'string'},'content':{'type':'string'}},'required':['path','content'],'additionalProperties':False}}},
 {'type':'function','function':{'name':'run_tests','description':'Run the immutable repository validator. Returns counts and at most three failing diagnostics.','parameters':{'type':'object','properties':{},'additionalProperties':False}}},
]

def run_episode(repo,rep,p):
    trial=f"{repo['id']}-r{rep}";out=ROOT/'tool-results.jsonl'
    old=[json.loads(s) for s in out.read_text().splitlines()] if out.exists() else []
    if any(r['trial_id']==trial and r['provider']==p for r in old):return
    files=copy.deepcopy(repo['files']);sid='magpie-v2-'+str(uuid.uuid4())
    messages=[{'role':'system','content':'You are a careful software engineer working in an isolated repository. Inspect files, fix the general behavior and run tests. Only provided tools exist. Python 3.12; follow the repository prompt restrictions. Validator limits are 15 seconds CPU, 20 seconds wall time, 768 MiB memory. Finish with a concise summary when done.'},{'role':'user','content':repo['prompt']}]
    responses=[];trace=[];termination='turn_cap';tool_errors=0
    for turn in range(12):
        r=call(p,messages,trial_id=trial+f'-t{turn:02d}',phase='tools',session=sid,tools=TOOLS,metadata={'repository_id':repo['id'],'repetition':rep,'episode_trial':trial,'turn':turn,'concurrency_per_provider':1})
        responses.append(r)
        if not r['complete']:termination=r['failure_class'] or 'incomplete';break
        if not r['tool_calls']:termination='final';break
        messages.append({'role':'assistant','content':r['content'] or None,'tool_calls':r['tool_calls']})
        for tc in r['tool_calls']:
            name=tc['function']['name']
            try:
                args=json.loads(tc['function']['arguments'])
                if name=='list_files':answer={'files':sorted(files)}
                elif name=='read_file':
                    path=args.get('path');answer={'path':path,'content':files[path]} if path in files else {'error':'file_not_found'}
                elif name=='write_file':
                    path=args.get('path');content=args.get('content')
                    if path not in repo['write_paths']:answer={'error':'path_not_writable'}
                    elif not isinstance(content,str) or len(content)>256000:answer={'error':'invalid_source_size_or_type'}
                    else:files[path]=content;answer={'written':path,'characters':len(content)}
                elif name=='run_tests':
                    g=grade('repository',repo['id'],files=files)
                    answer={'passed':g.get('passed'),'passed_checks':g.get('passed_checks'),'total':g.get('total'),'failures':[json.dumps(c,ensure_ascii=False)[:800] for c in g.get('checks',[]) if not c.get('ok')][:3]}
                    if g.get('error'):answer['error']=str(g['error'])[:800]
                else:answer={'error':'unknown_tool'}
            except Exception as e:answer={'error':type(e).__name__+': '+str(e)[:800]}
            if answer.get('error'):tool_errors+=1
            trace.append({'turn':turn,'tool':name,'arguments':tc['function']['arguments'],'result':answer})
            messages.append({'role':'tool','tool_call_id':tc['id'],'content':json.dumps(answer,ensure_ascii=False)})
    g=grade('repository',repo['id'],files=files)
    result={'provider':p,'trial_id':trial,'repository_id':repo['id'],'repetition':rep,'session':sid,'responses':responses,'trace':trace,'termination':termination,'censored':termination=='turn_cap','tool_errors':tool_errors,'grade':g,'source_pass':bool(g.get('passed')),'episode_success':bool(g.get('passed') and termination=='final'),'seconds':sum(r['total_ms'] for r in responses)/1000,'final_files':files}
    append(out,result)
    print(json.dumps({'event':'tool_episode_grade','provider':p,'trial':trial,'turns':len(responses),'source_pass':result['source_pass'],'termination':termination,'seconds':round(result['seconds'],1)}),flush=True)

def run():
    spec=importlib.util.spec_from_file_location('scenario_bank',ROOT/'scenarios/bank.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    repos=m.repositories();assert len(repos)==2
    (ROOT/'repository-tasks.json').write_text(json.dumps(repos,ensure_ascii=False,indent=2));(ROOT/'tool-schemas.json').write_text(json.dumps(TOOLS,indent=2))
    frozen={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'PLAN.md',ROOT/'client.py',ROOT/'worker.py',ROOT/'grading.py',ROOT/'run_tools.py',ROOT/'scenarios/bank.py',ROOT/'repository-tasks.json',ROOT/'tool-schemas.json']}
    (ROOT/'freeze-tools.json').write_text(json.dumps(frozen,indent=2))
    for rep in range(3):
        for repo in (repos if rep%2==0 else list(reversed(repos))):
            with concurrent.futures.ThreadPoolExecutor(2) as ex:
                jobs=[ex.submit(run_episode,repo,rep,p) for p in (['go','goat'] if rep%2==0 else ['goat','go'])]
                for f in concurrent.futures.as_completed(jobs):f.result()

if __name__=='__main__':run()
