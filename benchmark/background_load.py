"""Aggregate contemporaneous Magpie traffic; never export account IDs/prompts."""
import datetime
import json
import os
import statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def dt(value):
    return datetime.datetime.fromisoformat(value)
def run():
    path=ROOT/'requests.jsonl';requests=[json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    if not requests:return
    first=min(dt(r['started']) for r in requests);last=max(dt(r['ended']) for r in requests)
    intervals=[];malformed=0
    usage_path=Path(os.environ.get('MAGPIE_USAGE_LOG',Path.home()/'.config/magpie/usage.jsonl')).expanduser()
    if not usage_path.exists():
        raise FileNotFoundError(f'Set MAGPIE_USAGE_LOG to an existing Magpie usage JSONL file: {usage_path}')
    for line in usage_path.read_text().splitlines():
        try:r=json.loads(line)
        except Exception:malformed+=1;continue
        if str(r.get('session','')).startswith('magpie-v2-'):continue
        if r.get('provider') not in ['opencode-go','commandcode-plan']:continue
        if r.get('model') not in ['deepseek-v4.1-flash','deepseek/deepseek-v4.1-flash']:continue
        start=dt(r['t']);end=start+datetime.timedelta(milliseconds=r.get('ms',0))
        if end<first or start>last:continue
        intervals.append({'provider':r['provider'],'start':start,'end':end,'status':r.get('status')})
    rows=[]
    for r in requests:
        start=dt(r['started']);end=dt(r['ended']);p={'go':'opencode-go','goat':'commandcode-plan'}[r['provider']]
        overlaps=[x for x in intervals if x['provider']==p and max(start,x['start'])<min(end,x['end'])]
        rows.append({'attempt_id':r['attempt_id'],'provider':r['provider'],'phase':r['phase'],'same_model_background_calls_overlapping':len(overlaps),'summed_background_overlap_seconds':sum((min(end,x['end'])-max(start,x['start'])).total_seconds() for x in overlaps)})
    out={'source':'local Magpie usage log, aggregate only','not_causal_attribution':True,'window_start':first.isoformat(),'window_end':last.isoformat(),'malformed_rows_skipped':malformed,'background_calls_by_provider':{p:sum(x['provider']==p for x in intervals) for p in ['opencode-go','commandcode-plan']},'request_overlap':rows,'limitation':'Only logged completed background calls are visible; in-flight activity and other models/providers are not measured. Summed overlaps may exceed elapsed time when multiple calls overlap.'}
    (ROOT/'background-load.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({'background':out['background_calls_by_provider'],'bench_requests':len(rows)}))
if __name__=='__main__':run()
