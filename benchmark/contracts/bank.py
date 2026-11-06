"""Frozen, deterministic engineering contracts for Magpie provider comparison.

The import gate is defense in depth, not an OS security boundary. Execute grade()
in the caller's credential-free, resource-limited child process. fixtures.json
contains expected outcomes created before live trials; grading never recomputes
those outcomes from a reference implementation.
"""
import ast
import builtins
import copy
import hashlib
import importlib
import json
import pathlib
import random
import sys
import types

BASE = pathlib.Path(__file__).resolve().parent
SAFE_IMPORTS = frozenset('collections heapq re json codecs typing datetime math bisect functools decimal itertools copy dataclasses enum fractions unicodedata'.split())
COMMON = '''Return ONLY Python source, with no Markdown fences. Use only the standard library; allowed imports: collections, heapq, re, json, codecs, typing, datetime, math, bisect, functools, decimal, itertools, copy, dataclasses, enum, fractions, unicodedata. Do not read files, processes, network, environment, or stdin. Implement the named API exactly. Do not mutate caller-owned input data. All listed ordering rules use Python's ordinary case-sensitive string ordering. Hidden tests exercise boundaries, adversarial inputs and deterministic generated cases.''' 

PROMPTS = {}
REFS = {}
NEGATIVES = {}

PROMPTS['sse_stream'] = '''Implement class SSEParser with feed(chunk: bytes) -> list[dict] and finish() -> list[dict]. It incrementally parses an SSE byte stream. Each returned event has exactly {"event": str, "data": str, "id": str, "retry": int|None}. Decode UTF-8 incrementally with replacement for malformed input. Ignore exactly one initial U+FEFF BOM; subsequent BOMs are ordinary text. Lines terminate at LF, CR, or CRLF, including terminators split between chunks. A CR ends a line immediately; a following LF is swallowed. A blank line dispatches only if at least one data field was seen, joining data field values with LF and defaulting event to "message" when the event field is empty. After every blank line, reset data/event buffers; id and retry persist globally. Lines starting ':' are comments. Split other lines at their first colon, or use an empty value when there is no colon; strip exactly one leading ASCII space from the value. Recognized fields: data, event, id, retry; ignore others. An id containing U+0000 is ignored, otherwise it replaces the persistent id, even on a block with no data. retry replaces persistent retry only for a nonempty sequence of ASCII digits 0..9; interpret as base 10. id starts as "", retry as None. Empty data fields count as data. finish flushes the decoder and processes an unterminated final nonempty line, but never synthesizes a blank line: an undispatched block is dropped. Events produced by the final decoder flush are returned by finish. A second finish returns []; feed after finish raises ValueError. Calls may contain empty byte chunks. Events must be emitted as soon as their terminating blank line is available, not held until finish.'''
REFS['sse_stream'] = r'''
import codecs
class SSEParser:
    def __init__(self):
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.first = True
        self.swallow_lf = False
        self.line = ''
        self.data = []
        self.event = ''
        self.last_id = ''
        self.retry = None
        self.done = False
    def _line(self, line, out):
        if line == '':
            if self.data:
                out.append({'event': self.event or 'message', 'data': '\n'.join(self.data), 'id': self.last_id, 'retry': self.retry})
            self.data = []
            self.event = ''
            return
        if line.startswith(':'):
            return
        key, sep, value = line.partition(':')
        if value.startswith(' '):
            value = value[1:]
        if key == 'data':
            self.data.append(value)
        elif key == 'event':
            self.event = value
        elif key == 'id' and '\x00' not in value:
            self.last_id = value
        elif key == 'retry' and value and all('0' <= c <= '9' for c in value):
            self.retry = int(value)
    def _text(self, text):
        out = []
        for c in text:
            if self.first:
                self.first = False
                if c == '\ufeff':
                    continue
            if self.swallow_lf:
                self.swallow_lf = False
                if c == '\n':
                    continue
            if c in '\r\n':
                self._line(self.line, out)
                self.line = ''
                self.swallow_lf = c == '\r'
            else:
                self.line += c
        return out
    def feed(self, chunk):
        if self.done:
            raise ValueError('finished')
        return self._text(self.decoder.decode(chunk, final=False))
    def finish(self):
        if self.done:
            return []
        self.done = True
        out = self._text(self.decoder.decode(b'', final=True))
        if self.line:
            self._line(self.line, out)
            self.line = ''
        self.data = []
        return out
'''
NEGATIVES['sse_stream'] = REFS['sse_stream'].replace("self.swallow_lf = c == '\\r'", "self.swallow_lf = False")

