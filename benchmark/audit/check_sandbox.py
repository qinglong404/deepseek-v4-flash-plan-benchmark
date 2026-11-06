"""Non-author rerun of references and controls through actual bwrap boundary."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
contracts=load(HERE/'contracts_snapshot'/'bank.py','sandbox_contract_refs')
scenarios=load(ROOT/'scenarios'/'bank.py','sandbox_repo_refs')
inputs=HERE/'sandbox-inputs'
inputs.mkdir(exist_ok=True)
cases=[]
for task,source in contracts.REFS.items():
    cases.append((task+'/reference',True,{'kind':'code','task_id':task,'source':source}))
    cases.append((task+'/negative',False,{'kind':'code','task_id':task,'source':contracts.NEGATIVES[task]}))
for control in scenarios.controls():
    cases.append((control['id']+'/reference',True,{'kind':'repository','task_id':control['id'],'files':control['reference_files']}))
    for neg in control['negative_controls']:
        cases.append((control['id']+'/'+neg['id'],False,{'kind':'repository','task_id':control['id'],'files':neg['files']}))
results=[]
for i,(name,expected,data) in enumerate(cases):
    path=inputs/(str(i).zfill(2)+'.json')
    path.write_text(json.dumps(data))
    cmd=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/bench','--ro-bind',str(ROOT/'worker.py'),'/bench/worker.py','--ro-bind',str(HERE/'contracts_snapshot'),'/bench/contracts','--ro-bind',str(ROOT/'scenarios'),'/bench/scenarios','--ro-bind',str(path),'/bench/input.json','--chdir','/bench','--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','LANG','C.UTF-8','/usr/bin/python3','-I','-S','/bench/worker.py','/bench/input.json']
    proc=subprocess.run(cmd,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=20)
    assert proc.returncode==0,(name,proc.returncode,proc.stderr)
    grade=json.loads(proc.stdout)
    passed=grade.get('passed')
    if type(passed) is not bool:passed=passed==grade['total'] and grade['total']>0
    assert passed is expected,(name,expected,grade)
    results.append({'id':name,'expected_pass':expected,'actual_pass':passed,'checks_passed':grade.get('passed_checks',grade.get('passed')),'checks_total':grade['total']})
summary={'python_worker':'/usr/bin/python3 -I -S (3.12.3)','worker_sha256':hashlib.sha256((ROOT/'worker.py').read_bytes()).hexdigest(),'grading_sha256_read_review':hashlib.sha256((ROOT/'grading.py').read_bytes()).hexdigest(),'no_model_calls':True,'no_credentials_read':True,'sandbox_boundary':'same bwrap --unshare-all mount/env/process boundary as production grader; only audit input paths differ','results':results}
(HERE/'sandbox-acceptance-results.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'cases':len(results),'references_passed':sum(x['actual_pass'] for x in results),'negatives_rejected':sum(not x['actual_pass'] for x in results),'worker_sha256':summary['worker_sha256']},indent=2))
