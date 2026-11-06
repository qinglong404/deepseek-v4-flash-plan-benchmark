"""Exact-provider Magpie streaming client. Credentials are read only in memory."""
import datetime
import hashlib
import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parent
MODELS={'go':'opencode-go/deepseek-v4.1-flash','goat':'commandcode-plan/deepseek/deepseek-v4.1-flash'}
_WRITE_LOCK=threading.Lock()

def gateway_options():
    config_path=os.environ.get('MAGPIE_CONFIG')
    if config_path:
        return json.loads(Path(config_path).expanduser().read_text())['provider']['magpie']['options']
    options={'baseURL':os.environ.get('MAGPIE_BASE_URL',''),'apiKey':os.environ.get('MAGPIE_API_KEY','')}
    if not options['baseURL'] or not options['apiKey']:
        raise RuntimeError('Set MAGPIE_CONFIG or both MAGPIE_BASE_URL and MAGPIE_API_KEY before live collection')
    return options

def append(path,value):
    with _WRITE_LOCK:
        with Path(path).open('a') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')

def call(provider,messages,*,trial_id,phase,effort='high',max_tokens=65536,session=None,tools=None,metadata=None,deadline=600):
    cfg=gateway_options()
    sid=session or 'magpie-v2-'+str(uuid.uuid4())
    body={'model':MODELS[provider],'messages':messages,'stream':True,'stream_options':{'include_usage':True},'max_tokens':max_tokens,'temperature':0,'reasoning_effort':effort}
    if tools:body.update(tools=tools,tool_choice='auto')
    headers={'Authorization':'Bearer '+cfg['apiKey'],'Content-Type':'application/json','User-Agent':'magpie-coding-benchmark/2.0','x-opencode-session':sid,'x-session-id':sid}
    started=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    r={'attempt_id':str(uuid.uuid4()),'provider':provider,'model_requested':MODELS[provider],'phase':phase,'trial_id':trial_id,'session':sid,'started':started.isoformat(),'effort_requested':effort,'max_tokens':max_tokens,'temperature':0,'content':'','reasoning_chars':0,'usage':{},'models_seen':[],'tool_calls':[],'done':False,'metadata':metadata or {}}
    r['messages_sha256']=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    r['request_sha256']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    append(ROOT/'attempt-journal.jsonl',{'event':'started',**{k:r[k] for k in ['attempt_id','provider','phase','trial_id','session','started','model_requested','effort_requested','max_tokens','messages_sha256','request_sha256']}})
    t=time.perf_counter();delta_times=[];deadline_hit=threading.Event();active={}
    def abort():
        deadline_hit.set()
        response=active.get('response')
        if response is not None:
            try:
                stream=getattr(response,'extensions',{}).get('network_stream')
                sock=stream.get_extra_info('socket') if stream else None
                if sock is not None:sock.shutdown(socket.SHUT_RDWR)
            except Exception:pass
            try:response.close()
            except Exception:pass
    timer=threading.Timer(deadline,abort);timer.daemon=True;timer.start()
    try:
        timeout=httpx.Timeout(min(180,deadline),connect=min(20,deadline),write=min(90,deadline),pool=min(20,deadline))
        with httpx.Client(timeout=timeout,trust_env=False) as cli:
            with cli.stream('POST',cfg['baseURL'].rstrip('/')+'/chat/completions',json=body,headers=headers) as res:
                active['response']=res
                r['status']=res.status_code;r['headers_ms']=(time.perf_counter()-t)*1000
                r['response_headers']={k:v for k,v in res.headers.items() if any(z in k.lower() for z in ['magpie','model','provider','request-id']) and not any(z in k.lower() for z in ['key','token','account'])}
                if res.status_code>=400:
                    r['error']=res.read().decode(errors='replace')[:2000]
                else:
                    for line in res.iter_lines():
                        elapsed=(time.perf_counter()-t)*1000
                        if elapsed>deadline*1000 or deadline_hit.is_set():
                            r['error']=f'application_deadline_{deadline}s';r['deadline_hit']=True;break
                        if not line.startswith('data:'):continue
                        text=line[5:].strip()
                        if text=='[DONE]':r['done']=True;break
                        try:j=json.loads(text)
                        except Exception:
                            r['malformed_events']=r.get('malformed_events',0)+1;continue
                        if j.get('error'):r['stream_error']=j['error']
                        if j.get('model') and j['model'] not in r['models_seen']:r['models_seen'].append(j['model'])
                        if j.get('usage'):r['usage']=j['usage']
                        for c in j.get('choices',[]):
                            d=c.get('delta') or {};content=d.get('content') or '';reason=d.get('reasoning_content') or d.get('reasoning') or ''
                            calls=d.get('tool_calls') or []
                            if content or reason or calls:r.setdefault('first_event_ms',elapsed)
                            if content or calls:r.setdefault('first_visible_ms',elapsed)
                            if content:
                                r.setdefault('first_text_ms',elapsed);r['last_text_ms']=elapsed;r['content']+=content
                                if len(delta_times)<5000:delta_times.append([round(elapsed,2),len(content)])
                            r['reasoning_chars']+=len(reason)
                            for tc in calls:
                                ix=tc.get('index',0)
                                while len(r['tool_calls'])<=ix:r['tool_calls'].append({'id':'','type':'function','function':{'name':'','arguments':''}})
                                cur=r['tool_calls'][ix]
                                if tc.get('id'):cur['id']=tc['id']
                                for k,v in (tc.get('function') or {}).items():
                                    if isinstance(v,str):cur['function'][k]=cur['function'].get(k,'')+v
                            if c.get('finish_reason'):r['finish_reason']=c['finish_reason']
    except Exception as e:r['error']=type(e).__name__+': '+str(e)[:1500]
    finally:timer.cancel()
    if deadline_hit.is_set():r['deadline_hit']=True;r['error']=f'application_deadline_{deadline}s'
    r['total_ms']=(time.perf_counter()-t)*1000
    r['ended']=(started+datetime.timedelta(milliseconds=r['total_ms'])).isoformat()
    r['text_delta_timeline']=delta_times
    expected={'go':'opencode-go','goat':'commandcode-plan'}[provider]
    actual=r.get('response_headers',{}).get('x-magpie-provider')
    r['route_verified']=actual==expected
    valid_tools=True
    for tc in r['tool_calls']:
        try:
            args=json.loads(tc['function']['arguments'])
            if not tc['id'] or not tc['function']['name'] or not isinstance(args,dict):valid_tools=False
        except Exception:valid_tools=False
    r['tool_arguments_valid']=valid_tools
    payload=bool(r['content'].strip() or (r['tool_calls'] and valid_tools))
    r['complete']=bool(r.get('status',0) in range(200,300) and r['done'] and r.get('finish_reason') in ['stop','tool_calls'] and payload and valid_tools and not r.get('malformed_events') and not r.get('error') and not r.get('stream_error') and r['route_verified'])
    if not r['route_verified']:r['failure_class']='route_unverified'
    elif r.get('deadline_hit'):r['failure_class']='deadline'
    elif r.get('error') or r.get('stream_error'):r['failure_class']='transport'
    elif r.get('finish_reason')=='length':r['failure_class']='length'
    elif r.get('malformed_events') or not valid_tools:r['failure_class']='malformed_protocol'
    elif not r['complete']:r['failure_class']='incomplete_protocol'
    else:r['failure_class']=None
    append(ROOT/'requests.jsonl',r)
    append(ROOT/'attempt-journal.jsonl',{'event':'terminal','attempt_id':r['attempt_id'],'provider':provider,'phase':phase,'trial_id':trial_id,'session':sid,'ended':r['ended'],'complete':r['complete'],'failure_class':r['failure_class']})
    print(json.dumps({'phase':phase,'trial':trial_id,'provider':provider,'seconds':round(r['total_ms']/1000,2),'finish':r.get('finish_reason'),'complete':r['complete'],'failure':r['failure_class']}),flush=True)
    return r