PROMPTS['ttl_lru'] = '''Implement run_cache(capacity: int, operations: list[dict]) -> list. capacity starts nonnegative. Every operation has integer t, and times are nondecreasing; before EACH operation, purge entries with expires_at <= t. Keys are strings and stored values are integers. Entries are ordered least to most recently used. Operations: {op:"put",t,key,value,ttl}, {op:"get",t,key}, {op:"delete",t,key}, {op:"items",t}, {op:"resize",t,capacity}. put computes expires_at=t+ttl. With ttl<=0 or current capacity 0, remove that key if present and return None. Otherwise overwrite/insert, mark most recently used, evict LRU entries until size<=capacity, return None. get returns the value (including 0) and marks MRU, or returns None when absent. delete returns whether a live entry existed. items returns [[key,value],...] in LRU-to-MRU order and does not touch recency. resize replaces capacity with its nonnegative integer argument, evicts LRU entries if needed, and returns None. Expiration occurs even for items/resize/delete and does not reorder survivors. Return one result per operation. ttl is integer and may be zero or negative; inputs otherwise satisfy the contract.'''
REFS['ttl_lru'] = r'''
from collections import OrderedDict
def run_cache(capacity, operations):
    entries = OrderedDict()
    out = []
    for op in operations:
        now = op['t']
        for key in list(entries):
            if entries[key][1] <= now:
                del entries[key]
        kind = op['op']
        result = None
        if kind == 'put':
            key = op['key']
            entries.pop(key, None)
            if op['ttl'] > 0 and capacity > 0:
                entries[key] = (op['value'], now + op['ttl'])
        elif kind == 'get':
            key = op['key']
            if key in entries:
                result = entries[key][0]
                entries.move_to_end(key)
        elif kind == 'delete':
            key = op['key']
            result = key in entries
            entries.pop(key, None)
        elif kind == 'items':
            result = [[k, v[0]] for k, v in entries.items()]
        elif kind == 'resize':
            capacity = op['capacity']
        while len(entries) > capacity:
            entries.popitem(last=False)
        out.append(result)
    return out
'''
NEGATIVES['ttl_lru'] = REFS['ttl_lru'].replace("entries[key][1] <= now", "entries[key][1] < now")

PROMPTS['atomic_ledger'] = '''Implement replay_ledger(initial: dict[str,int], events: list[dict]) -> {"balances":dict,"results":list[dict]}. Initial balances are nonnegative integers. Process events in input order, each having string id, moves:[[from,to,amount],...], and optional expected:{account:balance}. A first-seen id is permanently remembered along with its entire event, even if rejected; an exact later repeat returns status "duplicate" and makes no change. A repeated id whose event differs returns "conflict" and makes no change. Results contain exactly {"id":id,"status":status}. For a new id, first validate every move: source and destination must exist, differ, and amount must be a positive int (bool is invalid); validate each expected key exists and each expected value is int but not bool. Invalid events have status "invalid" regardless of other failures. Missing expected means empty; moves may be empty. If valid, compare all expected values to balances BEFORE any move; mismatch gives "guard". Otherwise execute moves sequentially in a private tentative balance map: each source must have enough balance at that moment; a failure gives "insufficient" and rolls back ALL moves in the event. All moves succeeding gives "applied", including an empty event. Return final balances and one result per input event. Inputs have the stated structural shapes; amounts/expected values may have invalid scalar values and account names may be unknown. Duplicate equality ignores dict key order; moves list order matters; booleans are distinct from numbers, while int/float numeric equality is allowed.'''
REFS['atomic_ledger'] = r'''
def replay_ledger(initial, events):
    def equal(a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
        return a == b
    balances = dict(initial)
    seen = {}
    results = []
    for event in events:
        key = event['id']
        if key in seen:
            status = 'duplicate' if equal(seen[key], event) else 'conflict'
        else:
            seen[key] = event
            moves = event['moves']
            expected = event.get('expected', {})
            valid = all(a in balances and b in balances and a != b and type(n) is int and n > 0 for a, b, n in moves)
            valid = valid and all(a in balances and type(n) is int for a, n in expected.items())
            if not valid:
                status = 'invalid'
            elif any(balances[a] != n for a, n in expected.items()):
                status = 'guard'
            else:
                tentative = dict(balances)
                status = 'applied'
                for a, b, n in moves:
                    if tentative[a] < n:
                        status = 'insufficient'
                        break
                    tentative[a] -= n
                    tentative[b] += n
                if status == 'applied':
                    balances = tentative
        results.append({'id': key, 'status': status})
    return {'balances': balances, 'results': results}
'''
NEGATIVES['atomic_ledger'] = REFS['atomic_ledger'].replace("tentative = dict(balances)", "tentative = balances")

