# Round 18 - 2026-09-07

Lenses: backflow from an adopter thread, our own shipped code, CI wiring

**What this round was.** An adopter thread sent back three things it had paid
for, and reading its fixes found a defect in code this repository ships and
documents. That defect is R18-1 and it is the round: **a ratchet baseline
keyed on a line number re-flags the findings it has already banked.** Every
adopter following our own two playbooks inherited it. It was not found by a
test - no test we had could see it, because every one of them built a fixture
and read the keys back without ever editing above them.

The other two items are guards ported from that thread: the quiet half of
honest degradation, which `swallow_lint` structurally cannot see, and a
reachability check on CI wiring. The fourth is not a fix at all. It is a
record that the same thread arrived independently at "an exit code is a claim
about a process, not about a check" - our 6.7, invented separately, and
convergence at that width is the strongest evidence 8.1 accepts.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R18-1 | high | 2.1 | an adopter thread's fix, read directly | fixed | `ratchet.py` documented key mode as "violations are identifiers (file:line, route names, ...)", `detectors.find_unresolved_relative_imports` emitted `file:line: message`, `dead_route_lint.find_unfailable_assertions` emitted `a.cy.ts:1`, and `docs/backend.md` and `docs/frontend.md` both showed adopters wiring exactly those into `assert_only_shrinks`. A line number is not a stable identity: any edit above a banked finding re-flags it as new, and the obvious fix - `--update-baseline` - banks every genuinely new finding at the same time. Fixed: the four shipped detectors return `Violation(key, message)`, keyed on the file plus the normalised matched text with `#2`/`#3` for a repeat in one file, and `Ratchet.migrate_keys` moves an existing baseline across one to one, refusing anything it cannot place. BREAKING for adopters' baselines |
| R18-2 | med | 2.7 | an adopter thread's guard, ported | fixed | `swallow_lint` catches the loud half of honest degradation, an `except` that logs nothing. The quiet half it structurally cannot see is a handler that DOES log and returns the same falsy value some legitimate "there is nothing here" path in the same function returns - the caller cannot tell an outage from an empty result, and every number downstream is computed over an unknown fraction of reality under a green status. Shipped as `conflated_degrade_lint.py`, a ratchet keyed `path::qualified_name`, whose output says in as many words that the fix is not "raise instead" |
| R18-3 | med | 6.7 | an adopter thread's guard, ported | fixed | a CI step ran a guard by a path that did not resolve under that job's working directory. The interpreter exited 2 on file-not-found - a claim about a process, not about the code under test - and took every later step in the job with it, and its red was read for weeks as "the guard is failing" rather than "the guard is absent". Same class as R16-1, the plugin that worked in exactly one layout, and invisible from inside that layout by construction. Shipped as `ci_step_lint.py` and run over this repository's own workflow in CI |
| R18-4 | low | 6.7 | thread survey, convergence | closed | the adopter thread states, in its own guard's prose and without having read this file, that an exit code is a claim about a PROCESS and not about a check, and that a crash is the absence of a verdict rather than a verdict. That is 6.7 and 6.11, invented separately. It founds nothing and changes no text; it is recorded because 8.1 accepts convergence at that width as its strongest evidence, and because two of the four threads that converged on 2.9 got there the same way. Registered as backflow B-22 to B-24 rather than as doctrine |

## R18-1: what a key is for

A baseline entry names a violation, so it has to name it in a way that
survives an edit somewhere else in the file. Ours named a position.

The scar the adopter thread paid, in its own words:

> A baseline keyed on `path:line name` re-flagged banked findings three times
> in one day - a docstring edit above one function, a single added import, and
> a refactor that moved three functions it did not change. Each time the
> tempting fix was `--update-baseline`, which would have banked any real new
> finding along with the noise. The key became `path::qualified_name`.

Three things had to change together, because fixing one without the others
leaves the defect reachable:

1. **`ratchet.py`** states the contract on `assert_only_shrinks` and stops
   offering `file:line` as an example. `Violation(key, message)` carries the
   two halves: the ratchet banks the key and prints the message, so the line
   number reaches the reader and never reaches the baseline.
