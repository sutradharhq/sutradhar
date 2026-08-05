# Design note: <feature>

<!-- The prevention discipline as a fillable template. Five minutes here
     is the cheapest engineering you will do all week; every section maps
     to a doctrine rule (1.1-1.4) with a named incident behind it. Delete
     the comments as you fill it in. -->

## What and why

One paragraph. Who needs this, what decision or action it enables.

## Cardinalities and budgets  <!-- doctrine 1.1 -->

<!-- Numbers, not adjectives. "Lots of rows" is not a cardinality. -->

| Dimension | Design N | Test-enforced at |
|---|---|---|
| rows / entities this must survive | | |
| concurrent users / requests per second | | |
| latency envelope (p95) | | |
| memory envelope | | |

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