PROMPTS['priority_schedule'] = '''Implement schedule_jobs(jobs: list[dict], workers: int) -> list[dict]. Each job has unique string id, positive integer duration, integer priority, and deps:list[str]; repeated dependencies count only once. workers is positive. Detect any duplicate id, unknown dependency, self-dependency or cycle ANYWHERE and raise ValueError before scheduling. Empty jobs returns []. All jobs are available from t=0 but can start only after every dependency completes. Use nonpreemptive workers numbered 0..workers-1. At each time when workers become available, mark ALL jobs ending at that time completed, then repeatedly assign a ready unstarted job to the lowest-numbered free worker. Choose highest priority ready job, breaking ties by smallest id. Assign all possible ready jobs at that same time before advancing to the next completion time. Return scheduling actions in their assignment order, each exactly {"id":str,"start":int,"end":int,"worker":int}. Thus simultaneous starts are listed by assigned worker. A long low-priority job cannot be held back while a worker is idle waiting for a future high-priority job. Do not mutate jobs or deps.'''
REFS['priority_schedule'] = r'''
def schedule_jobs(jobs, workers):
    lookup = {}
    for job in jobs:
        if job['id'] in lookup:
            raise ValueError('duplicate')
        lookup[job['id']] = job
    deps = {k: set(v['deps']) for k, v in lookup.items()}
    if any(d not in lookup for ds in deps.values() for d in ds):
        raise ValueError('missing')
    pending = set(lookup)
    checked = set()
    while pending:
        ready = {k for k in pending if deps[k] <= checked}
        if not ready:
            raise ValueError('cycle')
        pending -= ready
        checked |= ready
    pending = set(lookup)
    done = set()
    running = {}
    out = []
    now = 0
    while pending or running:
        for worker in list(running):
            end, key = running[worker]
            if end == now:
                done.add(key)
                del running[worker]
        ready = sorted((k for k in pending if deps[k] <= done), key=lambda k: (-lookup[k]['priority'], k))
        for worker in range(workers):
            if worker not in running and ready:
                key = ready.pop(0)
                pending.remove(key)
                end = now + lookup[key]['duration']
                running[worker] = (end, key)
                out.append({'id':key,'start':now,'end':end,'worker':worker})
        if running:
            now = min(x[0] for x in running.values())
    return out
'''
NEGATIVES['priority_schedule'] = REFS['priority_schedule'].replace("(-lookup[k]['priority'], k)", "(lookup[k]['priority'], k)")

PROMPTS['json_patch'] = '''Implement apply_patch(document, operations:list[dict]) -> new_document for JSON values. Apply all operations atomically to a deep copy; original document and operations must remain unchanged on success and failure. Any invalid operation, pointer, missing target, out-of-range index, or failed test raises ValueError. Implement add/remove/replace/move/copy/test with standard keys op,path,value,from. All required keys exist and op is one of those six. JSON Pointer: "" denotes root; otherwise starts with '/', split by '/', decode only ~0=>~ and ~1=>/ in one pass; every other ~ escape is invalid. Dict keys, including empty strings, are literal after decoding. In arrays an index is exactly '0' or a nonzero ASCII digit followed by ASCII digits, with no signs/leading zeros. '-' is allowed only as the FINAL array token of an add destination (including copy/move destinations), meaning append. add to an object creates/replaces a key; add into an array inserts at 0<=index<=len. replace/remove/test targets must exist; array indices require <len. add/replace at root replace the whole document. remove at root is deliberately forbidden. copy reads the source then deep-copies to add destination. move validates source exists, forbids moving to a proper decoded-token descendant, removes source then evaluates add destination on the modified document; equal decoded source/destination is a successful no-op after validating source. A move from root to itself succeeds; root to any proper descendant fails. test uses JSON equality: dict key order irrelevant; arrays ordered; booleans are distinct from numbers; int/float numeric equality is allowed. Strings/null use their own types. Nested equality follows these rules. Scalar traversal fails. The document consists only of JSON types and finite numbers; pointer strings are Unicode.'''
REFS['json_patch'] = r'''
import copy
import re
def apply_patch(document, operations):
    root = copy.deepcopy(document)
    def tokens(pointer):
        if pointer == '':
            return []
        if not pointer.startswith('/'):
            raise ValueError('pointer')
        parts = []
        for item in pointer[1:].split('/'):
            if re.search(r'~(?![01])', item):
                raise ValueError('escape')
            parts.append(item.replace('~1', '/').replace('~0', '~'))
        return parts
    def index(token, length, adding=False):
        if adding and token == '-':
            return length
        if not re.fullmatch(r'0|[1-9][0-9]*', token):
            raise ValueError('index')
        n = int(token)
        if n > length if adding else n >= length:
            raise ValueError('bounds')
        return n
    def read(parts):
        current = root
        for token in parts:
            if isinstance(current, dict):
                if token not in current:
                    raise ValueError('missing')
                current = current[token]
            elif isinstance(current, list):
                current = current[index(token, len(current))]
            else:
                raise ValueError('scalar')
        return current
    def change(parts, value=None, kind='add'):
        nonlocal root
        if not parts:
            if kind == 'remove':
                raise ValueError('root remove')
            root = copy.deepcopy(value)
            return
        parent = read(parts[:-1])
        token = parts[-1]
        if isinstance(parent, dict):
            if kind != 'add' and token not in parent:
                raise ValueError('missing')
            if kind == 'remove':
                del parent[token]
            else:
                parent[token] = copy.deepcopy(value)
        elif isinstance(parent, list):
            n = index(token, len(parent), kind == 'add')
            if kind == 'add':
                parent.insert(n, copy.deepcopy(value))
            elif kind == 'remove':
                parent.pop(n)
            else:
                parent[n] = copy.deepcopy(value)
        else:
            raise ValueError('scalar')
    def equal(a, b):
        if isinstance(a, bool) or isinstance(b, bool):
            return type(a) is type(b) and a == b
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return a == b
        if type(a) is not type(b):
            return False
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
        if isinstance(a, list):
            return len(a) == len(b) and all(equal(x,y) for x,y in zip(a,b))
        return a == b
    for operation in operations:
        kind = operation['op']
        target = tokens(operation['path'])
        if kind == 'test':
            if not equal(read(target), operation['value']):
                raise ValueError('test')
        elif kind in ('copy', 'move'):
            source = tokens(operation['from'])
            value = copy.deepcopy(read(source))
            if kind == 'move':
                if target == source:
                    continue
                if len(target) > len(source) and target[:len(source)] == source:
                    raise ValueError('descendant')
                change(source, kind='remove')
            change(target, value)
        elif kind == 'remove':
            change(target, kind='remove')
        elif kind == 'replace':
            read(target)
            change(target, operation['value'], 'replace')
        else:
            change(target, operation['value'])
    return root
'''
NEGATIVES['json_patch'] = REFS['json_patch'].replace("root = copy.deepcopy(document)", "root = document")

