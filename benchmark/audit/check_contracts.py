"""Non-author local checks of frozen coding contracts, without external calls."""
import copy
import hashlib
import importlib.util
import json
import random
import shutil
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent/'contracts'
SNAPSHOT = HERE/'contracts_snapshot'
SNAPSHOT.mkdir(exist_ok=True)
for filename in ['bank.py','fixtures.json','manifest.json']:
    shutil.copy2(ORIGINAL/filename, SNAPSHOT/filename)
spec = importlib.util.spec_from_file_location('independent_contract_bank', SNAPSHOT/'bank.py')
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)
results = {'python':sys.version,'hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SNAPSHOT.iterdir() if p.is_file()},'no_model_calls':True,'no_credentials_read':True,'references':[],'negative_controls':[],'independent_checks':[]}
for task, entry in bank.controls().items():
    good, bad = entry['reference'], entry['negative']
    assert good['passed'] and good['passed_checks']==good['total'], (task,good)
    assert not bad['passed'], (task,bad)
    results['references'].append({'task':task,'passed':good['passed_checks'],'total':good['total']})
    results['negative_controls'].append({'task':task,'passed':bad['passed_checks'],'total':bad['total'],'failed':[c['name'] for c in bad['checks'] if not c['ok']]})

apis = {task:bank._load_source(source)[bank.API[task]] for task,source in bank.REFS.items()}
def record(name):
    results['independent_checks'].append({'id':name,'ok':True})
def raises(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('expected ValueError')
def same(actual,expected):
    assert bank._strict_equal(actual,expected),(actual,expected)

# Streaming tests assert dispatch timing and state transitions, not only final output.
p = apis['sse_stream']()
same(p.feed(b'\xef\xbb'),[])
same(p.feed(b'\xbfid: keep\r'),[])
same(p.feed(b'\nretry: 007\rdata: x\r'),[])
same(p.feed(b'\r'),[{'event':'message','data':'x','id':'keep','retry':7}])
same(p.feed(b'\ndata:\n\n'),[{'event':'message','data':'','id':'keep','retry':7}])
same(p.feed('event: gone\n\n\ufeffdata: ignored\ndata: kept\n\n'.encode()),[{'event':'message','data':'kept','id':'keep','retry':7}])
same(p.finish(),[])
same(p.finish(),[])
raises(lambda:p.feed(b''))
record('sse_stream/fragmented_BOM_CRLF_empty_data_sticky_fields_dispatch_and_seal')

def ttl_oracle(capacity,ops):
    order=[]
    values={}
    out=[]
    for op in ops:
        for key in list(order):
            if values[key][1]<=op['t']:
                order.remove(key);del values[key]
        kind=op['op'];key=op.get('key');value=None
        if kind=='put':
            if key in values:order.remove(key);del values[key]
            if capacity and op['ttl']>0:
                order.append(key);values[key]=(op['value'],op['t']+op['ttl'])
        elif kind=='get':
            if key in values:
                value=values[key][0];order.remove(key);order.append(key)
        elif kind=='delete':
            value=key in values
            if value:order.remove(key);del values[key]
        elif kind=='resize':capacity=op['capacity']
        elif kind=='items':value=[[k,values[k][0]] for k in order]
        while len(order)>capacity:del values[order.pop(0)]
        out.append(value)
    return out
rng=random.Random(9723)
for trial in range(100):
    ops=[];now=0;cap=rng.randrange(5)
    for i in range(30):
        now+=rng.choice([0,1,2])
        kind=rng.choice(['put','get','delete','resize','items'])
        op={'op':kind,'t':now,'key':rng.choice(['','x','雪'])}
        if kind=='put':op.update(value=rng.randrange(-2,3),ttl=rng.randrange(-1,5))
        if kind=='resize':op['capacity']=rng.randrange(5)
        ops.append(op)
    same(apis['ttl_lru'](cap,copy.deepcopy(ops)),ttl_oracle(cap,ops))
record('ttl_lru/100_fresh_random_sequences_against_list_order_oracle')

ev=lambda key,moves,expected=None:dict({'id':key,'moves':moves},**({'expected':expected} if expected is not None else {}))
events=[ev('x',[['a','b',True]]),ev('x',[['a','b',1]]),ev('y',[['a','b',1.0]]),ev('y',[['a','b',1]]),ev('z',[['a','b',3],['b','c',4]]),ev('g',[['a','missing',2]],{'a':999}),ev('v',[['a','b',2],['b','c',2]])]
same(apis['atomic_ledger']({'a':5,'b':0,'c':0},events),{'balances':{'a':3,'b':0,'c':2},'results':[{'id':e['id'],'status':status} for e,status in zip(events,['invalid','conflict','invalid','duplicate','insufficient','invalid','applied'])]})
record('atomic_ledger/type_sensitive_idempotency_invalid_precedence_and_rollback')

job=lambda key,d,p,deps:dict(id=key,duration=d,priority=p,deps=deps)
jobs=[job('a',2,0,[]),job('b',2,0,[]),job('z',1,100,['a','b']),job('c',5,-10,[]),job('q',1,5,['a'])]
same(apis['priority_schedule'](jobs,2),[{'id':'a','start':0,'end':2,'worker':0},{'id':'b','start':0,'end':2,'worker':1},{'id':'z','start':2,'end':3,'worker':0},{'id':'q','start':2,'end':3,'worker':1},{'id':'c','start':3,'end':8,'worker':0}])
raises(lambda:apis['priority_schedule'](jobs+[job('orphan',1,0,['orphan'])],2))
record('priority_schedule/simultaneous_completion_priority_ties_and_irrelevant_cycle')

same(apis['json_patch']({'a':[{'x':1},2],'~1':5},[{'op':'move','from':'/a/0','path':'/a/1'},{'op':'copy','from':'/a/1','path':'/-'},{'op':'test','path':'/~01','value':5}]),{'a':[2,{'x':1}],'~1':5,'-':{'x':1}})
raises(lambda:apis['json_patch']({'a':{'':1}},[{'op':'move','from':'/a','path':'/a/'}]))
raises(lambda:apis['json_patch']([1],[{'op':'test','path':'/0','value':True}]))
same(apis['json_patch']([1],[{'op':'test','path':'/0','value':1.0}]),[1])
record('json_patch/decoded_pointer_move_after_remove_literal_dash_and_JSON_equality')

for pattern,path,expected in [('**/**/雪/**','雪',True),('a/**/b','a/x/y/b',True),(r'\**','*x',True),(r'\**','x',False),('a?','a\n',True),('**','',True),('*','',False),('[a]','[a]',True)]:
    same(apis['path_glob'](pattern,path),expected)
raises(lambda:apis['path_glob']('mismatch/\\','different'))
record('path_glob/multiple_globstars_escaped_star_newline_and_eager_validation')

def allocation_oracle(limit,ops):
    allocations={};answers=[]
    def fits(start,n,key):
        used={i for k,(s,size) in allocations.items() if k!=key for i in range(s,s+size)}
        return start+n<=limit and all(i not in used for i in range(start,start+n))
    for op in ops:
        key=op['id'];kind=op['op'];answer=None
        if kind=='free':answer=key in allocations;allocations.pop(key,None)
        elif (kind=='alloc' and key not in allocations) or (kind=='resize' and key in allocations):
            n=op['size'];align=op['align'];skip=key if kind=='resize' else None
            old=allocations[key][0] if kind=='resize' else None
            if old is not None and old%align==0 and fits(old,n,skip):answer=old
            else:answer=next((s for s in range(limit+1) if s%align==0 and fits(s,n,skip)),None)
            if answer is not None:allocations[key]=[answer,n]
        answers.append(answer)
    occupied={i for s,n in allocations.values() for i in range(s,s+n)}
    free=[];pos=0
    while pos<limit:
        if pos in occupied:pos+=1;continue
        end=pos+1
        while end<limit and end not in occupied:end+=1
        free.append([pos,end]);pos=end
    return {'results':answers,'allocations':allocations,'free':free}
for trial in range(100):
    limit=rng.randrange(20);ops=[]
    for i in range(25):
        kind=rng.choice(['alloc','resize','free']);op={'op':kind,'id':rng.choice('abcd')}
        if kind!='free':op.update(size=rng.randrange(1,12),align=rng.randrange(1,9))
        ops.append(op)
    same(apis['interval_allocator'](limit,copy.deepcopy(ops)),allocation_oracle(limit,ops))
record('interval_allocator/100_fresh_random_sequences_against_cell_occupancy_oracle')

wire=lambda body:len(body).to_bytes(4,'big')+body
p=apis['utf8_frames'](5)
same(p.feed(wire(b'')+wire('雪'.encode())[:5]),[''])
same(p.feed(wire('雪'.encode())[5:]),['雪'])
same(p.finish(),None)
raises(lambda:p.feed(b''))
same(p.finish(),None)
p=apis['utf8_frames'](2)
raises(lambda:p.feed(wire(b'a')+wire(b'\xff')))
raises(lambda:p.finish())
raises(lambda:p.feed(b''))
record('utf8_frames/zero_frame_byte_length_seal_and_permanent_error_poison')

def half_up(value):
    return (2*value.numerator+value.denominator)//(2*value.denominator)
def invoice_oracle(items,rate,coupon):
    money=lambda n:f'{n//100}.{n%100:02d}'
    gross=[half_up(Fraction(i['unit'])*i['qty']*100) for i in items]
    subtotal=sum(gross);discount=min(half_up(Fraction(coupon)*100),subtotal)
    shares=[Fraction(discount*g,subtotal) if subtotal else Fraction(0) for g in gross]
    discounts=[s.numerator//s.denominator for s in shares]
    for i in sorted(range(len(items)),key=lambda i:(-(shares[i]-discounts[i]),i))[:discount-sum(discounts)]:discounts[i]+=1
    lines=[]
    for i,g,d in zip(items,gross,discounts):
        n=g-d;t=half_up(Fraction(n)*Fraction(rate)) if i['taxable'] else 0
        lines.append({k:money(v) for k,v in dict(gross=g,discount=d,net=n,tax=t,total=n+t).items()})
    tax=sum(int(Fraction(line['tax'])*100) for line in lines)
    return dict(lines=lines,subtotal=money(subtotal),discount=money(discount),net=money(subtotal-discount),tax=money(tax),total=money(subtotal-discount+tax))
for trial in range(100):
    items=[dict(unit=f'{rng.randrange(5)}.{rng.randrange(10000):04d}',qty=rng.randrange(20),taxable=bool(rng.randrange(2))) for i in range(rng.randrange(12))]
    rate=rng.choice(['0','0.005','0.0825','0.5','1']);coupon=f'{rng.randrange(100)}.{rng.randrange(1000):03d}'
    same(apis['decimal_invoice'](copy.deepcopy(items),rate,coupon),invoice_oracle(items,rate,coupon))
record('decimal_invoice/100_fresh_cases_against_fraction_only_oracle')

mig=lambda key,deps=(),reversible=True:dict(id=key,deps=list(deps),reversible=reversible)
registry=[mig('a'),mig('b',['a']),mig('c',['a']),mig('d',['b']),mig('x'),mig('y',['x'])]
same(apis['migration_plan'](['a','b','c','d'],['y'],registry),['-d','-c','-b','-a','+x','+y'])
same(apis['migration_plan'](['a','b'],['d'],registry),['+d'])
raises(lambda:apis['migration_plan']([],[],registry+[mig('bad',['bad'])]))
record('migration_plan/rollback_largest_then_forward_smallest_closure_and_global_validation')

def route_oracle(edges,start,goal):
    candidates=[]
    def visit(path,cost):
        if path[-1]==goal:candidates.append((cost,len(path)-1,tuple(path)));return
        for source,dest,w in edges:
            if source==path[-1] and dest not in path:visit(path+[dest],cost+w)
    visit([start],0)
    if not candidates:return None
    cost,hops,path=min(candidates)
    return {'cost':cost,'path':list(path)}
for trial in range(100):
    nodes=['s','a','雪','ab','t'];edges=[[a,b,rng.randrange(4)] for a in nodes for b in nodes if rng.random()<.25]
    same(apis['shortest_route'](copy.deepcopy(edges),'s','t'),route_oracle(edges,'s','t'))
record('shortest_route/100_fresh_graphs_against_simple_path_enumeration')

events=[dict(id='high',ts=4,actor='a',writes={'x':None}),dict(id='mid',ts=3,actor='a',writes={'x':2,'y':2}),dict(id='low',ts=2,actor='z',writes={'y':{'k':[1]}})]
expected={'values':{'y':{'k':[1]}},'tombstones':['x'],'accepted':['high','low'],'rejected':['mid']}
same(apis['record_conflicts'](events),expected)
same(apis['record_conflicts'](list(reversed(events))+[copy.deepcopy(events[0])]),expected)
raises(lambda:apis['record_conflicts']([dict(id='x',ts=1,actor='a',writes={'k':True}),dict(id='x',ts=1,actor='a',writes={'k':1})]))
record('record_conflicts/atomic_no_fallback_tombstones_permutation_duplicates_and_JSON_bool_distinction')

# Only known local reference/control source has run in this audit process.
# Generated model source still requires the main runner's isolated worker.
results['total_frozen_checks']=sum(x['total'] for x in results['references'])
results['all_original_hashes_unchanged']=all(hashlib.sha256((ORIGINAL/name).read_bytes()).hexdigest()==value for name,value in results['hashes'].items())
(HERE/'contract-acceptance-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in results.items() if k!='negative_controls'},ensure_ascii=False,indent=2))
print('negative controls rejected:',len(results['negative_controls']))
