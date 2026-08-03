# python/ - the backend guards

Copy-in, stdlib-only, Python 3.9+. Each module is both a CLI and an
importable library, and each carries the incident that earned it in its
docstring.

| Module | What it enforces | Mechanic |
|---|---|---|
| `swallow_lint.py` | No new silent exception swallows | AST detector + per-file count baseline that only shrinks |
| `interpolation_lint.py` | No f-string interpolation into query strings without escaping at the site | AST detector over JoinedStr, keyword presets for SQL/SPARQL/Cypher |
| `ratchet.py` | Your own class invariants, whatever they walk | Shrink-only allowlist library with the guard-the-guard stale check |
| `envgate.py` | Env-gated test tiers actually run somewhere | Marker auto-skip + an audit that fails when no CI file sets the gate |

## Install

There is nothing to install. Copy `sutradhar_guards/` next to your tests
(or the two lint CLIs into `scripts/`), and copy any tests from `tests/`
you want as living documentation.

## The pattern all four share

1. **Detector**: a function that walks source/AST/config and returns
   violations.
2. **Ratchet**: today's violations frozen in a reviewed baseline file; new
   ones fail; fixed ones must be banked out of the baseline (the floor
   only drops).
3. **Selfcheck**: the detector is run against a planted known-bad case in
   CI. A guard that cannot be shown to fail is decoration, and a detector
   silently edited into vacuity is the failure mode nobody tests for.

Run the toolkit's own tests:

```bash
cd python && python3 -m pytest tests/ -q
```
