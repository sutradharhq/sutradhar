# Design note: scope — framework, not a product

<!-- The repo's own scope statement. It has a matching gate, so this note is
     the prose beside a mechanism rather than a promise on its own. -->

## What and why

Sutradhar is a **framework**: a copy-in toolkit of stdlib-only guards, a
doctrine, and the agent workflow around them. It ships no runtime, no service,
and nothing to install. This note states the boundary that identity draws, and
points at the gate that keeps the repo inside it.

The one-line form: **checkable before deploy belongs here; witnessed after
deploy does not.**

## The line, and why it is exactly there

Everything Sutradhar mechanises is checkable *before* code runs in production —
a ratchet over a source tree, an assertion proven able to fail, a declared
budget a test enforces, a claim grounded in a computed value. That is why it
can be copy-in and dependency-free: a pre-deploy check needs your code and the
standard library, nothing more.

The disciplines whose value arrives *after* deploy — witnessing a running
fleet, a tamper-evident record of what an agent did, drills against a live
system — are deliberately out of scope for this repository. Not because they
do not matter, but because they cannot be a copy-in file: they need a running
service and a party that is not the code under test. Round 4 recorded this as a
structural boundary (R4-5), not an omission; doctrine 6.6 draws the same line
from the other side, admitting observability only as a *provenance gate* on
what a pre-deploy claim is worth, never as a monitoring runtime living here.

A reader who wants the after-deploy half should not find a half-built version
of it in this repo. They should find a framework that is complete for its job
and honest about its edge.

## The mechanism

`python/sutradhar_guards/framework_only.py` enforces the boundary so it cannot
erode by accident:

- every shipped guard in `sutradhar_guards/` imports the standard library only;
- no dependency manifest (`requirements.txt`, `pyproject.toml`, `package.json`,
  a lockfile) appears anywhere in the framework surface, `examples/` excepted —
  an example is allowed to be a real application with real dependencies.

The first `import requests` or the first `requirements.txt` is the moment the
framework starts becoming a product. The gate turns that into a visible diff
that fails CI, rather than a drift nobody decided on. It is itself stdlib-only,
so it passes its own check.

## What this note is not

It is not a product announcement. If an after-deploy product is ever built, it
lives in its own repository under its own invariants (it *may* take
dependencies; it *must* leave a witnessed record) — and this note is updated to
link it, not to blur the line. Adopters build products with this framework; the
framework itself stays a framework.
