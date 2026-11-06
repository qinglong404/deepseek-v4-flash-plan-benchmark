"""Post-hoc, conservative wrapper diagnostic; never alters primary scores/retries."""
import json
import re
from client import ROOT,append
from grading import grade

RULE='single_whole_fenced_block_v1'
def extract(text):
    m=re.fullmatch(r'\s*```(?:python|py)?[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*\s*',text)
    if not m:return None
    source=m.group(1)
    if any(line.strip().startswith('```') for line in source.splitlines()):return None
    return source+'\n'

def run():
    target=ROOT/'core-extracted-grades.jsonl'
    done={r['attempt_id'] for r in map(json.loads,target.read_text().splitlines())} if target.exists() else set()
    source=ROOT/'requests.jsonl'
    rows=[json.loads(s) for s in source.read_text().splitlines()] if source.exists() else []
    count=0
    for r in rows:
        if r['phase'] not in ['core_first','core_repair','low_core_first','low_core_repair'] or r['attempt_id'] in done or not r['complete']:continue
        code=extract(r['content'])
        if code is None:continue
        g=grade('code',r['metadata']['task_id'],source=code)
        append(target,{'attempt_id':r['attempt_id'],'provider':r['provider'],'trial_id':r['trial_id'],'stage':'first' if r['phase'].endswith('_first') else 'repair','extraction_rule':RULE,'extracted_code_grade':g})
        count+=1
    print(json.dumps({'new_normalized_attempts':count}))

if __name__=='__main__':run()
