"""Authoring-time deterministic fixture freezer; do not invoke during live trials.

Independent spot/exhaustive oracles here are validator-author self-checks, not
independent acceptance by another person/process implementation team.
"""
import copy
import hashlib
import itertools
import json
import random
import re
import bank

R = random.Random(2026110501)
CASES = {k:[] for k in bank.PROMPTS}

def add(task, name, *args, expected=None):
    case = {'name':name,'args':list(args)}
    if expected is not None:
        case['_hand_expected'] = expected
    CASES[task].append(case)

def stream(task,name,chunks,init=None,tail=None):
    case = {'name':name,'steps':[{'op':'feed','hex':c.hex()} for c in chunks] + (tail or [{'op':'finish'},{'op':'finish'},{'op':'feed','hex':''}])}
    if init is not None:
        case['init'] = init
    CASES[task].append(case)

def split_random(data,rng,max_size=7):
    result = []
    pos = 0
    while pos < len(data):
        if rng.random() < 0.15:
            result.append(b'')
        n = rng.randint(1,max_size)
        result.append(data[pos:pos+n])
        pos += n
    return result

# 54 SSE checks: complete/bytewise/adversarial chunking and sticky parser state.
sse_payloads = [
    b'', b'data: x\n\n', b'data\n\n', b'event: custom\ndata: a\ndata: b\n\n',
    b': c\nid: old\nretry: 0012\n\ndata: x\n\nid:\nretry: +5\ndata: y\n\n',
    b'data: x\r\rdata: y\r\ndata: z\r\n\r\n',
    b'event: ignored\n\ndata: a\n\nevent:\ndata: b\n\n',
    b'data:  two spaces\ndata:\ndata\n\n',
    '\ufeffdata: 雪🙂\n\ndata: 끝\n\n'.encode(),
    'data: a\n\n\ufeffdata: b\ndata: c\n\n'.encode(),
    b'id: stable\nid: ignored\x00value\nretry: 23\nretry: 2x\ndata: yes\n\n',
    'retry: １２\ndata: no ascii retry\n\n'.encode(),
    b'data: trailing', b'data: trailing\n', b'data: \xff\xc3(\n\n',
    b'data: a:b:c\nunknown: x\nData: ignored\n\n',
    b'data: one\r\n\r\ndata: two\r\r',
    b'data: before\n\ndata: \xe2\x82',
]
for i,data in enumerate(sse_payloads):
    stream('sse_stream',f'payload-{i:02d}-whole',[data])
    stream('sse_stream',f'payload-{i:02d}-bytewise',[bytes([v]) for v in data])
    stream('sse_stream',f'payload-{i:02d}-random',split_random(data,R))

# TTL LRU: boundary timestamps, recency, overwrite, zero TTL/capacity and churn.
ttl_hand = [
 (0, []),
 (1,[{'op':'put','t':0,'key':'a','value':0,'ttl':1},{'op':'get','t':0,'key':'a'},{'op':'get','t':1,'key':'a'}]),
 (2,[{'op':'put','t':0,'key':'a','value':1,'ttl':10},{'op':'put','t':0,'key':'b','value':2,'ttl':10},{'op':'get','t':0,'key':'a'},{'op':'put','t':0,'key':'c','value':3,'ttl':10},{'op':'items','t':0}]),
 (2,[{'op':'put','t':0,'key':'a','value':1,'ttl':10},{'op':'put','t':0,'key':'b','value':2,'ttl':10},{'op':'put','t':1,'key':'a','value':7,'ttl':0},{'op':'items','t':1}]),
 (2,[{'op':'put','t':0,'key':'a','value':1,'ttl':5},{'op':'put','t':0,'key':'b','value':2,'ttl':3},{'op':'items','t':3},{'op':'resize','t':3,'capacity':0},{'op':'resize','t':4,'capacity':2},{'op':'get','t':4,'key':'a'}]),
 (0,[{'op':'put','t':0,'key':'a','value':1,'ttl':2},{'op':'resize','t':0,'capacity':1},{'op':'put','t':0,'key':'a','value':2,'ttl':1},{'op':'delete','t':1,'key':'a'}]),
 (1,[{'op':'delete','t':0,'key':'a'},{'op':'items','t':5},{'op':'get','t':5,'key':'a'}]),
 (3,[{'op':'put','t':0,'key':k,'value':i,'ttl':i+1} for i,k in enumerate('abc')]+[{'op':'resize','t':1,'capacity':1},{'op':'items','t':1}]),
]
for i,(cap,ops) in enumerate(ttl_hand):
    add('ttl_lru',f'boundary-{i:02d}',cap,ops)
