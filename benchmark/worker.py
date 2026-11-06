"""Credential-free isolated grader entrypoint (invoked with /usr/bin/python3 -I -S)."""
import importlib.util
import json
import resource
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024*1024,2*1024*1024))
resource.setrlimit(resource.RLIMIT_NPROC,(1,1))
def main():
    data=json.loads(Path(sys.argv[1]).read_text());kind=data['kind']
    path=ROOT/('contracts' if kind=='code' else 'scenarios')/'bank.py'
    spec=importlib.util.spec_from_file_location('frozen_benchmark_bank',path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    if kind=='code':result=mod.grade(data['task_id'],data['source'])
    elif kind=='repository':result=mod.grade_repository(data['task_id'],data['files'])
    else:raise ValueError('unknown grade kind')
    print(json.dumps(result,ensure_ascii=False,default=str))
try:main()
except BaseException as e:print(json.dumps({'passed':False,'passed_checks':0,'total':1,'checks':[],'error':type(e).__name__+': '+str(e)[:1200]}))