PROMPTS['path_glob'] = '''Implement path_glob(pattern: str, path: str) -> bool. Match the WHOLE logical path, case-sensitive by Unicode code points. Empty path represents zero segments. Nonempty paths have nonempty slash-separated segments, no leading/trailing/doubled '/', and neither '.' nor '..' segments; paths given to you always satisfy this. Pattern may be empty, which matches only empty path; other patterns must also have nonempty slash-separated segments and no leading/trailing/doubled '/', else raise ValueError. Within an ordinary pattern segment, '*' matches zero or more code points, '?' exactly one, and backslash escapes the next code point as a literal. A trailing backslash in any segment is invalid and raises ValueError. A slash is always a segment separator and cannot be escaped; consequently any segment ending in backslash is invalid. All other characters, including [], . and !, are literal. A segment that is exactly the two UNESCAPED characters '**' matches zero or more complete path segments. '**' embedded in a longer segment has the ordinary repeated-star meaning. Multiple '**' segments are allowed. Validate the ENTIRE pattern before returning even if an earlier segment already mismatches. No filesystem access or path normalization. Examples: 'a/**/b' matches 'a/b' and 'a/x/y/b'; '*' does not match empty path; '**' does; escaped '\\*' matches a literal star segment.'''
REFS['path_glob'] = r'''
def path_glob(pattern, path):
    if pattern == '':
        segments = []
    else:
        segments = pattern.split('/')
        if any(not x for x in segments):
            raise ValueError('segment')
    parsed = []
    for segment in segments:
        if segment == '**':
            parsed.append(None)
            continue
        tokens = []
        i = 0
        while i < len(segment):
            char = segment[i]
            if char == '\\':
                i += 1
                if i == len(segment):
                    raise ValueError('escape')
                tokens.append(('literal', segment[i]))
            elif char == '*':
                tokens.append(('star', ''))
            elif char == '?':
                tokens.append(('one', ''))
            else:
                tokens.append(('literal', char))
            i += 1
        parsed.append(tokens)
    parts = path.split('/') if path else []
    def match_segment(tokens, value):
        possible = {0}
        for kind, char in tokens:
            if kind == 'star':
                possible = set(range(min(possible), len(value)+1)) if possible else set()
            elif kind == 'one':
                possible = {i+1 for i in possible if i < len(value)}
            else:
                possible = {i+1 for i in possible if i < len(value) and value[i] == char}
        return len(value) in possible
    possible = {0}
    for segment in parsed:
        if segment is None:
            possible = set(range(min(possible), len(parts)+1)) if possible else set()
        else:
            possible = {i+1 for i in possible if i < len(parts) and match_segment(segment, parts[i])}
    return len(parts) in possible
'''
NEGATIVES['path_glob'] = REFS['path_glob'].replace("set(range(min(possible), len(parts)+1))", "set(range(min(possible)+1, len(parts)+1))")

