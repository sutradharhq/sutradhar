---
sutradhar_scar: distribution
sutradhar_scar_argument: No round record charges the lint scan with a blown envelope. This note exists so the budget gate holds a real number in this repo and adopters read a filled-in example beside the blank template.
sutradhar_budget: lint-scan
n: 2000
n_unit: source files
p95_ms: 4000
memory_mb: 16
ci_slack: 2.0
---

# Design note: the lint scan

<!-- This is the repo's own budget, so the gate has something real to hold
     and readers have a filled-in example next to the blank template. -->

## What and why

`swallow_lint` and `interpolation_lint` walk a whole source tree on every
CI run. They are the cheapest guards in the toolkit and they are only cheap
if they stay linear in file count.

## Cardinalities and budgets  <!-- doctrine 1.1 -->

| Dimension | Design N | Enforced by |
|---|---|---|
| source files in one scan | 2,000 | `test_lint_scan_holds_its_declared_envelope` |
| wall clock for that scan | 4,000 ms (x2 CI slack) | same |
| peak Python heap | 16 MB (x2 CI slack) | same |

**Provenance of these numbers** (doctrine 5.1): the ceilings are *chosen*,
the baseline behind them is *measured*. On a 2026 laptop, 2,000 files took
1,236 ms and 0.12 MB of peak Python heap. The wall-clock ceiling is ~3x
that baseline so a shared CI runner does not flake; the memory ceiling is
deliberately loose because its job is not a tight fit but a **tripwire for
unbounded accumulation** - a change that holds every parsed AST would clear
16 MB immediately, and that is the regression worth catching.

2,000 is the design N because it is roughly 4x the largest single package
we expect anyone to point these lints at in one invocation. If your tree is
bigger, raise the number here - deliberately, in a diff someone reviews -
rather than quietly lowering the test.

## Failure story  <!-- doctrine 1.4 -->

| Dependency | Down | Slow | Partial |
|---|---|---|---|
| the filesystem | scan aborts with the OS error; CI red | budget breach names the elapsed ms | unreadable files are decoded with `errors="replace"`, never skipped silently |

## Illegal states  <!-- doctrine 1.2 -->

The lints hold no cross-file state, which is what keeps the scan linear.
That is the invariant the memory tripwire exists to defend: a future
"collect everything then report" refactor is exactly the shape that breaks
it, and it would pass every correctness test in the suite.

## Guards shipping with this

- [x] `test_lint_scan_holds_its_declared_envelope` (enforces all three numbers)
