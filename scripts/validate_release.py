#!/usr/bin/env python3
"""Offline structural, provenance, privacy, and checksum validation."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"PASS {message}")
    else:
        print(f"FAIL {message}")
        FAILURES.append(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


analysis_bytes = (ROOT / "data/analysis.json").read_bytes()
analysis = json.loads(analysis_bytes)
quantity = load_json(ROOT / "data/quantity.json")
trajectory = load_json(ROOT / "data/tool-trajectory.json")

check(analysis["partial_data"] is False, "analysis is final")
check(analysis["pending_extraction_diagnostics_n"] == 0, "no pending extraction diagnostics")
check(
    analysis["requests"]["unresolved_unreturned_attempts_n"] == 0,
    "no unresolved unreturned request attempts",
)
check(
    quantity["source_analysis_sha256"] == sha256_bytes(analysis_bytes),
    "quantity model points to exact analysis bytes",
)
check(quantity["source_analysis_partial_data"] is False, "quantity model uses final analysis")
check(
    trajectory["source_sha256"]
    == sha256_bytes((ROOT / "benchmark/tool-results.jsonl").read_bytes()),
    "tool trajectory points to exact raw tool result bytes",
)

expected_rows = {
    "core_trials": 72,
    "low_core_trials": 48,
    "baseline_trials": 52,
    "context_trials": 24,
    "tool_trials": 12,
}
for table, expected in expected_rows.items():
    check(len(analysis["tables"][table]) == expected, f"{table} has {expected} rows")

required = [
    "README.md",
    "DATA_DICTIONARY.md",
    "PRIVACY_AND_SECURITY.md",
    "NOTICE.md",
    "report/DeepSeek套餐扩展实测报告.md",
    "report/DeepSeek套餐扩展实测.xlsx",
    "report/final-plot-contact-sheet.png",
    "data/analysis.json",
    "data/quantity.json",
    "data/tool-trajectory.json",
    "artifacts/magpie-v2-evidence.zip",
    "benchmark/requests.jsonl",
    "benchmark/attempt-journal.jsonl",
    "benchmark/tool-results.jsonl",
    "scripts/validate_release.py",
    "SHA256SUMS.json",
]
for relpath in required:
    path = ROOT / relpath
    check(path.is_file() and path.stat().st_size > 0, f"required artifact: {relpath}")

csv_paths = sorted((ROOT / "data/tables").glob("*.csv"))
check(len(csv_paths) == 50, "50 flattened CSV tables")
for path in csv_paths:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        list(csv.DictReader(handle))

report_path = ROOT / "report/DeepSeek套餐扩展实测报告.md"
report = report_path.read_text(encoding="utf-8")
check(sum(line.startswith("# ") for line in report.splitlines()) == 1, "report has one H1")
check("{{" not in report and "}}" not in report, "report has no template placeholders")
for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", report):
    check((report_path.parent / target).is_file(), f"report image exists: {target}")

markdown_paths = [
    ROOT / "README.md",
    ROOT / "DATA_DICTIONARY.md",
    ROOT / "PRIVACY_AND_SECURITY.md",
    ROOT / "validation/README.md",
    ROOT / "data/tables/README.md",
]
for markdown_path in markdown_paths:
    markdown = markdown_path.read_text(encoding="utf-8")
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", markdown):
        if target.startswith(("http://", "https://", "#")):
            continue
        local = target.split("#", 1)[0]
        check(
            (markdown_path.parent / local).exists(),
            f"Markdown link exists in {markdown_path.relative_to(ROOT)}: {target}",
        )

xlsx = ROOT / "report/DeepSeek套餐扩展实测.xlsx"
with ZipFile(xlsx) as archive:
    check(archive.testzip() is None, "XLSX ZIP integrity")
    names = archive.namelist()
    worksheets = [
        name
        for name in names
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
    ]
    charts = [
        name
        for name in names
        if name.startswith("xl/drawings/charts/chart") and name.endswith(".xml")
    ]
    formulas: list[str] = []
    for name in worksheets:
        formulas.extend(
            re.findall(
                r"<x:f[^>]*>(.*?)</x:f>",
                archive.read(name).decode("utf-8", "replace"),
            )
        )
    check(len(worksheets) == 7, "XLSX has seven worksheets")
    check(len(charts) == 2, "XLSX has two native charts")
    check(len(formulas) >= 100, "XLSX formulas are retained")
    all_xml = b"\n".join(archive.read(name) for name in names if name.endswith(".xml"))
    errors = [
        b"#REF!",
        b"#DIV/0!",
        b"#VALUE!",
        b"#NAME?",
        b"#N/A",
        b"#NUM!",
        b"#NULL!",
        b"#SPILL!",
        b"#CALC!",
    ]
    check(not any(token in all_xml for token in errors), "XLSX has no formula error literals")

evidence = ROOT / "artifacts/magpie-v2-evidence.zip"
with ZipFile(evidence) as archive:
    check(archive.testzip() is None, "evidence ZIP integrity")
    manifest = json.loads(archive.read("MANIFEST.sha256.json"))
    check(len(archive.namelist()) == 118, "evidence ZIP has 118 members")
    check(len(manifest) == 117, "evidence manifest has 117 entries")
    check(
        all(
            sha256_bytes(archive.read(member)) == expected
            for member, expected in manifest.items()
        ),
        "every evidence member hash matches",
    )

forbidden_paths = {
    ".env",
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    "auth.json",
}
text_suffixes = {
    "",
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".mjs",
    ".py",
    ".txt",
    ".yml",
    ".yaml",
}
private_markers = [
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"github_pat_",
    b"ghp_",
    b"gho_",
    b"sk-proj-",
]
zip_member_data = []
for path in ROOT.rglob("*"):
    if not path.is_file() or ".git" in path.parts:
        continue
    rel = path.relative_to(ROOT)
    check(path.name not in forbidden_paths, f"no sensitive filename: {rel}")
    if rel == Path("scripts/validate_release.py"):
        continue
    if path.suffix.lower() not in text_suffixes or path.name == "SHA256SUMS.json":
        continue
    data = path.read_bytes()
    check(b"/home/lkf" not in data and b"/Users/" not in data, f"no local home path: {rel}")
    check(not any(marker in data for marker in private_markers), f"no private-key/token marker: {rel}")

with ZipFile(evidence) as archive:
    zip_member_data = [archive.read(member) for member in archive.namelist()]
check(
    not any(
        marker in data
        for data in zip_member_data
        for marker in (b"/home/lkf", b"/Users/", *private_markers)
    ),
    "evidence ZIP contains no local home path or private-key/token marker",
)
with ZipFile(xlsx) as archive:
    workbook_text = b"\n".join(
        archive.read(member) for member in archive.namelist() if member.endswith(".xml")
    )
check(
    not any(
        marker in workbook_text
        for marker in (b"/home/lkf", b"/Users/", *private_markers)
    ),
    "XLSX contains no local home path or private-key/token marker",
)

project_hashes = load_json(ROOT / "SHA256SUMS.json")
root_manifest = ROOT / "SHA256SUMS.json"
actual_files = {
    str(path.relative_to(ROOT))
    for path in ROOT.rglob("*")
    if path.is_file()
    and ".git" not in path.parts
    and path.resolve() != root_manifest
}
check(set(project_hashes) == actual_files, "SHA256SUMS covers every repository file exactly once")
check(
    all(
        (ROOT / relpath).is_file()
        and sha256_bytes((ROOT / relpath).read_bytes()) == expected
        for relpath, expected in project_hashes.items()
    ),
    "all project SHA256 values match",
)

if FAILURES:
    print(f"\n{len(FAILURES)} validation failure(s)")
    raise SystemExit(1)
print("\nAll release checks passed.")

