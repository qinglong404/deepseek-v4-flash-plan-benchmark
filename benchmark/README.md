# Reproducible comparison evidence

This directory contains the v2 experiment. Original model final answers, tool
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
  python3 analysis.py --draws 10000
  python3 quantity.py --draws 10000
  python3 trajectory.py

This reproduces statistics without model calls. Extracted-source regrading requires
Linux bubblewrap and /usr/bin/python3 Python3.12; inspect grading.py and worker.py.
Analysis uses 10,000 seeded cluster-bootstrap draws. plots.py requires
matplotlib and a CJK font; workbook.mjs uses the installed @oai/artifact-tool runtime.

The scripts run_core.py/run_low.py/run_context.py/run_tools.py/run_baseline.py DO
make live paid/subscription calls if explicitly executed, using existing local
Magpie configuration supplied through MAGPIE_CONFIG or MAGPIE_BASE_URL and
MAGPIE_API_KEY. They are evidence, not a request to rerun or consume quota.
No script modifies subscription/payment settings. Only final artifacts are linked
in the report. List-equivalent cost estimates are not exact billing or residual quota.

The primary evaluable cohorts were completed after one documented entire-pair
replacement. Two original missing client finals remain unknown, not free or
provider failures. Original returned restriction failure is preserved separately.
