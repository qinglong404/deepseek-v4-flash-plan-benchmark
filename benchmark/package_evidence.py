"""Allowlisted evidence archive; runtime credentials are only used for a leak check."""
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'artifacts'


def main():
    analysis_bytes=(ROOT/'analysis.json').read_bytes()
    analysis=json.loads(analysis_bytes)
    if analysis['partial_data']:raise SystemExit('Only completed evaluable cohorts may be packaged as final.')
    names={
        'PLAN.md','FORMAT_DIAGNOSTIC_ADDENDUM.md','LOW_EFFORT_ADDENDUM.md','COLLECTOR_RECOVERY_ADDENDUM.md',
        'ANALYSIS_README.md','QUANTITY_README.md','client.py','worker.py','grading.py',
        'run_baseline.py','run_core.py','run_core.before-recovery.py','run_context.py','run_tools.py','run_low.py',
        'analysis.py','quantity.py','trajectory.py','tool-trajectory.json','plots.py','extract_diagnostics.py','background_load.py',
        'deliver.py','workbook.mjs','package_evidence.py','decision.md',
        'requests.jsonl','attempt-journal.jsonl','core-results.jsonl','core-first-grades.jsonl',
        'low-core-results.jsonl','low-core-first-grades.jsonl','core-extracted-grades.jsonl',
        'baseline-results.jsonl','batch-times.jsonl','context-results.jsonl','tool-results.jsonl',
        'core-tasks.json','repository-tasks.json','tool-schemas.json','baseline-plan.json',
        'collector-interruptions.json','official-price-check.json','gateway-observation.json','background-load.json','historical-hour-profile.json',
        'external-load-observation.json',
        'analysis.json','quantity.json','analysis-summary.txt','workbook-formula-checks.json',
        'workbook-errors.txt','workbook-inspect.txt','durable-status.jsonl','phase-status.jsonl',
    }
    files=[ROOT/n for n in names if (ROOT/n).is_file()]
    files += list(ROOT.glob('freeze-*.json'))+list(ROOT.glob('*-order.json'))
    for directory in ['contracts','scenarios','contexts']:
        files += [p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.md') and '__pycache__' not in p.parts]
    files += [p for p in (ROOT/'audit').iterdir() if p.is_file() and p.suffix in ('.py','.json','.md')]
    files += [p for p in (ROOT/'audit/contracts_snapshot').glob('*') if p.is_file() and p.suffix in ('.py','.json')]
    files=sorted(set(files))
    payload={str(p.relative_to(ROOT)):p.read_bytes() for p in files}
    payload['analysis.json']=analysis_bytes
    if json.loads(payload['quantity.json'])['source_analysis_sha256']!=hashlib.sha256(analysis_bytes).hexdigest():raise SystemExit('Quantity source mismatch')
    environment={'collector_python':platform.python_version(),'httpx':importlib.metadata.version('httpx'),
                 'validator_python':subprocess.check_output(['/usr/bin/python3','--version'],text=True).strip(),
                 'bubblewrap':subprocess.check_output(['bwrap','--version'],text=True).strip(),
                 'plot_dependencies':'matplotlib3.11.2; numpy in isolated plot-env',
                 'workbook_dependencies':'@oai/artifact-tool via bundled primary Node runtime',
                 'source_analysis_sha256':hashlib.sha256(analysis_bytes).hexdigest()}
    payload['environment.json']=json.dumps(environment,ensure_ascii=False,indent=2).encode()
    readme='''# Reproducible comparison evidence

This archive contains only the v2 experiment. Original model final answers, tool
actions and all client records are retained. Reasoning prose was never recorded;
only reasoning counts were retained. No home/configuration/auth files are bundled.

Data areas:
- requests.jsonl / attempt-journal.jsonl: every saved terminal/start, not merely successes.
- core/low-core result files: selected first+repair workflows, including failures.
- collector-interruptions.json: exactly identified administrative exclusions and unknowns.
- contracts/scenarios/contexts: frozen synthetic contracts, references, negative controls,
  expected answers and final prompts; no real project source.
- audit/: independent local validation and synthetic audit results. Audit synthetic
  results are NOT real model performance observations.

Offline analysis (Python3 with stdlib):
  python3 analysis.py
  python3 quantity.py

This reproduces statistics without model calls. Extracted-source regrading requires
Linux bubblewrap and /usr/bin/python3 Python3.12; inspect grading.py and worker.py.
Analysis defaults to10,000 seeded cluster-bootstrap draws. plots.py requires
matplotlib and a CJK font; workbook.mjs uses the installed @oai/artifact-tool runtime.

The scripts run_core.py/run_low.py/run_context.py/run_tools.py/run_baseline.py DO
make live paid/subscription calls if explicitly executed, using existing local
Magpie configuration. They are evidence, not a request to rerun or consume quota.
No script modifies subscription/payment settings. Only final artifacts are linked
in the report. List-equivalent cost estimates are not exact billing or residual quota.

The primary evaluable cohorts were completed after one documented entire-pair
replacement. Two original missing client finals remain unknown, not free or
provider failures. Original returned restriction failure is preserved separately.
'''
    payload['README.md']=readme.encode()
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}
    payload['MANIFEST.sha256.json']=json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True).encode()
    # Compare an optional configured Magpie key entirely in memory. Public
    # reconstruction does not require or read any local configuration by default.
    config_path=os.environ.get('MAGPIE_CONFIG')
    key_scan_performed=bool(config_path and Path(config_path).expanduser().exists())
    key_is_local_placeholder=None
    key=b''
    if key_scan_performed:
        key_text=str(json.loads(Path(config_path).expanduser().read_text())['provider']['magpie']['options']['apiKey'])
        key_is_local_placeholder=key_text.strip().casefold()=='magpie'
        key=b'' if key_is_local_placeholder else key_text.encode()
    leaks=[name for name,data in payload.items() if key and key in data]
    if leaks:raise SystemExit('Credential literal leak detected in '+repr(leaks))
    # Stored schema must never contain actual reasoning prose fields.
    bad_reason=[]
    def check(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('reasoning_content','reasoning') and isinstance(v,str) and v.strip():bad_reason.append(k)
                check(v)
        elif isinstance(value,list):
            for v in value:check(v)
    for name in ['requests.jsonl','core-results.jsonl','low-core-results.jsonl','tool-results.jsonl']:
        for line in payload.get(name,b'').decode().splitlines():
            if line.strip():check(json.loads(line))
    if bad_reason:raise SystemExit('Unexpected stored reasoning prose in raw records.')
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/'magpie-v2-evidence.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,data in sorted(payload.items()):z.writestr(name,data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise RuntimeError('Archive integrity failure')
        for name,expected in manifest.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=expected:raise RuntimeError('Archive member hash mismatch')
    scan={'files_in_archive':len(payload),'manifest_entries':len(manifest),'credential_scan_performed':key_scan_performed,'exact_magpie_secret_matches':0 if key_scan_performed else None,'magpie_local_placeholder_excluded':key_is_local_placeholder,'stored_reasoning_prose_fields':0,
          'all_archive_members_hash_verified':True,'archive_bytes':archive.stat().st_size,
          'source_analysis_sha256':environment['source_analysis_sha256'],
          'scope':'Only allowlisted evidence. Credential matching is opt-in through MAGPIE_CONFIG and performed in memory; no configuration/auth files are included.'}
    (OUT/'delivery-checks.json').write_text(json.dumps(scan,ensure_ascii=False,indent=2))
    hashes={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json'}
    (OUT/'SHA256SUMS.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2))
    print(json.dumps(scan))


if __name__=='__main__':main()