for trial in range(36):
    ops=[]; now=0
    for j in range(R.randint(30,80)):
        now += R.choice([0,0,1,2,5])
        kind=R.choice(['put']*4+['get']*3+['delete','items','resize'])
        op={'op':kind,'t':now}
        if kind in ('put','get','delete'):op['key']=R.choice(['a','b','c','雪','0',''])
        if kind=='put':op.update(value=R.randint(-10,10),ttl=R.choice([-2,0,1,2,5,100]))
        if kind=='resize':op['capacity']=R.randint(0,5)
        ops.append(op)
    ops.append({'op':'items','t':now})
    add('ttl_lru',f'churn-{trial:02d}',R.randint(0,5),ops)

# Ledger first-occurrence idempotency, failed-transaction id consumption and rollback.
def ev(key,moves,expected=None):
    out={'id':key,'moves':moves}
    if expected is not None:out['expected']=expected
    return out
ledger_hand = [
 ({'a':10,'b':0},[]),
 ({'a':10,'b':0},[ev('x',[['a','b',5]]),ev('x',[['a','b',5]])]),
 ({'a':10,'b':0},[ev('x',[['a','b',5]]),ev('x',[['a','b',6]])]),
 ({'a':10,'b':0,'c':0},[ev('x',[['a','b',5],['b','c',6]])]),
 ({'a':10,'b':0,'c':0},[ev('x',[['a','b',5],['b','c',5]])]),
 ({'a':1,'b':0},[ev('x',[['a','b',2]]),ev('x',[['a','b',2]]),ev('x',[['a','b',1]])]),
 ({'a':10,'b':0},[ev('x',[],{'a':10}),ev('y',[],{'a':11})]),
 ({'a':10,'b':0},[ev('x',[['a','b',0]],{'a':11}),ev('y',[['a','a',1]])]),
 ({'a':10,'b':0},[ev('x',[['a','z',1]]),ev('y',[],{'z':0})]),
 ({'a':10,'b':0},[ev('x',[['a','b',True]]),ev('y',[],{'a':True})]),
 ({'a':10,'b':0},[ev('x',[['a','b',1.0]]),ev('y',[['a','b',-1]])]),
 ({'a':10,'b':0},[ev('x',[['a','b',True]]),ev('x',[['a','b',1]])]),
 ({'a':10,'b':0},[ev('x',[['a','b',1.0]]),ev('x',[['a','b',1]])]),
 ({},[ev('x',[]),ev('x',[])]),
]
for i,(initial,events) in enumerate(ledger_hand):add('atomic_ledger',f'atomic-{i:02d}',initial,events)
for trial in range(32):
    initial={k:R.randint(0,20) for k in 'abcd'}; events=[]
    for j in range(30):
        if events and R.random()<.2:
            event=copy.deepcopy(R.choice(events))
            if R.random()<.5:event['moves'].append(['a','b',1])
        else:
            moves=[]
            for _ in range(R.randint(0,4)):
                a,b=R.sample(list('abcd'),2)
                moves.append([a,b,R.randint(1,12)] if R.random()<.85 else [a,'x',0])
            event=ev('e'+str(j),moves)
            if R.random()<.4:event['expected']={R.choice('abcdx'):R.randint(0,20)}
        events.append(event)
    add('atomic_ledger',f'ledger-seed-{trial:02d}',initial,events)

