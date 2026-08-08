# Backend playbook

How to build backend code with agents that stays correct under real data,
real failure, and real scale. The mechanical guards in
[python/](../python/) enforce the enforceable subset; this playbook covers
the rest.

## The core loop: fix, guard, mutate

Every fix ships with a guard in the same commit, and the guard is shown to
fail before you trust it:

1. Fix the defect.
2. Write (or extend) the guard. Prefer, in order:
   - a **class ratchet**: a detector that walks the code (AST, route table,
     schema) and fails on any current or future sibling of the defect,
     gated by a shrink-only baseline (`sutradhar_guards.ratchet`);
   - a case in an existing themed test file;
   - a new per-defect pin, only when subtle arithmetic demands it.
3. **Mutation-verify**: revert the fix, watch the guard go red, restore.
   Weaken the seam it protects, watch the behavioral cases go red, restore.
   If you cannot make it fail, you have written decoration.

### Step 3 is a command, not a habit

Every rule that lives only in prose gets skipped under deadline pressure,
and this was the one with the worst consequences when skipped. Run it:

```bash
python scripts/verify_guard.py --guard-cmd "python -m pytest tests/test_tenant_scope.py"
```

It checks the fix commit out into a throwaway worktree, confirms the guard
is green there, reverts **only** the production half of the commit (test
files and prose are kept), and runs the guard again. The verdict is the
exit code:

| Exit | Verdict | Meaning |
|---|---|---|
| 0 | `VERIFIED` | red without the fix. The guard is real. |
| 1 | `DECORATION` | green without the fix. It guards nothing - fix the guard, not the report. |
| 2 | `INCONCLUSIVE` | premise broken, timeout, merge commit, no executable change. Never treat as a pass. |

Three things worth knowing before you trust a verdict:

- **`VERIFIED (weak)`** means the guard went red by failing to *load*
  (import or collection error), not by asserting. Removing the fix breaks
  the build, which is weaker evidence than an assertion that discriminates.
  Worth a second look, especially when the fix added a whole module.
- **`INCONCLUSIVE` on a green-looking run is the honest answer**, not a
  nuisance. A guard already red at the fix commit tells you nothing about
  the revert (doctrine 6.4), so the tool refuses rather than guessing.
- **The classification is printed every run.** It splits the commit into
  code (reverted), guards (kept), and inert prose/media. If it guesses
  wrong, say so explicitly with `--code src/billing.py` or
  `--guard-paths checks/`.

For a suite that needs installed dependencies, symlink them into the
worktree instead of reinstalling: `--link node_modules --link .venv`, or
run an explicit `--setup-cmd "npm ci"`.

The one half this does *not* mechanise is "weaken the seam and watch the
behavioral cases go red". That is mutation testing and remains a manual
exercise; the tool says so rather than implying full coverage of 2.2.

Why the ratchet preference is that strong: on our build record, ~37 ratchet
tests produced two thirds of all test-driven discoveries; ~1,400 point pins
produced three. A ratchet keeps finding NEW defects as the code grows; a
pin guards one grave.

### Anatomy of a class ratchet

```python
# tests/test_ratchets.py
import ast
from pathlib import Path
from sutradhar_guards.ratchet import Ratchet, selfcheck_detector

SRC = Path("src")

def find_uncapped_fleet_queries(source: str) -> list[str]:
    """Detector: every query over a growing collection must carry a cap."""
    hits = []
    tree = ast.parse(source)
    # ... walk for the shape of the defect class ...
    return hits

def all_violations() -> list[str]:
    out = []
    for f in SRC.rglob("*.py"):
        for hit in find_uncapped_fleet_queries(f.read_text()):
            out.append(f"{f}:{hit}")
    return out

def test_fleet_queries_are_capped():
    Ratchet("tests/baselines/uncapped_queries.json").assert_only_shrinks(
        all_violations()
    )

def test_the_detector_is_not_blind():
    # Guard the guard: a detector edited into vacuity passes every real
    # file forever. Only a planted bad case catches that.
    selfcheck_detector(
        find_uncapped_fleet_queries,
        "def f():\n    return db.query('SELECT * FROM readings')\n",
    )
```

## Honest degradation

A failure states itself. The concrete rules:

