import json
import re
import subprocess
import uuid
from pathlib import Path
from client import ROOT

def grade(kind,task_id,*,source=None,files=None):
    inputs=ROOT/'grade-inputs';inputs.mkdir(exist_ok=True)
    path=inputs/(str(uuid.uuid4())+'.json')
    data={'kind':kind,'task_id':task_id}
    if source is not None:data['source']=source
    if files is not None:data['files']=files
    path.write_text(json.dumps(data,ensure_ascii=False))
    try:
        command=['/usr/bin/bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/bench','--ro-bind',str(ROOT/'worker.py'),'/bench/worker.py','--ro-bind',str(ROOT/'contracts'),'/bench/contracts','--ro-bind',str(ROOT/'scenarios'),'/bench/scenarios','--ro-bind',str(path),'/bench/input.json','--chdir','/bench','--clearenv','--setenv','PATH','/usr/bin:/bin','--setenv','LANG','C.UTF-8','/usr/bin/python3','-I','-S','/bench/worker.py','/bench/input.json']
        r=subprocess.run(command,cwd=ROOT,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},capture_output=True,text=True,timeout=20)
        if r.returncode:
            return {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':f'grader_resource_or_process_exit_{r.returncode}','failure_class':'resource'}
        out=json.loads(r.stdout)
        if type(out.get('passed')) is not bool:
            out['passed_checks']=out.get('passed',0);out['passed']=out.get('passed')==out.get('total') and bool(out.get('total')) and not out.get('error')
        if 'passed_checks' not in out:out['passed_checks']=sum(bool(x.get('ok')) for x in out.get('checks',[]))
        if not out.get('passed'):
            err=str(out.get('error',''))
            out['failure_class']='restriction' if any(s in err.lower() for s in ['restricted','allowlist','forbidden','not allowed','blocked','disallow']) else 'semantic'
        else:out['failure_class']=None
        return out
    except subprocess.TimeoutExpired:
        return {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':'grader_wall_timeout_20s','failure_class':'resource'}
    except Exception as e:
        return {'passed':False,'passed_checks':0,'total':1,'checks':[],'error':type(e).__name__+': '+str(e)[:1200],'failure_class':'grader_error'}

def feedback(g,response):
    problems=[x for x in g.get('checks',[]) if not x.get('ok')][:3]
    bounded=[json.dumps(x,ensure_ascii=False)[:800] for x in problems]
    out='Your previous implementation did not satisfy the fixed tests. Return a corrected complete source file only. Do not change the contract.\n'
    if not response.get('complete'):out+='The previous response did not complete: '+str(response.get('failure_class'))+'.\n'
    if g.get('error'):out+='Evaluator diagnostic: '+str(g['error'])[:800]+'\n'
    if bounded:out+='First failing checks:\n'+'\n'.join(bounded)
    return out[:4000]
