# Validation records

- `delivery-checks.json` is the original flat-release security scan. Its configured local `apiKey` was the documented placeholder `magpie`; no real account credential was present. The scan found zero real credential literals and zero stored reasoning-prose fields.
- `pre-layout-SHA256SUMS.json` records the pre-GitHub flat output layout. Those hashes remain provenance for the original release but do not directly name files after repository reorganization.
- `workbook-formula-checks.json` records formula recomputation checks.
- `workbook-errors.txt` records the workbook error scan.
- `workbook-inspect.txt` contains a compact inspection sample.

The public repository adds a new root `SHA256SUMS.json` after sanitizing absolute local paths and wrapping environment-dependent live configuration in explicit variables. `artifacts/SHA256SUMS.json` covers the rebuilt evidence archive and its scan record. The archive also carries `MANIFEST.sha256.json` for each member.

Exact public-release path substitutions and unchanged scientific results are documented in [PUBLIC_SANITIZATION.md](PUBLIC_SANITIZATION.md).

