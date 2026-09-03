---
sutradhar_scar: <finding-id, or `distribution`>
sutradhar_scar_argument: <one sentence - required only when the scar is `distribution`>
sutradhar_budget: <short-id>
n: 200000
n_unit: rows
rps: 50
p95_ms: 800
memory_mb: 512
ci_slack: 2.0
---

# Design note: <feature>

<!-- The prevention discipline as a fillable template. Five minutes here
     is the cheapest engineering you will do all week; every section maps
     to a doctrine rule (1.1-1.4) with a named incident behind it. Delete
     the comments as you fill it in.

     The frontmatter above is READ BY THE TEST SUITE. Delete any line you
     genuinely have no number for; keep at least one. Flat `key: value`
     scalars only - the parser refuses anything it would have to guess at.
     See docs/design/lint-scan.md for a filled-in example.

     `sutradhar_scar` is REQUIRED and is doctrine 8.1 applied to mechanisms:
     name the finding id(s) from your round records that paid for this one,
     comma-separated, and `rounds.py --designs` will resolve every one of
     them. If no incident paid for it - if what you are really arguing is
     reach, adoption or convenience - write `distribution` and say so in one
     sentence in `sutradhar_scar_argument`. That is a legitimate answer. A
     mechanism that entered on argument alone and never said so is not. -->

## What and why

One paragraph. Who needs this, what decision or action it enables.

## Cardinalities and budgets  <!-- doctrine 1.1 -->

<!-- Numbers, not adjectives. "Lots of rows" is not a cardinality.

     The numbers live in the frontmatter so a test can read them; this
     table is for the humans, and for the reasoning the frontmatter cannot
     carry. State the PROVENANCE of each figure (doctrine 5.1): which are
     measured, which are chosen ceilings, which are guesses to revisit. -->

| Dimension | Design N | Enforced by |
|---|---|---|
| rows / entities this must survive | `n` | |
| concurrent users / requests per second | `rps` | |
| latency envelope (p95) | `p95_ms` | |
| memory envelope | `memory_mb` | |

The test that makes these binding:

```python
from sutradhar_guards.budget import budget

def test_<feature>_at_design_scale():
    with budget("<short-id>") as b:
        run_the_thing(make_input(b.n))     # b.n IS the declared N
```

A budget nobody enforces is decoration; `budget.py <notes>/ --tests
<tests>/` fails the build on any declared number no test mentions.

## Failure story  <!-- doctrine 1.4 -->

<!-- For EACH dependency: what does the user see when it is down, slow,
     or partial? "Same as success" means the design is not done. -->

| Dependency | Down | Slow | Partial |
|---|---|---|---|
| | | | |

## Illegal states  <!-- doctrine 1.2 -->

<!-- What invalid states can the types make unrepresentable, so no test
     is needed? What remains and needs a ratchet? -->

## Data provenance  <!-- doctrine 5.1, if any output carries numbers -->

<!-- Which figures are measured, which estimated (state assumptions),
     which illustrative? How does the surface show the tier? -->

## Guards shipping with this

<!-- Doctrine 2.1: named tests/ratchets, in the same PR, each one
     mutation-verified (you watched it fail). -->

- [ ]
