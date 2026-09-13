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

Every assertion runs in BOTH invocation forms (R21-4). `python -m
sutradhar_guards.<module>` is how this repository's tests reach a module;
`python3 path/to/<module>.py` is how an adopter reaches one, because
`bootstrap.sh` copies files, not a package. The two forms load a module
differently - the second puts the file's own directory on `sys.path` and
nothing else - so a module that only works when `sutradhar_guards` is
importable passes one form and fails the other. Both worked when this was
written; only one was pinned.
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


#: The two ways a module is reached. `-m` is the package form this
#: repository's own tests and CI use; `path` is the copy-in form an adopter
#: uses after `bootstrap.sh`, run with the package deliberately NOT importable.
FORMS = ("-m", "path")


def _run(module: str, *args: str, form: str = "-m",
         cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if form == "-m":
        # PYTHONPATH is set explicitly rather than inherited. Running with
        # cwd=REPO_ROOT means the package is not importable from the working
        # directory, so a test that relied on the caller's exported PYTHONPATH
        # passed locally and failed in CI - the ambient environment was doing
        # work the test claimed to do itself.
        env["PYTHONPATH"] = os.pathsep.join(
            [str(PKG_PARENT), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(PKG_PARENT)]
        )
        argv = [sys.executable, "-m", f"sutradhar_guards.{module}", *args]
    elif form == "path":
        # The adopter's condition: a file, run by path, with nothing on the
        # path but its own directory. An inherited PYTHONPATH that happens to
        # reach `python/` would let a package-only import pass here and fail
        # in their tree, so it is removed rather than trusted.
        env.pop("PYTHONPATH", None)
        argv = [sys.executable, str(PKG_PARENT / "sutradhar_guards" / f"{module}.py"), *args]
    else:  # pragma: no cover - a typo in a parametrize list
        raise ValueError(f"unknown invocation form {form!r}; expected one of {FORMS}")
    return subprocess.run(
        argv,
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


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("module", MODULES)
def test_selfcheck_runs_and_says_so(module: str, form: str):
    proc = _run(module, "--selfcheck", form=form)
    assert proc.returncode == 0, (
        f"sutradhar_guards.{module} --selfcheck ({form} form) exited "
        f"{proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert module.replace("_", "-") in proc.stdout or module in proc.stdout, (
        f"sutradhar_guards.{module} --selfcheck ({form} form) exited 0 but "
        f"printed nothing naming itself. A silent pass cannot be told apart "
        f"from a check that never ran.\nstdout: {proc.stdout!r}"
    )


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("module", MODULES)
def test_unknown_flag_is_rejected(module: str, form: str):
    """The one that makes exit 0 mean something.

    If an unknown flag exits 0, then so does `--selfcheck`, for the same
    reason: nothing parsed it. Mutation-verify this by deleting a module's
    `__main__` block - this test must go red for that module.
    """
    proc = _run(module, UNKNOWN_FLAG, form=form)
    assert proc.returncode != 0, (
        f"sutradhar_guards.{module} {UNKNOWN_FLAG} ({form} form) exited 0. An "
        f"unrecognised flag was ignored, which means `--selfcheck` proves only "
        f"that the module imported - not that any check ran.\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("module", MODULES)
def test_no_import_warnings_on_cli_invocation(module: str, form: str):
    """`__init__` eagerly importing a submodule makes `python -m pkg.mod`
    emit a RuntimeWarning about unpredictable behaviour on every run. Noise
    on a guard's own stderr trains people to stop reading stderr."""
    proc = _run(module, "--selfcheck", form=form)
    assert "RuntimeWarning" not in proc.stderr, (
        f"sutradhar_guards.{module} ({form} form) emits a RuntimeWarning on "
        f"every CLI run:\n{proc.stderr}"
    )


# ── the shebang, where the kernel reads it ──────────────────────────────────
#
# R21-5. Six guards carried `#!/usr/bin/env python3` on line 3, under the
# two-line license header, where no loader reads it: a kernel honours `#!`
# only as the first two bytes of the file. Every documented invocation says
# `python3 <file>`, so nothing broke - the line claimed the file could be run
# directly, and the claim was false in six places and true in three. Marked
# executable and run as `./swallow_lint.py --selfcheck`, the round-20 copy was
# handed to a shell, which ran its docstring as commands ("Guard: flag
# exception handlers ...: command not found") and exited 2.

SHEBANG_DIRS = (
    REPO_ROOT / "python" / "sutradhar_guards",
    REPO_ROOT / "plugin" / "scripts",
    REPO_ROOT / "plugin" / "guards",
)


def _python_files_with_a_shebang() -> dict:
    """{path: 1-based line of the first `#!`} for every file that has one."""
    found = {}
    for root in SHEBANG_DIRS:
        for path in sorted(root.glob("*.py")):
            lines = path.read_text(encoding="utf-8").splitlines()
            at = next((n for n, line in enumerate(lines, 1)
                       if line.startswith("#!")), None)
            if at is not None:
                found[path] = at
    return found


def test_the_shebang_scan_has_something_to_read():
    """Guards the guard (3.6): a glob that matched nothing, or a tree with no
    shebang left in it, would pass the ratchet below over an empty dict."""
    assert all(root.is_dir() for root in SHEBANG_DIRS), SHEBANG_DIRS
    assert len(_python_files_with_a_shebang()) >= 3


def test_every_shebang_is_on_line_one():
    """A class ratchet over every `.py` in the three shipped directories, so a
    guard added next month with its header pasted above the shebang is
    refused the day it lands rather than found by reading."""
    misplaced = {
        str(path.relative_to(REPO_ROOT)): line
        for path, line in _python_files_with_a_shebang().items() if line != 1
    }
    assert not misplaced, (
        f"a shebang below line 1 is a comment, not an interpreter line: "
        f"{misplaced}. Put `#!/usr/bin/env python3` first and the license "
        f"header under it, then run `python3 plugin/sync_guards.py`."
    )


# ── nothing to read is not a pass ───────────────────────────────────────────
#
# R21-2. Three lints printed OK and exited 0 over a directory holding no
# Python file, so a CI step aimed at the wrong path was green on every run and
# had read nothing. The ratchet below does not keep a list of "the modules
# that scan a directory" - a list is what goes stale. It hands EVERY module
# only an empty directory, and runs it from inside that directory so no
# default path can find this repository instead. A module that takes no
# directory refuses the argument; one that does must refuse the empty scan.
# Either way, exit 0 or a line saying OK is the lie.
#
# Empty, and not "a README and no code": the first draft planted a README.md,
# and framework_shape - whose surface includes a top-level README - read it
# and correctly said OK over one file. A fixture a guard legitimately reads is
# not nothing to read. The no-Python-repository case lives in each lint's own
# tests, where "nothing" can be defined per guard.

#: Modules that exit 0 over a directory with nothing in it ON PURPOSE, each
#: with the line it prints instead of OK and the reason. The exemption test
#: fails the day an entry stops being true, so this cannot quietly become an
#: ignore list.
EMPTY_SCAN_EXEMPT = {
    "budget": (
        "no budgets declared under",
        "a design-notes directory that declares no budget has promised "
        "nothing, and bootstrap.sh ships one holding only TEMPLATE.md; "
        "refusing it would open every fresh adopter's CI red over a promise "
        "they have not made. It names the directory and says nothing was "
        "declared, and it never prints OK.",
    ),
}


def _says_ok(text: str) -> bool:
    """True when OK appears as a word. `selfcheck ok` is lowercase and is the
    guard proving itself, not a verdict on the directory."""
    return any(token.strip("()[]{}:;,.!-'\"") == "OK" for token in text.split())


def _nothing_to_read(tmp_path: Path) -> Path:
    tree = tmp_path / "nothing-to-read"
    tree.mkdir()
    assert not any(tree.iterdir()), "the fixture must be empty to mean nothing"
    return tree


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize(
    "module", [m for m in MODULES if m not in EMPTY_SCAN_EXEMPT])
def test_a_directory_with_nothing_to_read_is_never_ok(module: str, form: str,
                                                      tmp_path: Path):
    tree = _nothing_to_read(tmp_path)
    proc = _run(module, str(tree), form=form, cwd=tree)
    said = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        f"sutradhar_guards.{module} ({form} form) exited 0 when handed only a "
        f"directory with nothing in it to read. That is a pass for a check "
        f"that never ran (2.9): refuse it with 2 and say nothing was scanned, "
        f"or add it to EMPTY_SCAN_EXEMPT with the line it prints and why.\n"
        f"{said}"
    )
    assert not _says_ok(said), (
        f"sutradhar_guards.{module} ({form} form) printed OK over a directory "
        f"with nothing in it to read:\n{said}"
    )


@pytest.mark.parametrize("module", sorted(EMPTY_SCAN_EXEMPT))
def test_every_empty_scan_exemption_is_still_true(module: str, tmp_path: Path):
    line, reason = EMPTY_SCAN_EXEMPT[module]
    assert module in MODULES, f"{module} is exempt and no longer exists"
    assert len(reason) > 80, f"{module}'s exemption carries no real reason"
    tree = _nothing_to_read(tmp_path)
    proc = _run(module, str(tree), form="path", cwd=tree)
    said = proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        f"{module} now refuses an empty directory (exit {proc.returncode}); "
        f"delete its EMPTY_SCAN_EXEMPT entry so the ratchet holds it.\n{said}"
    )
    assert line in said, f"{module} exits 0 without saying {line!r}:\n{said}"
    assert not _says_ok(said), f"{module} printed OK over nothing:\n{said}"