# Priority scheduling DAGs and validation of unrelated invalid components.
def job(key,duration=1,priority=0,deps=None):return {'id':key,'duration':duration,'priority':priority,'deps':deps or []}
sched_hand = [
 ([],2),([job('a')],1),([job('a',3,0),job('b',1,5)],1),
 ([job('a',3,0),job('b',1,5),job('c',1,8,['b'])],2),
 ([job('a',2),job('b',2),job('c',1,99,['a','b']),job('d',3)],2),
 ([job('a'),job('a')],2),([job('a',deps=['missing'])],2),([job('a',deps=['a'])],2),
 ([job('a',deps=['b']),job('b',deps=['a']),job('c')],2),
 ([job('a'),job('b',deps=['a','a'])],2),
 ([job('z',5,-5),job('a',5,-5),job('m',5,-5)],3),
 ([job('a',2),job('b',3),job('c',1,100,['a']),job('d',1,200,['b'])],2),
]
for i,(jobs,w) in enumerate(sched_hand):add('priority_schedule',f'schedule-{i:02d}',jobs,w)
for trial in range(32):
    jobs=[]; ids=['j'+str(i).zfill(2) for i in range(R.randint(3,15))]
    for i,key in enumerate(ids):jobs.append(job(key,R.randint(1,8),R.randint(-3,4),[v for v in ids[:i] if R.random()<.25]))
    R.shuffle(jobs)
    add('priority_schedule',f'dag-{trial:02d}',jobs,R.randint(1,5))

# JSON Patch pointers, roots, arrays, move index semantics, ownership, test equality.
patch_hand = [
 ({},[]),
 ({},[{'op':'add','path':'/a','value':[1,2]}]),
 ({'a':[1,2]},[{'op':'add','path':'/a/1','value':9}]),
 ({'a':[1,2]},[{'op':'add','path':'/a/-','value':9}]),
 ({'a':[1,2]},[{'op':'add','path':'/a/2','value':9}]),
 ({'a':[1,2]},[{'op':'add','path':'/a/3','value':9}]),
 ({'a':[1,2]},[{'op':'replace','path':'/a/2','value':9}]),
 ({'a':[1,2]},[{'op':'remove','path':'/a/01'}]),
 ({'a':[1,2]},[{'op':'test','path':'/a/+1','value':2}]),
 ({'a':[1,2]},[{'op':'test','path':'/a/١','value':2}]),
 ({'a':[1,2]},[{'op':'remove','path':'/a/-'}]),
 ({'a':[1,2]},[{'op':'move','from':'/a/0','path':'/a/1'}]),
 ({'a':[1,2,3]},[{'op':'move','from':'/a/0','path':'/a/3'}]),
 ({'a':[1,2]},[{'op':'copy','from':'/a','path':'/b'},{'op':'replace','path':'/b/0','value':9}]),
 ({'a':{'b':1}},[{'op':'move','from':'/a','path':'/a/c'}]),
 ({'a':1},[{'op':'move','from':'/missing','path':'/missing'}]),
 ({'a':1},[{'op':'move','from':'/a','path':'/a'}]),
 ({'a':1},[{'op':'copy','from':'','path':'/copy'}]),
 ({'a':1},[{'op':'move','from':'','path':''}]),
 ({'a':1},[{'op':'move','from':'','path':'/a'}]),
 ({'a':1},[{'op':'remove','path':''}]),
 ({'a':1},[{'op':'add','path':'','value':[1,2]}]),
 ([1,2],[{'op':'replace','path':'','value':{'x':1}}]),
 ({'':{'a/b':{'~':7}}},[{'op':'test','path':'//a~1b/~0','value':7}]),
 ({'~1':3,'/':4},[{'op':'test','path':'/~01','value':3}]),
 ({'a':1},[{'op':'add','path':'/~2','value':2}]),
 ({'a':1},[{'op':'add','path':'/~','value':2}]),
 ({'a':1},[{'op':'add','path':'a','value':2}]),
 ({'a':1},[{'op':'add','path':'/a/x','value':2}]),
 ({'a':1},[{'op':'replace','path':'/b','value':2}]),
 ({'a':1},[{'op':'remove','path':'/b'}]),
 ({'a':1},[{'op':'add','path':'/b','value':2},{'op':'test','path':'/a','value':2}]),
 ({'a':True},[{'op':'test','path':'/a','value':1}]),
 ({'a':1},[{'op':'test','path':'/a','value':1.0}]),
 ({'a':[True,{'x':2}]},[{'op':'test','path':'/a','value':[1,{'x':2}]}]),
 ({'a':{'b':2,'c':3}},[{'op':'test','path':'/a','value':{'c':3,'b':2}}]),
 ({'a':None},[{'op':'test','path':'/a','value':None},{'op':'remove','path':'/a'}]),
 ({'a':{'x':1},'b':{}},[{'op':'move','from':'/a','path':'/b/a'},{'op':'add','path':'/b/a/x','value':2}]),
 ([],[{'op':'add','path':'/0','value':1},{'op':'remove','path':'/0'}]),
 ({'a':1},[{'op':'copy','from':'/a','path':''}]),
]
for i,(doc,ops) in enumerate(patch_hand):add('json_patch',f'pointer-{i:02d}',doc,ops)
for trial in range(20):
    array=list(range(R.randint(0,8))); ops=[]; working=array[:]
    for j in range(12):
        if not working or R.random()<.45:
            n=R.randint(0,len(working)); value=R.randint(-5,5)
            ops.append({'op':'add','path':'/arr/'+str(n),'value':value});working.insert(n,value)
        elif R.random()<.5:
            n=R.randrange(len(working));ops.append({'op':'remove','path':'/arr/'+str(n)});working.pop(n)
        else:
            n=R.randrange(len(working));value=R.randint(-5,5)
            ops.append({'op':'replace','path':'/arr/'+str(n),'value':value});working[n]=value
    ops.append({'op':'test','path':'/arr','value':working})
    add('json_patch',f'array-edit-{trial:02d}',{'arr':array},ops,expected={'value':{'arr':working}})

