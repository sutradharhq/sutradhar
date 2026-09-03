# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Class ratchets over the Cypress guard source.

`expectEffect` shipped for its whole first life blind to form state: it
compared the URL, `body.innerText`, and configured storage keys, and
`innerText` reports neither an input's value nor a button's disabled
attribute. Typing into a field and watching a submit button enable moved
nothing it could see - a false red on a working control, and worse, a silent
pass over a form that genuinely did nothing.

The behavioral proof lives in `js/cypress/uiGuards.selftest.mjs`, which runs
the compiled shipped source against a DOM stub. These are the guards that
selftest cannot be: that the dimension is still wired into the comparison,
and that the selftest is still executed by CI. A selftest nothing runs is
the decoration this repo is about (2.2).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_GUARDS = REPO_ROOT / "js" / "cypress" / "uiGuards.ts"
SELFTEST = REPO_ROOT / "js" / "cypress" / "uiGuards.selftest.mjs"
CI = REPO_ROOT / ".github" / "workflows" / "selftest.yml"


def test_form_state_is_one_of_the_dimensions_expecteffect_compares():
    """The fix in one assertion. `EFFECT_DIMENSIONS` drives both the snapshot
    and the comparison, so dropping "form" from it is the whole regression."""
    src = UI_GUARDS.read_text(encoding="utf-8")
    m = re.search(r"const EFFECT_DIMENSIONS = \[([^\]]*)\]", src)
    assert m, "EFFECT_DIMENSIONS no longer exists - expectEffect was restructured"
    dims = {d.strip().strip('"\'') for d in m.group(1).split(",") if d.strip()}
    assert dims == {"url", "text", "form", "store"}, (
        f"expectEffect now watches {sorted(dims)}. Adding a dimension is fine "
        "(update this test); losing one is a regression - 'form' in particular "
        "is the one the other three are structurally blind to."
    )


def test_the_snapshot_and_the_comparison_are_driven_off_the_same_list():
    """The half-wiring failure: a dimension captured but never compared (or
    the reverse) is invisible and makes the guard weaker in silence. Both
    sides must iterate EFFECT_DIMENSIONS rather than naming fields by hand."""
    src = UI_GUARDS.read_text(encoding="utf-8")
    body = src[src.index("export function expectEffect") :]
    body = body[: body.index("\n}\n") + 3]
    assert "EFFECT_DIMENSIONS.filter" in body, (
        "the comparison no longer iterates EFFECT_DIMENSIONS - if it now names "
        "dimensions individually, a captured-but-uncompared field is possible "
        "again and this ratchet cannot see it"
    )


def test_readformstate_reads_the_properties_innertext_cannot_see():
    """Presence-based, and says so (3.6): this asserts the digest still names
    each property, not that it reads them correctly. Correctness is the
    selftest's job; this catches a field quietly dropped from the digest."""
    src = UI_GUARDS.read_text(encoding="utf-8")
    fn = src[src.index("export function readFormState") :]
    fn = fn[: fn.index("\n}\n")]
    for prop in ("value", "checked", "disabled", "aria-disabled", "aria-expanded"):
        assert prop in fn, f"readFormState no longer looks at {prop!r}"


def test_the_selftest_exists_and_ci_runs_it():
    """The skip-gate class, applied to ourselves: a selftest that CI does not
    invoke is a file, not a check. This repo has already paid for a guard whose
    selfcheck was never wired (round 4) - exit 0 from a process that checked
    nothing."""
    assert SELFTEST.exists(), "uiGuards.selftest.mjs is gone"
    ci = CI.read_text(encoding="utf-8")
    assert "node js/cypress/uiGuards.selftest.mjs" in ci, (
        "CI no longer runs the uiGuards selftest. Restore the step in "
        ".github/workflows/selftest.yml or this guard is unwitnessed."
    )


def test_the_selftest_refuses_rather_than_passing_when_it_cannot_run():
    """A check that could not run has not passed. If esbuild is unavailable the
    selftest must exit non-zero and say nothing was checked - the alternative
    is a green CI square over a guard that never executed."""
    src = SELFTEST.read_text(encoding="utf-8")
    assert "process.exit(2)" in src, "the cannot-run path no longer exits non-zero"
    assert "CANNOT RUN" in src, "the cannot-run path no longer says whose failure it is"


def test_bootstrap_ships_the_selftest_with_the_guard():
    """An adopter who gets uiGuards.ts without its selftest has no way to know
    the digest still works in their tree."""
    bootstrap = (REPO_ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    assert "uiGuards.selftest.mjs" in bootstrap