PROMPTS['interval_allocator'] = '''Implement allocate_intervals(limit: int, operations:list[dict]) -> {"results":list,"allocations":dict,"free":list}. The integer address domain is [0,limit), limit>=0, initially empty. Active allocations have unique string ids and positive sizes. Operations: {op:"alloc",id,size,align}, {op:"resize",id,size,align}, {op:"free",id}. size/align are positive integers; alignment may be ANY positive integer. alloc must find the smallest start>=0 divisible by align whose [start,start+size) is wholly free. Return start, or None when no space or id already exists. resize of an unknown id returns None. For a known id, first keep its current start if it is aligned and the requested interval fits without overlapping any OTHER allocation; shrinking is allowed. Otherwise relocate to the smallest aligned fitting start, treating the old interval as free during the search. On failure leave the old allocation unchanged. Successful resize returns its resulting start. free removes an existing allocation and returns True, else False. Return one result per operation. allocations maps each remaining id to [start,size]. free is the maximal free half-open intervals as [[start,end],...] sorted by start, with no zero-length intervals. Allocations and free intervals must partition [0,limit). No alignment padding is reserved. No mutation of input.'''
REFS['interval_allocator'] = r'''
def allocate_intervals(limit, operations):
    blocks = {}
    results = []
    def gaps(skip=None):
        result = []
        cursor = 0
        for start, size in sorted(v for k,v in blocks.items() if k != skip):
            if cursor < start:
                result.append([cursor, start])
            cursor = start + size
        if cursor < limit:
            result.append([cursor, limit])
        return result
    def fits(start, size, skip):
        return 0 <= start and start+size <= limit and all(k == skip or start+size <= s or s+n <= start for k,(s,n) in blocks.items())
    for operation in operations:
        kind, key = operation['op'], operation['id']
        result = None
        if kind == 'free':
            result = key in blocks
            blocks.pop(key, None)
        elif (kind == 'alloc' and key not in blocks) or (kind == 'resize' and key in blocks):
            size, align = operation['size'], operation['align']
            skip = key if kind == 'resize' else None
            if kind == 'resize' and blocks[key][0] % align == 0 and fits(blocks[key][0], size, key):
                result = blocks[key][0]
            else:
                for left, right in gaps(skip):
                    start = ((left + align - 1) // align) * align
                    if start + size <= right:
                        result = start
                        break
            if result is not None:
                blocks[key] = [result, size]
        results.append(result)
    return {'results':results,'allocations':blocks,'free':gaps()}
'''
NEGATIVES['interval_allocator'] = REFS['interval_allocator'].replace("skip = key if kind == 'resize' else None", "skip = None")

PROMPTS['utf8_frames'] = '''Implement class FrameParser(max_size:int), feed(chunk:bytes)->list[str], finish()->None. max_size>=0. Wire format concatenates frames: unsigned four-byte big-endian body length N, followed by exactly N bytes encoding one UTF-8 string. N counts BYTES, may be zero, must be <=max_size. Return every complete decoded frame immediately in wire order, preserving partial header/body across feed calls. Chunks may be empty and split anywhere. Decode each body strictly; malformed UTF-8 raises ValueError. As soon as four header bytes are available, an oversized length raises ValueError even if body bytes are absent. Any oversized frame, malformed UTF-8, or finish with a partial header/body permanently poisons the parser: all subsequent feed or finish calls raise ValueError. finish succeeds with None only at a frame boundary, seals the parser, and is idempotent after successful finish; feed after successful finish raises ValueError without changing that successful-finish state. If a feed contains completed frames followed by an error, the feed raises ValueError and no output is returned for that call. Do not decode partial bodies early. A zero-length frame emits the empty string and does not prevent later frames from being parsed.'''
REFS['utf8_frames'] = r'''
class FrameParser:
    def __init__(self, max_size):
        self.max_size = max_size
        self.buffer = bytearray()
        self.expected = None
        self.poisoned = False
        self.done = False
    def feed(self, chunk):
        if self.poisoned or self.done:
            raise ValueError('closed')
        self.buffer.extend(chunk)
        out = []
        while True:
            if self.expected is None:
                if len(self.buffer) < 4:
                    return out
                self.expected = int.from_bytes(self.buffer[:4], 'big')
                del self.buffer[:4]
                if self.expected > self.max_size:
                    self.poisoned = True
                    raise ValueError('oversized')
            if len(self.buffer) < self.expected:
                return out
            body = bytes(self.buffer[:self.expected])
            del self.buffer[:self.expected]
            self.expected = None
            try:
                out.append(body.decode('utf-8', 'strict'))
            except UnicodeDecodeError:
                self.poisoned = True
                raise ValueError('utf8')
    def finish(self):
        if self.poisoned:
            raise ValueError('poisoned')
        if self.done:
            return None
        if self.expected is not None or self.buffer:
            self.poisoned = True
            raise ValueError('incomplete')
        self.done = True
        return None
'''
NEGATIVES['utf8_frames'] = REFS['utf8_frames'].replace("body.decode('utf-8', 'strict')", "body.decode('utf-8', 'replace')")

