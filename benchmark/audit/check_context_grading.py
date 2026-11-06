"""Run context runner with a fully local fake client to check exact JSON policy."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
from contextlib import redirect_stdout
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('context_runner_for_audit',ROOT/'run_context.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
folder=HERE/'mock-context-run'
folder.mkdir(exist_ok=True)
(folder/'scenarios').mkdir(exist_ok=True)
for name in ['PLAN.md','client.py','run_context.py']:
    shutil.copy2(ROOT/name,folder/name)
shutil.copy2(ROOT/'scenarios'/'bank.py',folder/'scenarios'/'bank.py')
# Remove only audit-owned previous mock result, so rerunning executes all cases.
if (folder/'context-results.jsonl').exists():(folder/'context-results.jsonl').unlink()

expected={'active_skus':['a','b'],'available_units':1,'available_value_cents':20,'highest_value_sku':'a','over_reserved_skus':[],'owners':{'a':'team','b':None},'restock_needed':0,'most_recent_winner_seq':3,'excluded_conflicting_event_ids':[]}
class FakeBank:
    def context_case(self,size,seed):
        return {'id':f'{size}-{seed}','prompt':'synthetic JSON task','expected':copy.deepcopy(expected),'estimated_tokens':16}
labels=['valid','extra_key','missing_key','bool_for_int','wrong_nested_owner','incomplete_valid_content','fenced_json','wrong_order']
records=[]
def fake_call(p,messages,*,trial_id,phase,metadata,**kwargs):
    i=(['16K','64K','160K','320K'].index(metadata['size_label'])*3+metadata['seed'])*2+(p=='goat')
    variant=i%8;actual=copy.deepcopy(expected);complete=True
    if variant==1:actual['extra']='x'
    elif variant==2:del actual['owners']
    elif variant==3:actual['available_units']=True
    elif variant==4:actual['owners']['a']=True
    elif variant==5:complete=False
    elif variant==7:actual['active_skus'].reverse()
    content=json.dumps(actual)
    if variant==6:content='```json\n'+content+'\n```'
    return {'provider':p,'trial_id':trial_id,'phase':phase,'content':content,'complete':complete,'metadata':metadata,'usage':{'prompt_tokens':16},'total_ms':1,'audit_variant':labels[variant]}
def capture(path,row):
    records.append(row)
    with path.open('a') as f:f.write(json.dumps(row)+'\n')
with patch.object(runner,'ROOT',folder),patch.object(runner,'bank',return_value=FakeBank()),patch.object(runner,'call',side_effect=fake_call),patch.object(runner,'append',side_effect=capture),redirect_stdout(io.StringIO()):
    runner.run()
assert len(records)==24
for row in records:
    assert row['grade']['total']==9
    assert row['grade']['passed'] is (row['audit_variant']=='valid'),row
summary={'no_upstream_calls':True,'no_credential_reads':True,'fake_calls':len(records),'checks':[{'variant':label,'n':sum(r['audit_variant']==label for r in records),'full_json_passed':sum(r['grade']['passed'] for r in records if r['audit_variant']==label)} for label in labels]}
(HERE/'context-grading-results.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
