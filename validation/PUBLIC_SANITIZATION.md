# Public-release sanitization log

The benchmark facts, prompts, model outputs, grades, token counts, timings, statistical methods, and reported results were not changed for public release.

The following code and path-only changes were made:

1. `benchmark/client.py` now loads gateway settings from `MAGPIE_CONFIG`, or from `MAGPIE_BASE_URL` plus `MAGPIE_API_KEY`, instead of a machine-specific configuration path.
2. `benchmark/background_load.py` uses `MAGPIE_USAGE_LOG` and a generic home-relative default rather than a hard-coded home directory.
3. `benchmark/package_evidence.py` performs optional credential matching only when `MAGPIE_CONFIG` is explicitly supplied and writes its archive to this repository's `artifacts/` directory.
4. The `source_path` in `tool-trajectory.json` changed from an absolute path to the relative filename `tool-results.jsonl`; its source hash remains the SHA-256 of the same raw `tool-results.jsonl`.
5. The repository-level README, data dictionary, privacy/security notes, validation script, and GitHub Actions workflow were added.

The original flat-release checksums remain in `pre-layout-SHA256SUMS.json`. The public project has a separate root `SHA256SUMS.json` because moving files changes path keys, and the sanitized evidence archive has its own internal member manifest.

