# The defect corpus

The scorer for the framework's own improvement loop. Each case is one
defective/clean twin pair: the defective twin carries a real defect shape,
the clean twin is the same file without it. `corpus.py` materializes each
twin into a throwaway directory, runs the named guard the way that guard
is really invoked, and scores CAUGHT / MISSED / FALSE_POSITIVE / INVALID.

The denominator is the manifest set: the report counts cases discovered on
disk (`<caught> of <expected-caught>`), never a loop counter. A count read
off the disk shrinks with the disk, so the total is also declared:
`case_count.json` holds `{"cases": N}`, and a full run exits 1 unless
exactly N case files load. Deleting a case without lowering N fails, naming
the shortfall; adding one without raising N fails too, because a floor left
below new cases would let the next deletion pass unseen (R24-2). There is
no flag that rewrites N: it moves by hand, in the reviewed diff that adds
or deletes the case. CI passes `--require-case-count`, so deleting
`case_count.json` itself is an exit 2, not a way round it.

## Adding a case

One markdown file per case in `cases/`, named `<case-id>.md`. Nothing here
is ever a live `.py` file: the plugin precommit gate lints staged Python,
pytest must never collect a defect file, and `compileall` must never parse
one. Fences open and close on their own lines. Raise `cases` in
`case_count.json` by one in the same diff.

Frontmatter (flat scalars, the house parser):

```markdown
---
case: swallow-outage-as-data
guard: swallow_lint
rule: 2.7
scar: R1-3
expected: caught
---

A failed read becomes "this device reported nothing", and the caller
cannot tell the difference from a device that truly reported nothing.

## defective

```python path=app/units.py
def latest_total(store):
    try:
        return store.fetch()
    except Exception:
        return {}
```

## clean

```python path=app/units.py
def latest_total(store):
    return store.fetch()
```
```

- `case` must equal the filename stem; `guard` must be a registry key in
  `corpus.py` (a manifest never names a command); `rule` is a doctrine id
  or `-` for a repo-specific promise that contributes to no rule's
  coverage; `scar` cites `R<n>-<m>` / `B-<n>` ids that resolve, or the
  literal `distribution` plus a `scar_argument:` sentence; `expected` is
  `caught` or `open`; `fixture: two_commit` only for guards needing real
  git history; `options` only from the guard's fixed enum.
- Every fenced block carries `path=` (the file it materializes to).
  Fences outside the twin sections are helpers - data for the adapter,
  reviewed in the same file.
- Author the case from scar prose, never from guard output (4.2/2.5).
  A case written to match what a guard already flags proves nothing.

## Adapter contracts

Each guard reads fixed paths inside the throwaway dir:

| guard | twins | helpers | options |
|---|---|---|---|
| swallow_lint | `.py` anywhere | none | none |
| interpolation_lint | `.py` anywhere | none | `strict` |
| detectors | `.py` anywhere, scored by ALL THREE finders - keep twins clean of the sibling detectors | none | none |
| claim_check | text is all non-`.json` files joined | `witnessed.json` `[{value, unit}]`, required | none |
| envgate | CI file at `.github/workflows/*.yml` | `gates.json` `[{marker, env_var}]`, required | none |
| golden | `data.json` (the computed values) | `golden.json` (frozen baseline), required | `rebaseline`: replays an intentional re-baseline with UPDATE on - the reason comes from a `reason.txt` helper, or from nowhere (refused). Without the option both update variables are scrubbed. |
| budget | any layout; the note's id unquoted, a test file quoting it | none | none |
| obsgate | `metrics.txt` + `floor.json` | none | none |
| rounds | `rounds/` records | `design/` notes iff `designs` | `designs` |
| framework_shape | files under `docs/`; absent baseline reads as an empty floor | none | none |
| framework_only | files under `guards/` | none | none |
| dead_route_lint | spec files, scored by both finders | `routes.json` `{"routes": [...]}`, required | none |
| verify_guard | exactly one guard file; registry owns the bug, the fix, git, and the guard command | none | `fixture: two_commit` required |
| ci_step_lint | `workflows/` workflow files | none | none |

## Running it

```bash
python3 python/sutradhar_guards/corpus.py corpus/ --rounds docs/rounds/ \
  --backflow docs/backflow.md
python3 python/sutradhar_guards/corpus.py corpus/ --case <id>
python3 python/sutradhar_guards/corpus.py corpus/ --sweep <guard>
python3 python/sutradhar_guards/corpus.py corpus/ --sweep-all
```

`--case` scores one twin pair (MISSED before its guard exists is the
proposer loop's starting gun). `--sweep` runs one guard over every clean
twin in the corpus - that is what catches a guard that flags everything.
It prints how many twins it measured silent, found not applicable (the
guard exited 2 or 3), flagged, and could not run; a sweep that measured
zero twins exits 2, because reading nothing is not a pass.
`--sweep-all` runs that sweep for every guard in the registry and is
what CI runs (R25-4): per-case scoring never shows a guard another
case's clean twin, so a guard flagging one stays invisible until a
sweep is run. It exits 2 if any guard measured nothing, else 1 if any
flagged a clean twin, else 0.

## Coverage

Every doctrine rule is covered (a `caught`-expected case cites it - an
open case names a gap, never coverage), excluded (`EXCLUSIONS.md`,
`- <rule>: <one-line reason>` - drills and human-only rules), or banked in
`uncovered.json` (`{rule: why-not-yet}`). A rule uncovered and unbanked
fails; a banked rule that gained a case fails until removed. Banking is an
act of writing a sentence: there is no update flag.