2. **The four shipped detectors** emit stable keys - the file plus the
   normalised matched text (`a.cy.ts::.to.not.eq(500)`, `src/a.py::from .util
   import helper`), with `#2`, `#3` in source order for a repeat of the same
   text in one file, so adding a second never renames the first. Numbering is
   done in source order rather than `ast.walk` order, which is breadth first
   and would let a nested match take `#2` from one written above it.
3. **Both playbooks**, because R18-1 reached adopters through the docs as
   much as through the code. `docs/backend.md` composed `f"{f}:{hit}"` in its
   worked example. A test now refuses that string in any shipped document.

`migrate_keys` is the path across for an existing baseline, and its refusals
are the feature: every banked entry must be placed, every mapping key must
already be banked, and two entries may not merge onto one key. It cannot bank
something that was not banked, which is the entire difference between it and
`--update-baseline`.

## Two defects found while building the CI guard, both in the guard

Worth recording because neither came from a test that existed first.

**The scanner read only half the file.** It matched a `run:` on its own line
and not the `- run: |` form. On this repository's own workflow that was four
jobs and eight of nineteen script references skipped without a word - a guard
reporting green over what it had not read, which is the class its own subject
belongs to.

**The selfcheck raised instead of reporting.** It indexed
`list(steps(...))[0]` before checking the list was non-empty, so the mutation
that blinded the scanner killed the instrument rather than the guard:
`IndexError`, no verdict, and every later case in the run lost with it. That
is 6.11 exactly, on the first guard written since 6.11 was adopted. The shapes
are validated before they are indexed now.

## What running the new guards over this repository found

| guard | run | result |
|---|---|---|
| `ci_step_lint.py` | `.github/workflows` | **clean** - 1 workflow, 24 script references reachable, 12 absolute paths skipped and said out loud |
| `ci_step_lint.py` | `ci/guards.yml` | 7 findings, and every one is the template working as intended: it names `scripts/*.py`, which resolve in the tree `bootstrap.sh` builds and not in this one. The guard's docstring now says not to point it at a template, and a test pins the check that IS worth having there - that every script the template runs is one bootstrap actually copies |
| `conflated_degrade_lint.py` | `python/sutradhar_guards` | 2 candidates, **both judged intentional and neither fixed**. `mcp_server.handle_line` returns `None` from its handlers only when the request was a notification, which is the same thing its non-exception `return None` means, and the error is logged with its type; `detectors._module_exports` returns `None` for a module that does not parse and for one whose star-import surface is unknowable, and the unparseable case is separately reported by the caller. Recorded rather than baselined: a two-entry baseline holding no defect is an ignore-list with a better name, and this repository does not yet run the guard over itself |

## Mutation verification (2.2)

Every fix was shown able to fail before it was trusted. Each mutant was
applied by editing the file, running the named test file with `cd python &&
PYTHONPATH=. python -m pytest tests/<file> -q`, and restoring from a backup
taken first.

| commit | mutant | result |
|---|---|---|
| 1 | `find_unfailable_assertions` keyed `spec:line` again | **5 red**, incl. `unfailable_assertions banks a position, not an identity: ['a.cy.ts:2', 'a.cy.ts:4']` and the guard's own selfcheck |
| 1 | both import-detector keys returned to `file:line` | **6 red**, and the end-to-end case reproduced the scar itself: `[imports] 2 NEW violation(s) beyond the baseline` after a docstring and one import were added above them |
| 1 | `_numbered` stopped disambiguating a repeat | **1 red**: `2 == 2 and False` where the second key did not end `#2` |
| 1 | `migrate_keys` stopped refusing an unplaceable entry | **1 red** - and note the shape: it went red by raising `KeyError`, which is 6.11's warning, and the guard clause is the shape validation that keeps it a verdict |
| 1 | `migrate_keys` stopped refusing an unbanked mapping key | **1 red**: `DID NOT RAISE RatchetError` |
| 1 | `migrate_keys` stopped refusing a merge | **1 red**: `DID NOT RAISE RatchetError` |
| 2 | `conflates` returned `bool(handler_tags)`, dropping the intersection | **2 red**: the `(value, ok)` fix and the re-raise both flagged |
| 2 | `#n` removed from `functions_with_qualnames` | **2 red**, and the selfcheck printed `qualified keys are wrong: [... '<src>::read', '<src>::read']` |
| 2 | the line put back into the key | **5 red** |
| 2 | the stale-entry half of `compare` deleted | **2 red**, one of them through the CLI |
| 3 | every path resolved from the repo root, ignoring `working-directory` | **10 red** |
| 3 | the `- run:` inline form dropped again | **8 red**, incl. `the '- run:' step was not read at all` |
| 3 | absolute paths checked instead of skipped | **8 red**, and the selfcheck printed `an absolute path an earlier step creates: flagged, expected accepted` |
| 3 | an empty workflow directory allowed to report a pass | **1 red** on the 2.9 case |