# Glob matching: independent recursive segment oracle below uses regex for each segment.
glob_hand = [
 ('',''),('','a'),('*',''),('**',''),('**','a/b'),('a/**/b','a/b'),('a/**/b','a/x/y/b'),
 ('a/*/b','a/b'),('a/*/b','a/x/y/b'),('a/?/b','a/雪/b'),('a/?/b','a/🙂x/b'),
 ('a/**/**/b','a/x/b'),('a/**x/b','a/x/b'),('a/**x/b','a/q/x/b'),
 (r'\*','*'),(r'\?','?'),(r'\\','\\'),(r'a\*b','axxb'),(r'a\*b','a*b'),
 ('[ab]','a'),('[ab]','[ab]'),('A','a'),('a.b','a.b'),('a.b','axb'),
 ('/a','a'),('a/','a'),('a//b','a/b'),('a/\\','z'),('no/\\','other/path'),
 ('***','a'),('***',''),('**/**',''),('**/a/**','a'),('**/a/**','x/a/y'),
 (r'\**','*xyz'),(r'\**','axyz'),('??','🙂雪'),('**/x','x/y'),
]
for i,(pattern,path) in enumerate(glob_hand):add('path_glob',f'glob-{i:02d}',pattern,path)
for trial in range(30):
    pattern='/'.join(R.choice(['a','b','*','?','**','a*','*b',r'\*','[x]']) for _ in range(R.randint(0,5)))
    path='/'.join(R.choice(['a','b','ab','ba','雪','*','[x]']) for _ in range(R.randint(0,5)))
    add('path_glob',f'glob-generated-{trial:02d}',pattern,path)

