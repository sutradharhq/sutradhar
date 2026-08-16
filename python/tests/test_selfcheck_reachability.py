# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""Every module's --selfcheck must be REACHABLE and its exit code must MEAN
something.

Scar (round 4): `python -m sutradhar_guards.envgate --selfcheck` exited 0 for
five of ten modules that had no `__main__` block at all. The flag was
ignored, the module imported, and the interpreter exited 0. A weekly review
read those five zeros as "selfcheck passed" and reported the suite green.

The exit code was not lying about the check. There was no check. That is the
`verify_guard` thesis - a guard never shown to fail is decoration - occurring
inside the guard suite itself, and doctrine 6.4: prove the instrument is
valid before trusting what it reports.

Two assertions per module, and the SECOND is the load-bearing one:

  1. `--selfcheck` exits 0 and prints a line naming the module. Silence is
     indistinguishable from a check that never ran.
  2. An unknown flag exits NON-zero. Without this, `exit 0` only proves the
     import succeeded. This is what makes assertion 1 informative.

A class ratchet over `pkgutil.iter_modules`, not a point test per module
(doctrine 2.1), so any module added later is covered the day it lands.
"""
import os
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

import sutradhar_guards

# `python/` - the directory the package is importable FROM.
PKG_PARENT = Path(sutradhar_guards.__path__[0]).parent
# Repo root, not `python/`: several tools scan the tree relative to cwd, so
# running them from the package directory exercises a different code path
# than the one CI and humans use.
REPO_ROOT = PKG_PARENT.parent
UNKNOWN_FLAG = "--zzz-not-a-real-flag"

MODULES = sorted(info.name for info in pkgutil.iter_modules(sutradhar_guards.__path__))


def _run(module: str, *args: str) -> subprocess.CompletedProcess:
    # PYTHONPATH is set explicitly rather than inherited. Running with
    # cwd=REPO_ROOT means the package is not importable from the working
    # directory, so a test that relied on the caller's exported PYTHONPATH
    # passed locally and failed in CI - the ambient environment was doing
    # work the test claimed to do itself.
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PKG_PARENT), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(PKG_PARENT)]
    )
    return subprocess.run(
        [sys.executable, "-m", f"sutradhar_guards.{module}", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=180,
    )


def test_the_package_actually_has_modules():
    """Guards the guard: if iter_modules returned nothing, every
    parametrised test below would vacuously pass (doctrine 3.6)."""
    assert len(MODULES) >= 8, f"expected the full tool set, found {MODULES}"


@pytest.mark.parametrize("module", MODULES)
def test_selfcheck_runs_and_says_so(module: str):
    proc = _run(module, "--selfcheck")
    assert proc.returncode == 0, (
        f"sutradhar_guards.{module} --selfcheck exited {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert module.replace("_", "-") in proc.stdout or module in proc.stdout, (
        f"sutradhar_guards.{module} --selfcheck exited 0 but printed nothing "
        f"naming itself. A silent pass cannot be told apart from a check that "
        f"never ran.\nstdout: {proc.stdout!r}"
    )


@pytest.mark.parametrize("module", MODULES)
def test_unknown_flag_is_rejected(module: str):
    """The one that makes exit 0 mean something.

    If an unknown flag exits 0, then so does `--selfcheck`, for the same
    reason: nothing parsed it. Mutation-verify this by deleting a module's
    `__main__` block - this test must go red for that module.
    """
    proc = _run(module, UNKNOWN_FLAG)
    assert proc.returncode != 0, (
        f"sutradhar_guards.{module} {UNKNOWN_FLAG} exited 0. An unrecognised "
        f"flag was ignored, which means `--selfcheck` proves only that the "
        f"module imported - not that any check ran.\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )


@pytest.mark.parametrize("module", MODULES)
def test_no_import_warnings_on_cli_invocation(module: str):
    """`__init__` eagerly importing a submodule makes `python -m pkg.mod`
    emit a RuntimeWarning about unpredictable behaviour on every run. Noise
    on a guard's own stderr trains people to stop reading stderr."""
    proc = _run(module, "--selfcheck")
    assert "RuntimeWarning" not in proc.stderr, (
        f"sutradhar_guards.{module} emits a RuntimeWarning on every CLI run:\n"
        f"{proc.stderr}"
    )
