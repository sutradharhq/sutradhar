# Round 14 - 2026-09-03

Lenses: cross-thread survey, backflow, adopter-reported defects

**What this round was.** A survey of what the other build threads have learned
since round 7, and the first round in which any of it crossed on purpose.

Round 7 found that four independent threads had solved problems this doctrine
still listed as open, filed it as R7-1 (high), and deferred it. It stayed
deferred for six rounds. Every crossing that happened in that time happened as
a side-effect of somebody building a tool — never because anyone decided. That
is not a scheduling failure; it is the absence of a mechanism, and R7-1 said so
at the time.

This round built the mechanism, and then used it.

## The survey

Twenty-two candidates came back. Two of them were not proposals at all — they
were defects in files this repo ships, found by the threads using them:

- **`expectEffect` was blind to form state.** It compared the URL,
  `body.innerText`, and configured storage keys. `innerText` reports neither an
  input's value nor a button's `disabled` attribute, so typing into a field and
  watching a submit button enable moved nothing it could see. Both directions
  were wrong: a working control read as broken, and — the expensive one — a form
  that silently did nothing read as fine. Forms are where the money controls
  live, so the blind spot sat in the highest-stakes surface the helper is
  pointed at.
- **`swallow_lint` walked vendor trees.** The only exclusion was
  `__pycache__`. Pointed at a project root it descended into `.venv` and
  returned dozens of third-party findings around the one real one. The guard
  was not wrong; its signal was unreadable, and it was switched off that
  afternoon. Same outcome as a broken guard, by a slower route.

Neither was findable by reading this repo. Both were found by operating it
somewhere else, which is 6.1 arriving from outside.

The strongest *rule* evidence was convergence. **Four threads independently
invented the same rule**: a check that cannot measure must refuse rather than
pass. One returned `None` both for "could not compute" and "computed, failed",
over an optional dependency — so every deployment missing that library ran with
the gate silently disabled under a green suite. The others arrived at the same
shape from different directions: `UNARMED` rather than "not triggered", an
`INSUFFICIENT_EVIDENCE` verdict that names what would resolve it, and a refusal
rate published beside the pass rate.

This repo's *tooling* already knew that rule — 33 `INCONCLUSIVE` references
across `verify_guard.py` and `obsgate.py`. The doctrine stated it once, in
passing. Four threads each paid separately for something already mechanized
here and never written down.

## The mechanism

`docs/backflow.md`, gated by `rounds.py --backflow`. An item past its
`by-round` and still `owed` or `deferred` fails the gate, and the only ways out
are decisions: adopt, reject with a reason, or re-defer to a later round with a
reason. The register is seeded with 19 items, five of them inherited from
round 7 and carrying no deadline until now.

The `evidence` column is the part that keeps 8.1 honest. A charter, protocol or
ADR is an intention, not an incident, so a `practice` item may strengthen the
mechanism of a rule that already has a scar but may not found a new one. The
gate refuses `practice` + `new`. Without that, a survey of well-run repos
inflates the doctrine with things nobody has paid for — which is how a scar
corpus becomes a style guide.

## Findings

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
| R14-1 | high | 3.1 | Thread-B | fixed | `expectEffect` compared URL, body text and storage - none of which report an input's value or a button's disabled state - so it was blind on forms, the surface it is most often pointed at |
| R14-2 | med | 2.1 | Thread-B | fixed | `swallow_lint`'s only walk exclusion was `__pycache__`, so a project-root scan buried the real finding under vendor ones and the guard was disabled rather than fixed |
| R14-3 | high | 2.9 | thread survey | fixed | four threads independently invented "a check that cannot measure must refuse"; the tooling here already enforced it in 33 places and the doctrine stated it once, in passing |
| R14-4 | med | 2.9 | self | fixed | the backflow parser skipped any row without exactly eight cells, so the first real register silently lost an item to a pipe inside a note while the gate printed OK - 2.9 violated by the commit that added 2.9 |
| R7-1 | high | - | thread survey | closed | closed by this round: `docs/backflow.md` plus the `--backflow` gate is the mechanism R7-1 said was missing. 19 items registered, 3 decided here. Recorded under its original id so the residual register actually clears it - a closure filed under a new id leaves the deferral open, which is how a register drifts from the thing it claims to track |
| R14-5 | med | 8.1 | thread survey | deferred | this repo's public `DOCTRINE.md` lags the maintainer's standing doctrine and the two have diverged in section 2; two independent agents cited a section 6 rule that does not exist here. Reconciling them must not renumber published ids - 89 findings cite them (B-19) |
| R14-6 | med | 5.1 | Thread-K | deferred | per-value provenance tiers with weakest-input propagation - the strong form of what 5.1 has owed since round 7 (B-7) |
| R14-7 | low | 8.1 | thread survey | deferred | candidates drawn from charters and protocols carry no recorded cost; the register marks them `practice` and refuses them as new rules, but nothing yet measures how many `practice` items later earn a scar (B-11, B-12) |
| R14-8 | med | 8.1 | maintainer question | fixed | mechanisms had no admission criterion - every design note that entered cited a scar by habit, one cited nothing, and nothing would have refused a note that cited nothing. `--designs` now requires every note to name the finding that paid for it or to say `distribution` out loud |

## What was ruled out (7.4)

- **Adopting the twenty-two candidates as rules.** Most are mechanisms, not
  rules, and several rest on documented intentions rather than incidents. They
  are in the register with an evidence tier, which is the honest place for
  them.
- **A separate `backflow.py` guard.** It would need `rounds.py`'s rule ids and
  round numbers anyway, and copy-in adopters do not need a fourteenth file.
- **Renumbering `DOCTRINE.md` to match the maintainer's standing doctrine.**
  `rounds.py` resolves every finding's citation against this file. Renumbering
  silently reassigns 89 citations. Recorded as B-19 with the hazard named.
- **Backdating the register's deadlines to round 14.** Three items were decided
  this round; writing 14 against the rest would have been a deadline blown in
  the same commit that set it.

## Mutation verification (2.2)

Every guard added this round was shown able to fail before it was trusted.

| guard | mutant | result |
|---|---|---|
| `readFormState` selftest | return `""` (the pre-fix blindness) | 8 cases red |
| | drop `disabled` from the digest | 1 red |
| | drop the `aria-*` reads | 2 red |
| uiGuards source ratchets | drop `form` from `EFFECT_DIMENSIONS` | 1 red |
| | CI stops running the selftest | 1 red |
| | comparison stops iterating the list | 1 red |
| `swallow_lint` vendor exclusion | exclusion never fires | 3 red |
| | skip happens but is not reported | 1 red |
| | `_is_vendor` ignores the named root | 1 red |
| backflow gate | overdue check never fires | 3 red |
| | `practice` may found a new rule | 1 red |
| | malformed rows skipped again | 1 red |
| | missing register reports OK | 1 red |
| | reasonless deferral accepted | 2 red |
| scar gate | the unknown-id check never fires | 10 red (2 direct, 8 through the selfcheck `main` runs first) |
| | a missing `sutradhar_scar` is skipped, not refused | 10 red (2 direct, 8 the same way) |
| | `distribution` no longer requires an argument | 10 red (2 direct, 8 the same way) |
| | a missing designs directory returns 0 | 3 red |
| `rounds --selfcheck` | overdue check disabled | exit 1 (exit 0 when restored) |
| | unknown-id check disabled | exit 1 (exit 0 when restored) |

370 tests, up from 310.