# Allocator's frozen results are also checked with a cell-grid brute-force oracle.
def alloc(key,size,align=1):return {'op':'alloc','id':key,'size':size,'align':align}
def resize(key,size,align=1):return {'op':'resize','id':key,'size':size,'align':align}
def free(key):return {'op':'free','id':key}
allocator_hand = [
 (0,[]),(0,[alloc('a',1)]),(10,[alloc('a',10),alloc('b',1),free('a'),alloc('b',1)]),
 (12,[alloc('a',3),alloc('b',3,4),alloc('c',2,3)]),
 (10,[alloc('a',3),alloc('b',3),free('a'),resize('b',5)]),
 (10,[alloc('a',3),alloc('b',3),resize('a',5)]),
 (10,[alloc('a',3),alloc('b',3),resize('a',8),free('a'),alloc('c',4)]),
 (10,[alloc('a',3),resize('a',5,4)]),
 (12,[alloc('a',3),alloc('b',5),free('a'),resize('b',2,4)]),
 (10,[alloc('a',2),alloc('a',1),resize('x',2),free('x')]),
 (20,[alloc('a',2),alloc('b',3,7),alloc('c',1,3),free('b'),alloc('d',8,5)]),
 (8,[alloc('a',2),alloc('b',2),alloc('c',2),free('b'),free('a'),free('c')]),
]
for i,(limit,ops) in enumerate(allocator_hand):add('interval_allocator',f'allocator-{i:02d}',limit,ops)
for trial in range(32):
    ops=[]
    for j in range(40):
        kind=R.choice(['alloc','alloc','resize','resize','free']); key=R.choice('abcde')
        ops.append(free(key) if kind=='free' else {'op':kind,'id':key,'size':R.randint(1,12),'align':R.randint(1,9)})
    add('interval_allocator',f'fragmentation-{trial:02d}',R.randint(0,30),ops)

# Framing across every header boundary, Unicode byte counts, poison and finish state.
def frame(body):return len(body).to_bytes(4,'big')+body
frame_payloads = [[],[b''],[b'a'],['雪🙂'.encode()],[b'',b'a',b''],[b'abc',b'xyz'],[b'x'*20],['a\x00b'.encode()],[b'',b'',b''],['مرحبا'.encode(),b'z']]
for i,bodies in enumerate(frame_payloads):
    wire=b''.join(frame(x) for x in bodies)
    for mode,chunks in [('whole',[wire]),('bytewise',[bytes([c]) for c in wire]),('random',split_random(wire,R))]:
        stream('utf8_frames',f'valid-{i:02d}-{mode}',chunks,[max([len(x) for x in bodies]+[0])])
bad_streams = [
 ([b'\x00'],10),([b'\x00\x00'],10),([b'\x00\x00\x00'],10),
 ([(1).to_bytes(4,'big')],10),([(2).to_bytes(4,'big')+b'a'],10),
 ([(11).to_bytes(4,'big')],10),([(1).to_bytes(4,'big')],0),
 ([frame(b'\xff')],10),([frame(b'\xc0\xaf')],10),([frame(b'\xed\xa0\x80')],10),
 ([frame(b'\xf4\x90\x80\x80')],10),([frame(b'\xe2\x82')],10),
 ([frame(b'ok')+frame(b'\xff')],10),
 ([b'\x00\x00',b'\x00\x05'],4),
 ([frame(b''),b'\x00',b'\x00\x00\x00'],0),
]
for i,(chunks,maxsize) in enumerate(bad_streams):
    stream('utf8_frames',f'error-state-{i:02d}',chunks,[maxsize],tail=[{'op':'finish'},{'op':'feed','hex':frame(b'a').hex()},{'op':'finish'}])

# Decimal lines: no binary floats, HALF_UP, largest-remainder allocation and taxable mix.
def item(unit,qty=1,taxable=True):return {'unit':unit,'qty':qty,'taxable':taxable}
invoice_hand = [
 ([], '0.2','10'),([item('0')],'0.2','1'),([item('0.005')],'0','0'),
 ([item('1.005'),item('1.005')],'0.1','0'),
 ([item('0.01') for _ in range(3)],'0','0.01'),
 ([item('0.01') for _ in range(3)],'0','0.02'),
 ([item('0.01'),item('0.02'),item('0.03')],'0','0.02'),
 ([item('0.05'),item('0.05')],'0.1','0'),
 ([item('10',0),item('0.1',3,False),item('0.2',2)],'0.0825','0.11'),
 ([item('3.333333',3),item('0.000001',9999)],'0.099999','2.555'),
 ([item('999999999999.999999',10000),item('0.005')],'1','0.005'),
 ([item('1'),item('2',taxable=False)],'1','999'),
 ([item('1'),item('1')],'0.005','0.005'),
 ([item('0',taxable=False),item('0.01'),item('0')],'0.5','0.01'),
]
for i,(items,rate,coupon) in enumerate(invoice_hand):add('decimal_invoice',f'invoice-{i:02d}',items,rate,coupon)
for trial in range(32):
    items=[item(str(R.randint(0,9999)/10000) if i%3 else str(R.randint(0,100))+'.005',R.randint(0,15),bool(R.randrange(2))) for i in range(R.randint(0,12))]
    rate=R.choice(['0','0.1','0.0825','0.075','0.005','1','0.333333'])
    from decimal import Decimal
    gross_estimate=sum(Decimal(v['unit'])*v['qty'] for v in items)
    coupon=format(gross_estimate*Decimal(R.randint(0,120))/100,'.6f')
    add('decimal_invoice',f'rounding-generated-{trial:02d}',items,rate,coupon)