PROMPTS['decimal_invoice'] = '''Implement invoice(items:list[dict], tax_rate:str, coupon:str) -> dict. Each item has unit:str (nonnegative decimal currency), qty:nonnegative int, taxable:bool. Decimal strings are finite nonnegative fixed-point strings (no exponent), at most 12 digits before and 6 after decimal; qty<=10000; 0<=tax_rate<=1. Use exact decimal arithmetic. First compute each line gross=unit*qty, rounded to cents with ROUND_HALF_UP. All following discount arithmetic uses integer cents. subtotal is sum of rounded line gross. Round coupon to cents HALF_UP, then clamp to subtotal. Allocate this fixed total discount proportionally to each line gross: floor(total_discount*gross_i/subtotal), then distribute remaining cents in order of descending fractional remainder, ties by original line index. With zero subtotal allocate zero discounts. Zero-gross lines have no fractional remainder and cannot receive a discount cent. Each line net=gross-discount. Tax is computed separately for EACH taxable line as net_currency*tax_rate rounded to cents HALF_UP; nontaxable lines tax=0. Return {"lines":[{"gross":s,"discount":s,"net":s,"tax":s,"total":s},...],"subtotal":s,"discount":s,"net":s,"tax":s,"total":s}. Every s is a fixed two-decimal nonnegative string. total=net+tax per line and invoice; aggregate tax is sum of line taxes. Preserve zero-quantity lines and input order. Avoid binary floating point. Coupon can exceed subtotal. Example: three one-cent lines with one-cent coupon allocate that cent to the first line.'''
REFS['decimal_invoice'] = r'''
from decimal import Decimal, localcontext, ROUND_HALF_UP
def invoice(items, tax_rate, coupon):
    with localcontext() as context:
        context.prec = 80
        def cents(value):
            return int((value * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        def money(value):
            return str(value // 100) + '.' + str(value % 100).zfill(2)
        gross = [cents(Decimal(item['unit']) * item['qty']) for item in items]
        subtotal = sum(gross)
        discount = min(cents(Decimal(coupon)), subtotal)
        portions = [discount * n // subtotal if subtotal else 0 for n in gross]
        if subtotal:
            order = sorted(range(len(gross)), key=lambda i: (-(discount*gross[i] % subtotal), i))
            for i in order[:discount-sum(portions)]:
                portions[i] += 1
        lines = []
        taxes = []
        for item, g, d in zip(items, gross, portions):
            net = g - d
            tax = cents(Decimal(net) / 100 * Decimal(tax_rate)) if item['taxable'] else 0
            taxes.append(tax)
            lines.append({k: money(v) for k,v in {'gross':g,'discount':d,'net':net,'tax':tax,'total':net+tax}.items()})
        net = subtotal-discount
        tax = sum(taxes)
        return {'lines':lines,'subtotal':money(subtotal),'discount':money(discount),'net':money(net),'tax':money(tax),'total':money(net+tax)}
'''
NEGATIVES['decimal_invoice'] = REFS['decimal_invoice'].replace("ROUND_HALF_UP))", "'ROUND_HALF_EVEN'))")

PROMPTS['migration_plan'] = '''Implement plan_migrations(applied:list[str], target:list[str], migrations:list[dict]) -> list[str]. Registry entries have unique string id, deps:list[str], reversible:bool. Validate the ENTIRE registry first: duplicate id, unknown dependency, self dependency or any cycle raises ValueError, even if irrelevant to target/applied. Repeated deps are harmless. applied/target names must exist; repetitions in those two lists are ignored. applied must be dependency-closed (all transitive dependencies of every applied migration are applied), otherwise ValueError. Desired final set is target plus its transitive dependency closure. Remove applied migrations outside desired, then apply missing desired migrations. Every removal must be reversible; if any required removal is irreversible, raise ValueError. Deterministic rollback: repeatedly choose the lexicographically LARGEST removable migration (one with no currently applied dependent), append '-'+id and remove it. Deterministic forward: repeatedly choose the lexicographically SMALLEST missing desired migration whose deps are currently applied, append '+'+id and apply it. Return the full plan; no side effects. Rollbacks all precede forward steps. Empty registry/applied/target is valid. Existing migrations in desired must never be rolled back merely to change order.'''
REFS['migration_plan'] = r'''
def plan_migrations(applied, target, migrations):
    registry = {}
    for item in migrations:
        if item['id'] in registry:
            raise ValueError('duplicate')
        registry[item['id']] = item
    deps = {k:set(v['deps']) for k,v in registry.items()}
    if any(d not in registry for ds in deps.values() for d in ds):
        raise ValueError('missing dependency')
    waiting, checked = set(registry), set()
    while waiting:
        ready = {k for k in waiting if deps[k] <= checked}
        if not ready:
            raise ValueError('cycle')
        waiting -= ready
        checked |= ready
    current = set(applied)
    desired = set(target)
    if not (current | desired) <= set(registry):
        raise ValueError('unknown')
    if any(not deps[k] <= current for k in current):
        raise ValueError('not closed')
    while True:
        expanded = desired | {d for k in desired for d in deps[k]}
        if expanded == desired:
            break
        desired = expanded
    remove = current - desired
    if any(not registry[k]['reversible'] for k in remove):
        raise ValueError('irreversible')
    result = []
    while remove:
        ready = [k for k in remove if all(k not in deps[other] for other in current)]
        key = max(ready)
        result.append('-'+key)
        current.remove(key)
        remove.remove(key)
    while desired-current:
        key = min(k for k in desired-current if deps[k] <= current)
        result.append('+'+key)
        current.add(key)
    return result
'''
NEGATIVES['migration_plan'] = REFS['migration_plan'].replace("key = max(ready)", "key = min(ready)")