- An `except` block logs, degrades explicitly, or re-raises
  (`swallow_lint.py` enforces this). Returning `{}` from a broad handler
  converts an outage into "there is genuinely nothing here", and downstream
  code will happily compute on the lie. Our worst instance flipped a
  detector's verdict for an entire fleet, under a green status, cached for
  the full TTL.
- A partial result carries a flag the caller must see:
  `(data, ok)` tuples, a `degraded_inputs` list on the response, a
  `status: "error"` with a stated reason. Pick one idiom per project.
- When a function grows a new state (a third value, an abstention), grep
  every branch AND every string that describes its output. We fixed a
  detector's abstention logic and left prose that still spoke for the
  absent input as if it had voted.
- Confirmations are earned. "Deleted", "sent", "erased" are only said when
  every layer verifiably succeeded. A purge that hit a datastore limit and
  removed nothing must not report ok.

## Scale discipline

Every "works fine" you have ever observed was probably at demo scale.
Rules that survived contact with a 4,000x scale jump:

- **State the N at design time** and put it in the PR. Tests enforce the
  envelope.
- **No unbounded reads**: any sweep over a growing collection carries a cap
  and refuses honestly above it ("too large", with the count), instead of
  materializing it.
- **ORDER BY on an unbounded result set is a memory bomb** in most stores;
  an unordered stream with a cap is the safe shape.
- **Watch the zero-data case**: an anchor query that is O(1) when recent
  data exists can be a full-table walk when none does, which means your
  newest customer hits it on day one.
- **Sync work on an async path stalls every concurrent request.** Thread
  it off the loop, and check the framework actually runs your guard where
  you think it does (a `def` dependency running in a threadpool got its
  context write silently discarded; the fix was `async def`).

## Scale discipline starts at design time

The cheapest rule in this framework is a sentence written before the code:
*this must survive 200,000 meters, inside 800ms and 512MB.* The sentence
costs nothing. Skipping it cost us a full scale pass and seventeen store
crashes on a sweep that was flawless at demo scale.

Put the numbers where a machine can read them - the design note's
frontmatter - and let the test take its N from there:

```python
from sutradhar_guards.budget import budget

def test_fleet_sweep_at_design_scale():
    with budget("fleet-sweep") as b:
        sweep(synth_meters(b.n))        # b.n IS the declared 200,000
```

Two properties fall out of that and both matter more than they look:

- **Nobody hand-picks a comfortable N.** The number in the test is the
  number in the design, always, because there is only one of them.
- **Weakening a budget becomes an argument, not an edit.** Raising the
  design figure shows up as a diff in a document a reviewer reads. Quietly
  changing `200_000` to `2_000` in a test file does not.

Then close the loop, because a budget nobody enforces is decoration in
exactly the way an untested guard is:

```bash
python scripts/budget.py docs/design/ --tests tests/
```

It fails on any declared number that no test so much as mentions. Note what
this gate is *not*: it does not ask "does this feature have a design note".
That question measures paperwork, cannot be answered mechanically (what is
a "feature"?), and is satisfied by an empty file. It asks the harder one -
is every number you wrote down actually binding.

Two honest limits worth knowing before you trust a green run. `memory_mb`
is measured with `tracemalloc`, so it counts Python heap allocations and
not process RSS - a good tripwire for "this structure grew unbounded", a
bad one for "the container OOMed", where the drill remains the authority.
And the latency check is a ceiling on the runs you performed, not a
percentile: `p95_ms` records design intent, and a single sample above it
fails. On shared CI runners declare `ci_slack: 2.0` in the note rather than
inflating the real number, so the looseness stays visible.

## Numeric truth

- Golden datasets with declared tolerances for anything numeric.
  Re-baseline only deliberately, in the same commit as the intentional
  change, with the reason in the message.
- Property tests on parsing and numeric surfaces: examples pin known
  cases, properties pin the space.
- Cumulative vs interval, units, and timezones are where the money bugs
  live. Test wraparound, reset, out-of-order, and the first-ever row.

## Test-tier honesty

- Env-gated tiers must audit their own gates
  (`sutradhar_guards.envgate.audit_skip_gates`). A skip marker nothing sets
  is a deleted test that still shows up in your file count.
- Test through the real seam: the route, not the helper. A helper test
  cannot see the handler's missing import.
- Never stand up a second app instance per test when the lifespan is
  expensive; share a session-scoped client.
- When comparing two runs, disable test-order randomization first; a
  stateful flake looks exactly like a regression.