# Migration closure/validation/rollback order and deterministic forward ordering.
def migration(key,deps=None,reversible=True):return {'id':key,'deps':deps or [],'reversible':reversible}
migration_hand = [
 ([],[],[]),([],['b'],[migration('a'),migration('b',['a'])]),
 (['a','b'],[],[migration('a'),migration('b')]),
 (['a','b','c'],['c'],[migration('a'),migration('b',['a']),migration('c',['a'])]),
 (['a'],[],[migration('a',reversible=False)]),
 (['a'],['a'],[migration('a',reversible=False)]),
 (['b'],[],[migration('a'),migration('b',['a'])]),
 ([],[],[migration('a'),migration('a')]),
 ([],[],[migration('a',['x'])]),
 ([],[],[migration('a',['a'])]),
 ([],[],[migration('a',['b']),migration('b',['a'])]),
 (['x'],[],[migration('a')]),([],['x'],[migration('a')]),
 (['a','a'],['b','b'],[migration('a'),migration('b',['a','a'])]),
 (['a','b'],['c'],[migration('a'),migration('b',['a']),migration('c',['a'])]),
 ([],['z'],[migration('z'),migration('a',['b']),migration('b',['a'])]),
]
for i,(applied,target,registry) in enumerate(migration_hand):add('migration_plan',f'migration-{i:02d}',applied,target,registry)
for trial in range(30):
    ids=['m'+str(i).zfill(2) for i in range(R.randint(2,12))]
    registry=[migration(key,[v for v in ids[:i] if R.random()<.22],R.random()>.15) for i,key in enumerate(ids)]
    lookup={v['id']:v for v in registry}
    def closure(keys):
        result=set(keys)
        while True:
            grown=result|{d for k in result for d in lookup[k]['deps']}
            if grown==result:return sorted(result)
            result=grown
    applied=closure([k for k in ids if R.random()<.45]); target=[k for k in ids if R.random()<.4]
    R.shuffle(registry);R.shuffle(applied);R.shuffle(target)
    add('migration_plan',f'migration-dag-{trial:02d}',applied,target,registry)

# Path ties validated by an independent enumeration of simple paths.
route_hand = [
 ([], 's','s'),([], 's','t'),([['s','t',1]],'s','t'),
 ([['s','a',0],['a','s',0],['a','t',1],['s','t',1]],'s','t'),
 ([['s','a',1],['a','t',1],['s','b',1],['b','t',1]],'s','t'),
 ([['s','a',0],['a','b',0],['b','t',1],['s','z',0],['z','t',1]],'s','t'),
 ([['s','t',5],['s','a',1],['a','b',1],['b','t',1]],'s','t'),
 ([['s','t',3],['s','t',1],['s','t',2]],'s','t'),
 ([['s','ab',0],['ab','c',0],['c','t',1],['s','a',0],['a','bc',0],['bc','t',1]],'s','t'),
 ([['s','雪',0],['雪','t',1],['s','a',0],['a','t',1]],'s','t'),
 ([['s','s',0],['s','t',0],['t','s',0]],'s','t'),
 ([['t','s',0]],'s','t'),
]
for i,(edges,start,goal) in enumerate(route_hand):add('shortest_route',f'route-{i:02d}',edges,start,goal)
for trial in range(36):
    ids=['s','a','b','c','d','t'][:R.randint(3,6)]
    edges=[[a,b,R.randint(0,5)] for a in ids for b in ids if R.random()<.3]
    if edges and trial%3==0:edges.append(copy.deepcopy(R.choice(edges)))
    R.shuffle(edges)
    add('shortest_route',f'route-graph-{trial:02d}',edges,ids[0],ids[-1])

