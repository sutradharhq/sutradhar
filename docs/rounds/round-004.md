# Round 4 - 2026-08-15

Lenses: self-application, instrument validity, CLI surface

**What this round was.** The first run of the weekly review routine, and it
found the defect class the framework exists to name - inside the framework's
own guard suite. Recorded because a maintenance pass that finds something
real is the only kind worth keeping on a schedule, and because the report
that opened this round was itself wrong in the way R3-1 predicted.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R4-1 | high | 2.2 | weekly review | fixed | `--selfcheck` exited 0 on five of ten modules that had no `__main__` block at all. The flag was ignored, the module imported, the interpreter exited 0, and the zero was read as a passing check |
| R4-2 | med | 2.4 | weekly review | fixed | four CLIs silently skipped unrecognised flags, so a typo like `--selfchek` ran the default scan and exited 0 |
| R4-3 | med | 6.3 | weekly review | fixed | four selfchecks passed silently; a check that prints nothing cannot be told apart from one that never ran |
| R4-4 | low | 8.2 | weekly review | fixed | `__init__` imported every submodule eagerly, so `python -m` emitted a RuntimeWarning on every CLI run of six tools |
| R4-5 | med | 5.1 | weekly review | deferred | `docs/operations.md` carries an "Observability floor" that no doctrine rule numbers and no tool enforces. `rounds --check` cannot accept a finding against it, because there is no rule id to cite |
| R2-4 | high | 3.6 | - | deferred | unchanged: still awaiting a second repo |
| R1-7 | med | 2.2 | - | deferred | unchanged |
| R1-8 | med | 1.1 | - | deferred | unchanged |
| R1-9 | low | 1.1 | - | deferred | unchanged |

## Corrected premises

### "Exit 0 means the check passed" (R4-1)

The report that opened this round stated: *8 tool selfchecks, exit 0 times
eight, all pass.* Three of those modules had no selfcheck reachable from the
command line. They exited 0 because importing a module and doing nothing
succeeds.

This is **R3-1 recurring one round later, in the pass built to catch it.**
Round 3 wrote it down as "a verification aimed at a queryable proxy passed
repeatedly while the surface that carried the consequence disagreed", held it
for a second incident, and declined to promote it. This is the second
incident. The instrument was the exit code; the thing it measured was process
termination, not verification.

The generalisation, now with two scars behind it:

> *An exit code is a claim about a process, not about a check. It becomes
> evidence only in pairs: a known-good input must exit 0 AND a known-bad
> input must exit non-zero. One half alone is decoration.*

Still not promoted to DOCTRINE.md. **2.2** already says a guard never shown
to fail is decoration, and this is that rule applied to the guard suite's own
CLI rather than a new rule. The correct response to a rule being violated is
to mechanise the rule, not to write a second rule saying the same thing -
which is what `test_selfcheck_reachability.py` now does. If a third incident
lands in a place 2.2 does not reach, promote it then.

### "A guard proves its worth against planted defects" (R4-2)

It proved its worth against a real one within a minute of existing. The
health command used all round - `rounds --check --rounds docs/rounds` - is
malformed. `--rounds` is not a flag; the records directory is positional.
That command had been silently accepted for the entire life of the tool
because unknown flags were skipped, and the first thing the new rejection did
was fail it.

Nobody planted that. It was in the reviewer's own fingers, and it had been
passing.

## Harness gotchas

- `pytest` vanished from the system interpreter partway through the session.
  `examples/run-the-guards.sh` defaults to `PY="${PYTHON:-python3}"` and duly
  reported defect 7 as MISSED. Doctrine 6.4 says verify the finding refutes
  the null before filing it: it did not. `PYTHON=.venv/bin/python` gives 7 of
  7 and exit 0. A missing test runner is indistinguishable from a broken
  guard if you only read the summary line.
- The new ratchet was written before the fixes and shown red (25 failed, 6
  passed), then green (31 passed), then mutation-verified by deleting
  `golden`'s `__main__` - which fails exactly the two `golden` assertions and
  nothing else. A ratchet that was never shown to fail would have been the
  same defect one level up.
- The ratchet carries `test_the_package_actually_has_modules`. Without it,
  a `pkgutil.iter_modules` that returned nothing would make every
  parametrised assertion vacuously pass (doctrine 3.6).

## The observability gap (R4-5)

Asked directly whether Sutradhar supports observability, the honest answer is
no, and the gap is structural rather than accidental.

`docs/operations.md` has a good six-line "Observability floor": four surfaces
with metrics (requests by route *template*, jobs, ingest chokepoints,
dependency gauges), probes that must not block the serving path, and a
metrics endpoint that degrades to an honest comment block rather than an
empty 200 a scraper reads as all-zero. That last line is 2.4 applied to
telemetry, and it is the sharpest sentence in the file.

But it is orphaned. It carries no rule number, so `rounds --check` will
reject any finding that cites it. No tool enforces any part of it. The
README's own caption for `operations.md` does not mention it. Every other
pillar - backend, frontend, AI, claims - has at least one mechanised guard;
this has none.

The structural reason: **everything Sutradhar mechanises is checkable before
deploy.** Observability is the one discipline whose entire value arrives
after. That is doctrine 8.5 (*the unvalidated loop is production*) naming its
own boundary, and it is honest for the framework to have a boundary. What is
not honest is prose that reads like doctrine without being numbered,
enforced, or citable.

Left DEFERRED rather than fixed. Numbering it is cheap and would take ten
minutes; mechanising it is not, and a rule with no mechanism is what 8.1
warns about. The decision belongs with a maintainer, not with a maintenance
pass.

## Stop decision

**Unchanged.** v0.3.0 stays closed at four of seven items.

Nothing here is external evidence. Every finding came from the author's own
routine running against the author's own repo, which is the WEAKER form
(8.4) and does not meet the restart bar recorded in round 2. This round ships
one ratchet and four repairs; it builds no new tool and promotes no new rule.

Worth recording plainly: the repo has 0 stars, 0 forks and 0 watchers. The
restart condition - evidence from a repository that is not this one - is
therefore **unreachable by construction**, not merely unmet. No second repo
can report a defect class in code nobody has. Doctrine 8.4 asks for outside
minds on purpose and budgets for them; this repo has a rule requiring them
and no mechanism for obtaining any. That is the binding constraint on this
framework, and it is a distribution problem rather than an engineering one.
