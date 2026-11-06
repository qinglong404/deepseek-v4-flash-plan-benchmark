#!/usr/bin/env python3
"""Regenerate the project-level SHA256SUMS.json after intentional edits."""

from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SHA256SUMS.json"
hashes = {}
for path in sorted(ROOT.rglob("*")):
    if not path.is_file() or ".git" in path.parts or path == MANIFEST:
        continue
    rel = str(path.relative_to(ROOT))
    hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
MANIFEST.write_text(
    json.dumps(hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"wrote {MANIFEST} with {len(hashes)} entries")

