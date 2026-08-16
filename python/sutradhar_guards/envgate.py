"""Env-gated test tiers that audit their own skip gates.

The trap this module exists for: a pytest marker like ``requires_full_stack``
that auto-skips unless an env var is set is a fine pattern - until nothing
anywhere sets the var. Then the gated tests run in NO environment while the
suite reports green, and a skip marker nothing sets is indistinguishable
from a deleted test.

That happened to us: ~86 tests, including the entire billing arithmetic,
were discovered to have never executed anywhere. The conftest even claimed a
CI job set the variable; the claim was false and nothing checked it.

So this module gives you both halves:

1. ``register_env_gate`` - the standard auto-skip wiring for conftest.py.
2. ``audit_skip_gates`` - a test that FAILS unless every gating env var is
   actually set by something in your CI config. The gate audits itself.

conftest.py wiring:

    from sutradhar_guards.envgate import EnvGate, apply_env_gates

    GATES = [
        EnvGate(marker="requires_full_stack",
                env_var="FULL_STACK",
                reason="needs the full docker stack"),
    ]

    def pytest_configure(config):
        for g in GATES:
            config.addinivalue_line("markers", f"{g.marker}: {g.reason}")

    def pytest_collection_modifyitems(config, items):
        apply_env_gates(GATES, items)

And the audit, as a normal test:

    def test_every_skip_gate_is_set_somewhere():
        audit_skip_gates(GATES, search_globs=[".github/workflows/*.yml",
                                              "Makefile", "docker-compose*.yml"])
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvGate:
    marker: str          # pytest marker name
    env_var: str         # env var that enables the tier
    reason: str = ""     # human explanation shown in the skip message

    @property
    def enabled(self) -> bool:
        return os.environ.get(self.env_var, "").lower() in ("1", "true", "yes")


def apply_env_gates(gates: list[EnvGate], items) -> None:
    """pytest_collection_modifyitems body: skip gated tests when disabled."""
    import pytest

    for gate in gates:
        if gate.enabled:
            continue
        skip = pytest.mark.skip(
            reason=(
                f"{gate.reason or gate.marker} - set {gate.env_var}=1 to enable"
            )
        )
        for item in items:
            if gate.marker in item.keywords:
                item.add_marker(skip)


def audit_skip_gates(
    gates: list[EnvGate],
    search_globs: list[str],
    root: str | Path = ".",
) -> list[str]:
    """Return the list of env vars that no searched file ever sets.

    Raise-style use in a test:

        missing = audit_skip_gates(GATES, [".github/workflows/*.yml"])
        assert not missing, (
            f"skip gates set by NOTHING - the tests behind them run in no "
            f"environment: {missing}"
        )

    The check is textual on purpose: it asks "does this variable's name
    appear in any CI/automation file at all", which catches the deleted-job
    and renamed-variable failure modes with zero YAML parsing. A textual hit
    can still be a lie (a comment), so pair this with one real CI run where
    you confirm the gated tier's tests appear in the output count.
    """
    root = Path(root)
    corpus = ""
    matched_any = False
    for g in search_globs:
        for path in glob.glob(str(root / g), recursive=True):
            matched_any = True
            try:
                corpus += Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    if not matched_any:
        # No files matched - that is its own failure. An audit over nothing
        # passing silently would be exactly the vacuity it exists to catch.
        return [f"<no files matched {search_globs} under {root.resolve()}>"]
    return [g.env_var for g in gates if g.env_var not in corpus]


def selfcheck() -> bool:
    """Exercise the audit's three verdicts, including the vacuity guard.

    The third case is the one that matters: an audit whose globs match no
    files must FAIL, not pass quietly. A skip-gate audit that ran over an
    empty corpus and reported "nothing missing" is the exact vacuity these
    gates exist to catch.
    """
    import tempfile

    gates = [EnvGate("slow", "SLOW_TESTS", "the slow tier")]
    ok = True

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "ci").mkdir()

        (root / "ci" / "none.yml").write_text("jobs:\n  test:\n    run: pytest\n")
        missing = audit_skip_gates(gates, ["ci/*.yml"], root)
        if missing != ["SLOW_TESTS"]:
            print(f"[envgate] SELFCHECK FAILED: unset gate not reported: {missing}")
            ok = False

        (root / "ci" / "sets.yml").write_text("env:\n  SLOW_TESTS: 1\n")
        missing = audit_skip_gates(gates, ["ci/*.yml"], root)
        if missing != []:
            print(f"[envgate] SELFCHECK FAILED: set gate reported missing: {missing}")
            ok = False

        missing = audit_skip_gates(gates, ["nope/*.yml"], root)
        if not (len(missing) == 1 and "no files matched" in missing[0]):
            print(f"[envgate] SELFCHECK FAILED: empty corpus passed quietly: {missing}")
            ok = False

    import os as _os

    gate = EnvGate("slow", "ZZ_ENVGATE_SELFCHECK")
    _os.environ.pop("ZZ_ENVGATE_SELFCHECK", None)
    if gate.enabled:
        print("[envgate] SELFCHECK FAILED: gate enabled with no env var set")
        ok = False
    _os.environ["ZZ_ENVGATE_SELFCHECK"] = "1"
    if not gate.enabled:
        print("[envgate] SELFCHECK FAILED: gate disabled with env var set to 1")
        ok = False
    _os.environ.pop("ZZ_ENVGATE_SELFCHECK", None)

    if ok:
        print("[envgate] selfcheck ok: unset reported, set cleared, empty corpus refused")
    return ok


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    print(
        f"[envgate] unknown argument(s): {' '.join(argv)}\n"
        f"envgate is a library; its CLI exists to run --selfcheck.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