# Atomic cross-record conflict groups and no-fallback behavior.
def record(key,ts,actor,writes):return {'id':key,'ts':ts,'actor':actor,'writes':writes}
record_hand = [
 [],[record('x',1,'a',{'r':1})],
 [record('x',1,'a',{'r':1}),record('x',1,'a',{'r':1})],
 [record('x',1,'a',{'r':1}),record('x',1,'a',{'r':2})],
 [record('x',1,'a',{'r':True}),record('x',1,'a',{'r':1})],
 [record('new',3,'a',{'a':3}),record('mid',2,'a',{'a':2,'b':2}),record('old',1,'a',{'b':1})],
 [record('del',3,'a',{'a':None}),record('mid',2,'a',{'a':2,'b':2}),record('old',1,'a',{'b':1})],
 [record('x',1,'a',{'r':1}),record('y',1,'b',{'r':2})],
 [record('a',1,'a',{'r':1}),record('z',1,'a',{'r':2})],
 [record('x',1,'a',{'r':{'nested':[1,2]}})],
 [record('x',1,'a',{'r':[{'nested':[1,2]}]})],
 [record('x',1,'a',{'r':None,'s':None}),record('y',0,'z',{'s':3})],
]
for i,events in enumerate(record_hand):add('record_conflicts',f'conflict-{i:02d}',events)
for trial in range(32):
    events=[]
    for j in range(R.randint(5,25)):
        keys=R.sample(list('abcdef'),R.randint(1,3))
        values=[None,True,0,1,'x',{'payload':[j,{'n':trial}]}]
        event=record('e'+str(j).zfill(2),R.randint(0,6),R.choice(['a','b','雪']),{k:copy.deepcopy(R.choice(values)) for k in keys})
        events.append(event)
        if R.random()<.15:events.append(copy.deepcopy(event))
    R.shuffle(events)
    add('record_conflicts',f'conflict-batch-{trial:02d}',events)


def oracle_allocator(limit,operations):
    blocks={};out=[]
    def fits(start,size,skip):
        occupied={p for key,(s,n) in blocks.items() if key!=skip for p in range(s,s+n)}
        return start>=0 and start+size<=limit and all(p not in occupied for p in range(start,start+size))
    for op in operations:
        key=op['id'];kind=op['op'];result=None
        if kind=='free':result=key in blocks;blocks.pop(key,None)
        elif (kind=='alloc' and key not in blocks) or (kind=='resize' and key in blocks):
            size,align=op['size'],op['align'];skip=key if kind=='resize' else None
            old=blocks[key][0] if key in blocks else None
            if old is not None and old%align==0 and fits(old,size,skip):result=old
            else:result=next((i for i in range(limit+1) if i%align==0 and fits(i,size,skip)),None)
            if result is not None:blocks[key]=[result,size]
        out.append(result)
    occupied={p for s,n in blocks.values() for p in range(s,s+n)};gaps=[]
    for empty,group in itertools.groupby(range(limit),key=lambda p:p not in occupied):
        values=list(group)
        if empty:gaps.append([values[0],values[-1]+1])
    return {'results':out,'allocations':blocks,'free':gaps}


def oracle_route(edges,start,goal):
    candidates=[]
    def visit(node,path,cost):
        if node==goal:
            candidates.append((cost,len(path)-1,tuple(path)))
            return
        for a,b,w in edges:
            if a==node and b not in path:visit(b,path+[b],cost+w)
    visit(start,[start],0)
    if not candidates:return None
    cost,_,path=min(candidates)
    return {'cost':cost,'path':list(path)}