PROMPTS['shortest_route'] = '''Implement shortest_route(edges:list[list], start:str, goal:str) -> dict|None. Each edge is [source:str,destination:str,weight:int] of a directed graph. All weights are nonnegative integers; parallel edges, self loops, zero weights, disconnected components and arbitrary Unicode node names are allowed. Nodes are those in edges plus start/goal. Return None if goal is unreachable. Otherwise return exactly {"cost":int,"path":list[str]}. Choose paths by (1) smallest total edge cost, (2) fewest edges among paths with that cost, (3) lexicographically smallest FULL node sequence among paths tied on cost and edge count. Ordinary tuple/list string comparison determines rule 3, not concatenation of node names. start==goal returns cost 0 and path [start], regardless of cycles. Do not mutate edge list. Hidden tests include cycles and cases where a cheaper route has more hops, and equal-cost routes where fewer hops must beat lexicographic order.'''
REFS['shortest_route'] = r'''
import heapq
def shortest_route(edges, start, goal):
    graph = {}
    for source, dest, weight in edges:
        graph.setdefault(source, []).append((dest, weight))
    initial = (0, 0, (start,))
    best = {start:initial}
    queue = [initial]
    while queue:
        cost, hops, path = heapq.heappop(queue)
        node = path[-1]
        if best[node] != (cost,hops,path):
            continue
        if node == goal:
            return {'cost':cost,'path':list(path)}
        for dest, weight in graph.get(node, []):
            candidate = (cost+weight, hops+1, path+(dest,))
            if dest not in best or candidate < best[dest]:
                best[dest] = candidate
                heapq.heappush(queue,candidate)
    return None
'''
NEGATIVES['shortest_route'] = REFS['shortest_route'].replace("(cost+weight, hops+1, path+(dest,))", "(cost+weight, hops, path+(dest,))")

PROMPTS['record_conflicts'] = '''Implement resolve_records(events:list[dict]) -> {"values":dict,"tombstones":list[str],"accepted":list[str],"rejected":list[str]}. This is an explicitly defined batch conflict resolver for ATOMIC multi-record updates, not ordinary per-key LWW. Each event has unique-intent string id, nonnegative integer ts, string actor, and nonempty writes:dict[str,JSON_value]. A write value None is a tombstone. Duplicate event ids with EXACTLY identical entire event payload are collapsed; dict key order is irrelevant, list order matters, and JSON booleans are distinct from numbers; int/float numeric equality is allowed. The same id with any differing payload invalidates the whole batch and raises ValueError. Resolve deduplicated events in descending tuple order (ts,actor,id). Initially no keys are claimed. Accept an event if NONE of its write keys has already been claimed by an accepted event; then atomically claim ALL its keys and record all its writes. If ANY key is claimed, reject the entire event; its other keys remain unclaimed and can be claimed by later lower-ranked events. There is no partial acceptance, fallback merge, or replay order dependence. Tombstones claim keys just like ordinary writes. values contains final non-null values for claimed keys; tombstones is sorted claimed keys with null values. accepted/rejected contain ids in the actual descending-rank processing order (each id once). Returned nested values must be independent copies of the input; modifying returned values must not modify caller data. Ids are global across actors. Reordering input or dict key order must not change output.'''
REFS['record_conflicts'] = r'''
import copy
def resolve_records(events):
    def equal(a,b):
        if isinstance(a,bool) or isinstance(b,bool):
            return type(a) is type(b) and a == b
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):
            return a == b
        if type(a) is not type(b):
            return False
        if isinstance(a,dict):
            return a.keys() == b.keys() and all(equal(a[k],b[k]) for k in a)
        if isinstance(a,list):
            return len(a) == len(b) and all(equal(x,y) for x,y in zip(a,b))
        return a == b
    unique = {}
    for event in events:
        key = event['id']
        if key in unique and not equal(unique[key],event):
            raise ValueError('conflicting id')
        unique[key] = event
    claimed = {}
    accepted, rejected = [], []
    for event in sorted(unique.values(),key=lambda e:(e['ts'],e['actor'],e['id']),reverse=True):
        if any(k in claimed for k in event['writes']):
            rejected.append(event['id'])
        else:
            accepted.append(event['id'])
            claimed.update(copy.deepcopy(event['writes']))
    return {'values':{k:v for k,v in claimed.items() if v is not None}, 'tombstones':sorted(k for k,v in claimed.items() if v is None), 'accepted':accepted,'rejected':rejected}
'''
NEGATIVES['record_conflicts'] = REFS['record_conflicts'].replace("if any(k in claimed for k in event['writes']):", "if all(k in claimed for k in event['writes']):")

API = {'sse_stream':'SSEParser','ttl_lru':'run_cache','atomic_ledger':'replay_ledger','priority_schedule':'schedule_jobs','json_patch':'apply_patch','path_glob':'path_glob','interval_allocator':'allocate_intervals','utf8_frames':'FrameParser','decimal_invoice':'invoice','migration_plan':'plan_migrations','shortest_route':'shortest_route','record_conflicts':'resolve_records'}


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split('.')[0] not in SAFE_IMPORTS:
        raise ImportError('import not permitted: '+name)
    return builtins.__import__(name, globals, locals, fromlist, level)