## Measured, not estimated

| Number | Before | After |
|---|---|---|
| tests | 465 | **550** |
| guard modules | 14 | **16** |
| script references `ci_step_lint` reads in this repo's workflow | - | **24**, plus 12 absolute skipped |
| script references it read before the `- run:` fix | 11 | 24 |

## The backflow register comes due, and this round did not answer it

Recording round 18 makes four register items overdue: **B-13** and **B-16**
(decided ADOPT in round 17 and re-deferred to 18 because each is a mechanism
to build - the Playwright port and the file-ownership manifest guard) and
**B-20** and **B-21** (owed since round 16). The gate therefore fails:

```
python3 python/sutradhar_guards/rounds.py docs/rounds/ --backflow docs/backflow.md
```

**That is the mechanism working, and it is left failing on purpose.** This
round was a guards round: it did not build the Playwright port, the ownership
manifest, or the `%`-format detector, and moving four deadlines to make a gate
go green would be exactly the behaviour R15-4 was filed to stop and round 16
refused twice. A red gate naming four undecided items is an honest report of
where the register stands. Deciding them is the next round's first job.

Three new items were added rather than decided - B-22, B-23 and B-24, all
`owed`, carrying rounds 19 and 20 - because an item recorded with a deadline
is the thing this register exists to make possible, and marking any of them
adopted with nothing built would be the register lying.

## What was ruled out (7.4)

- **Fixing the two conflated-degrade candidates in our own guards.** Both
  were read and both are intended (see the table above). Changing
  `handle_line` to distinguish "notification" from "notification" would be a
  change with no defect behind it.
- **Baselining those two and wiring a self-scan into CI.** A baseline whose
  every entry is a false positive is an ignore-list, and 2.1 is explicit that
  a ratchet differs from one by only ever shrinking. If a third candidate
  appears and it is real, that is the round to add the scan.
- **Pointing `ci_step_lint` at `ci/guards.yml` in CI.** It is a template. Its
  paths resolve in the adopter's tree, which is the point of it, and a guard
  that reports a template's whole purpose as seven findings gets muted. What
  is checkable here is the pairing - every script the template runs is one
  `bootstrap.sh` copies - and that is a test.
- **Exporting `Violation` from the package.** Three modules define one, and
  they may not import each other because copy-in files land in different
  directories in an adopter's tree. One package attribute with three owners is
  the shadowing class `test_no_export_shadows_a_submodule` exists to refuse.
- **Adding `--migrate-legacy-baseline` to `conflated_degrade_lint`.** It ships
  with the stable key from its first commit, so it has no legacy format to
  migrate. `Ratchet.migrate_keys` is the general answer and the docstring
  names it.
- **Making `ci_step_lint` resolve non-Python scripts.** A `.sh` or `.mjs` a
  step names is the same class and would be the same check, and every one of
  them would also be a new false-positive surface (a `.sh` written by an
  earlier step, a `.mjs` inside `npx`). Recorded because the next session will
  reach for it.
- **Renumbering or adding a doctrine rule.** 2.7 gained one sentence and the
  genericized scar for its quiet half. R18-3 and R18-4 both land on 6.7, which
  already says what they say; a guard is a mechanism, not a rule.

## Guards touched

`ratchet.py` (the stable-key contract and `migrate_keys`), `detectors.py` and
`dead_route_lint.py` (stable keys), `conflated_degrade_lint.py` and
`ci_step_lint.py` (new), both playbooks, `bootstrap.sh`, `ci/guards.yml` and
`.github/workflows/selftest.yml`.

465 tests before, 550 after.