def oracle_glob(pattern,path):
    if pattern=='':parts=[]
    else:
        parts=pattern.split('/')
        if any(not x for x in parts):raise ValueError('segment')
    compiled=[]
    for part in parts:
        if part=='**':compiled.append(None);continue
        expression='';i=0
        while i<len(part):
            c=part[i]
            if c=='\\':
                i+=1
                if i==len(part):raise ValueError('escape')
                expression+=re.escape(part[i])
            elif c=='*':expression+='.*'
            elif c=='?':expression+='.'
            else:expression+=re.escape(c)
            i+=1
        compiled.append(re.compile(expression,re.S))
    values=path.split('/') if path else []
    def visit(i,j):
        if i==len(compiled):return j==len(values)
        if compiled[i] is None:return any(visit(i+1,n) for n in range(j,len(values)+1))
        return j<len(values) and compiled[i].fullmatch(values[j]) is not None and visit(i+1,j+1)
    return visit(0,0)


def oracle_sse(data):
    text=data.decode('utf-8','replace')
    if text.startswith('\ufeff'):text=text[1:]
    # split() leaves an unterminated tail; only terminator-ended lines are handled.
    lines=re.split(r'\r\n|\r|\n',text)
    if text and not text.endswith(('\r','\n')):lines=lines[:-1]
    else:lines=lines[:-1]
    result=[];fields=[];event='';ident='';retry=None
    for line in lines:
        if not line:
            if fields:result.append({'event':event or 'message','data':'\n'.join(fields),'id':ident,'retry':retry})
            fields=[];event='';continue
        if line.startswith(':'):continue
        name,_,value=line.partition(':')
        if value.startswith(' '):value=value[1:]
        if name=='data':fields.append(value)
        elif name=='event':event=value
        elif name=='id' and '\x00' not in value:ident=value
        elif name=='retry' and re.fullmatch('[0-9]+',value):retry=int(value)
    return result


def main():
    counts={}
    for task,cases in CASES.items():
        namespace=bank._load_source(bank.REFS[task])
        for case in cases:
            expected=bank._observe(namespace,task,case)
            if '_hand_expected' in case:
                assert bank._strict_equal(expected,case.pop('_hand_expected')),(task,case['name'],expected)
            if task in ('interval_allocator','shortest_route','path_glob'):
                oracle={'interval_allocator':oracle_allocator,'shortest_route':oracle_route,'path_glob':oracle_glob}[task]
                try:independent={'value':oracle(*copy.deepcopy(case['args']))}
                except ValueError:independent={'raises':'ValueError'}
                assert bank._strict_equal(expected,independent),(task,case['name'],expected,independent)
            if task=='sse_stream':
                all_bytes=b''.join(bytes.fromhex(x['hex']) for x in case['steps'] if x['op']=='feed')
                flat=[event for step in expected['value'] if 'value' in step for event in step['value']]
                assert flat==oracle_sse(all_bytes),(task,case['name'],flat,oracle_sse(all_bytes))
            case['expected']=expected
        assert 20 <= len(cases) <= 80
        counts[task]=len(cases)
    path=bank.BASE/'fixtures.json'
    path.write_text(json.dumps(CASES,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    results=bank.controls()
    summary={}
    for key,result in results.items():
        positive,negative=result['reference'],result['negative']
        assert positive['passed'] and positive['passed_checks']==positive['total'],(key,positive)
        assert not negative['passed'] and negative['passed_checks']<negative['total'],(key,'negative escaped')
        summary[key]={'checks':positive['total'],'reference_passed':positive['passed_checks'],'negative_passed':negative['passed_checks'],'negative_failed':negative['total']-negative['passed_checks']}
    (bank.BASE/'author_controls.json').write_text(json.dumps(summary,indent=2)+'\n')
    manifest={'design':'12 equal-weight tasks; every task solved iff all its checks pass','seed':2026110501,'case_counts':counts,'total_checks':sum(counts.values()),'hashes':{name:hashlib.sha256((bank.BASE/name).read_bytes()).hexdigest() for name in ['bank.py','freeze.py','fixtures.json','author_controls.json']},'independent_author_oracles':['interval_allocator:cell-grid exhaustive candidate starts','shortest_route:enumeration of simple paths','path_glob:recursive whole-path matching plus regex segments','sse_stream:whole-stream regex line parser and concatenated event comparison'],'acceptance':'Author self-checks only. Separate independent acceptance required.'}
    (bank.BASE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