def _load_source(source):
    tree = ast.parse(source, '<submission>', 'exec')
    banned = {'open','exec','eval','compile','input','breakpoint','globals','locals','vars','__import__'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import,ast.ImportFrom)):
            names = [x.name for x in node.names] if isinstance(node,ast.Import) else [node.module or '']
            if isinstance(node,ast.ImportFrom) and node.level:
                raise ValueError('relative import not permitted')
            if any(n.split('.')[0] not in SAFE_IMPORTS for n in names):
                raise ValueError('import not permitted')
        if isinstance(node,ast.Name) and node.id in banned:
            raise ValueError('restricted name: '+node.id)
        if isinstance(node,ast.Attribute) and node.attr.startswith('__'):
            raise ValueError('dunder attribute access not permitted')
    names = 'abs all any ascii bin bool bytearray bytes callable chr classmethod complex dict divmod enumerate filter float format frozenset getattr hasattr hash hex int isinstance issubclass iter len list map max memoryview min next object oct ord pow property range repr reversed round set setattr slice sorted staticmethod str sum super tuple type zip Exception ValueError TypeError KeyError IndexError RuntimeError AssertionError StopIteration UnicodeDecodeError OverflowError ZeroDivisionError NotImplementedError'.split()
    permitted = {k:getattr(builtins,k) for k in names}
    permitted['__build_class__'] = builtins.__build_class__
    permitted['__import__'] = _safe_import
    module = types.ModuleType('_benchmark_submission')
    module.__dict__['__builtins__'] = permitted
    previous = sys.modules.get(module.__name__)
    sys.modules[module.__name__] = module
    try:
        exec(compile(tree,'<submission>','exec'),module.__dict__)
    except BaseException:
        if previous is None:
            sys.modules.pop(module.__name__,None)
        else:
            sys.modules[module.__name__] = previous
        raise
    # Keep the module registered for dataclasses/typing during calls in this process.
    return module.__dict__


def _strict_equal(a,b):
    if type(a) is not type(b):
        return False
    if isinstance(a,dict):
        return a.keys() == b.keys() and all(_strict_equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)):
        return len(a) == len(b) and all(_strict_equal(x,y) for x,y in zip(a,b))
    return a == b


def _observe(namespace,task_id,case):
    api = namespace[API[task_id]]
    if task_id in ('sse_stream','utf8_frames'):
        instance = api(*case.get('init',[]))
        observed = []
        for step in case['steps']:
            try:
                value = instance.feed(bytes.fromhex(step['hex'])) if step['op'] == 'feed' else instance.finish()
                observed.append({'value':value})
            except Exception as exc:
                observed.append({'raises':type(exc).__name__})
        return {'value':observed}
    args = copy.deepcopy(case['args'])
    original = copy.deepcopy(args)
    try:
        result = api(*args)
        outcome = {'value':result}
        # These two APIs additionally promise independent output ownership.
        if task_id in ('record_conflicts','json_patch'):
            clean_result = copy.deepcopy(result)
            def mutate(value):
                if isinstance(value,dict):
                    for child in list(value.values()):
                        mutate(child)
                    value['__output_ownership_probe__'] = True
                elif isinstance(value,list):
                    for child in list(value):
                        mutate(child)
                    value.append('__output_ownership_probe__')
            if task_id == 'record_conflicts' and isinstance(result,dict):
                for value in result.get('values',{}).values():
                    mutate(value)
            elif task_id == 'json_patch':
                mutate(result)
            if not _strict_equal(args,original):
                return {'violation':'output aliases input'}
            outcome = {'value':clean_result}
    except Exception as exc:
        outcome = {'raises':type(exc).__name__}
    if not _strict_equal(args,original):
        return {'violation':'input mutated'}
    return outcome


def tasks():
    return [{'id':key,'prompt':COMMON+'\n\n'+value} for key,value in PROMPTS.items()]


def grade(task_id,source):
    fixtures = json.loads((BASE/'fixtures.json').read_text(encoding='utf-8'))
    cases = fixtures[task_id]
    checks = []
    try:
        namespace = _load_source(source)
        if API[task_id] not in namespace:
            raise ValueError('missing API '+API[task_id])
    except Exception as exc:
        error = type(exc).__name__+': '+str(exc)[:400]
        return {'passed':False,'passed_checks':0,'total':len(cases),'checks':[{'name':x['name'],'ok':False,'error':error} for x in cases],'error':error}
    for case in cases:
        try:
            actual = _observe(namespace,task_id,case)
            okay = _strict_equal(actual,case['expected'])
            check = {'name':case['name'],'ok':okay}
            if not okay:
                check['error'] = ('expected '+repr(case['expected'])+'; got '+repr(actual))[:1500]
        except Exception as exc:
            check = {'name':case['name'],'ok':False,'error':type(exc).__name__+': '+str(exc)[:600]}
        checks.append(check)
    return {'passed':all(x['ok'] for x in checks),'passed_checks':sum(x['ok'] for x in checks),'total':len(checks),'checks':checks}


def controls():
    return {key:{'reference':grade(key,REFS[key]),'negative':grade(key,NEGATIVES[key])} for key in PROMPTS}
