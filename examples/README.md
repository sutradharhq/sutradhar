# The worked example

A tiny meter-billing app with seven defects in it. Its test suite is green.

```bash
bash examples/run-the-guards.sh
```

Needs `python3` and `pytest`. No install, no network, about ten seconds.

The script runs the app's own tests first - five pass, one skips - and then
runs the guards over the same code. Seven defects surface. None of them
would be found by reading the file, and none of them are found by the tests
that ship with it.

That gap is the entire argument of this repo: **a green suite is evidence of
nothing until something has shown it can go red.**

---

## What is planted, and why each one matters

### 1. A silent swallow turns an outage into data

`app/readings.py`

```python
def latest_readings(store, meter_id):
    try:
        return store.fetch(meter_id)
    except Exception:
        return {}
```

The caller cannot distinguish "this meter genuinely reported nothing" from
"we could not reach the store". Downstream, that difference is a bill.

*The original: a fleet-wide read failure was swallowed into `{}`, which the
next layer read as "an event-free fleet", flipping a fraud detector's
verdict for every entity at once - under a green status page.*

Caught by `swallow_lint.py` (doctrine 2.7). Note it is a **ratchet**: on a
real codebase you record today's count as the floor and only new swallows
fail the build, so you can adopt it on a tree with hundreds of them.

### 2. An unbounded ORDER BY

```python
HISTORY_QUERY = "SELECT ts, kwh FROM readings WHERE meter = ? ORDER BY ts DESC"
```

Sorting a table that grows with every reading, with no `LIMIT`. Perfect on
the demo dataset; a memory bomb on a meter that has been reporting for a
year.

*The original: a sweep that was flawless at 50 entities OOM-crashed the
datastore at 200,000.*

Caught by `detectors.find_order_by_without_limit` (doctrine 2.6).

### 3. SQL built by interpolation

```python
return f"SELECT ts, kwh FROM readings WHERE meter = '{meter_id}'"
```

Safe today, because the only caller passes an integer. The pattern becomes
the vulnerability the moment someone wires it to a request parameter - and
nobody re-audits a line that was fine last year.

Caught by `interpolation_lint.py` (doctrine 2.8). Do not baseline this one;
fix it. The shape *is* the hole.

### 4. A model that invents numbers

`app/report.py` returns "Your usage rose 47% this month to 1,240 kWh". The
witnessed values were 980 kWh and 12%. Every figure in that sentence is
fabricated, and the prose is fluent enough that a careful reader signs off.

Caught by `claim_check.py` (doctrine 4.1: the model phrases, it never
invents). It grounds each number against the values you actually computed
and returns the ones that trace to nothing.

### 5. A skip gate nothing sets

`tests/test_billing_integration.py` carries a `billing_integration` marker.
`tests/conftest.py` skips it unless `BILLING_TESTS` is set. Nothing sets
`BILLING_TESTS` - not the workflow, not a Makefile, nothing.

So the test that would actually catch a billing error **has never run
anywhere**, while the suite counts it and reports green. A skip marker
nothing sets is indistinguishable from a deleted test.

*The original: ~86 tests, including the entire billing arithmetic, were
discovered to have been executing in no environment at all.*

Caught by `envgate.audit_skip_gates`. Worth seeing once: the audit is a
**textual** check, so even naming the variable in a comment satisfies it.
That caveat is in its docstring, and this example's CI file deliberately
avoids the word so the demo shows the real failure. Pair the audit with one
real CI run where you confirm the gated tier's tests appear in the count.

### 6. A budget declared and never enforced

`docs/design/sweep.md` promises 200,000 meters inside 800ms and 512MB.
Nothing holds the code to it. The note reads like a commitment and behaves
like a wish.

Caught by `budget.py` (doctrine 1.1). Note what the gate does *not* ask -
"does this feature have a design note", which measures paperwork. It asks
whether every number you wrote down is actually binding.

### 7. A test that cannot fail

`tests/test_billing.py`:

```python
def test_bulk_discount_applies():
    subtotal = 1000 * 0.5
    subtotal *= 0.9              # the test re-implements the fix locally
    assert subtotal == 450.0
```

It never calls `total()`. Delete the bulk discount from `app/billing.py` and
this test stays green. In review it reads exactly like a test that works.

*The original, and the worst week on the record: a tenant-isolation fix
shipped tested-and-half-dead for a week, because its tests set internal
state by hand instead of exercising the real seam.*

Caught by `verify_guard.py` (doctrine 2.2), which reverts the production
half of the fix commit, keeps the tests, and reports `DECORATION` when the
guard survives. The demo builds a throwaway two-commit repo to show it,
because the tool needs real history.

---

## What is deliberately not here

The frontend guards - asserted effects on every control (`expectEffect`),
the route sweep, and overprint detection - are not in this walkthrough. They
need Cypress, npm, and a browser, which would turn a ten-second demo into a
five-minute install and break the one thing this example is for.

They are real and they carry their weight; the picker that rendered, opened,
accepted a selection and changed nothing was found by exactly that guard.
See [`js/cypress/uiGuards.ts`](../js/cypress/uiGuards.ts) and
[`routeSweep.example.cy.ts`](../js/cypress/routeSweep.example.cy.ts), plus
[`docs/frontend.md`](../docs/frontend.md).

Also absent: the operational drills. Restore-reconciliation and
cold-start-from-docs found more than any code-reading round on the original
record, and neither can be demonstrated in a shell script - you need a stack
and a few hours. That is the point of [`ops-drill.md`](../agent/skills/ops-drill.md),
and it is the honest limit of a demo like this one.

## This example is itself under guard

A walkthrough that has quietly stopped catching its planted defects fails in
the most damaging place possible: in front of someone deciding whether any of
this works. So `run-the-guards.sh` exits nonzero if any defect goes
uncaught, and `python/tests/test_examples.py` runs it in CI on every push.

That test was mutation-verified before it was trusted: fixing the silent
swallow, making the decorative test real, or enforcing the orphan budget
each turns the runner red at 6 of 7. Which is the same discipline the
example is teaching, applied to the example.
