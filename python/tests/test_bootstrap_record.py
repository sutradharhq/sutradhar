# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""`bootstrap.sh` leaves a record, and `--check` reads it (R21-6).

Two adopting trees ran copies of a guard that were missing a detection this
repository had added weeks earlier, and nothing could tell them. The
CHANGELOG told copy-in users to upgrade "by diffing against the tag they
took", and no file anywhere said which tag that was.

Every test here drives `bash bootstrap.sh` as a subprocess into a fresh
`git init` directory - the seam an adopter uses (2.3). A newer checkout is
simulated by copying the parts of this one that bootstrap reads, changing one
guard and bumping the release, because that is exactly what pulling a later
Sutradhar does to the files `--check` compares.

The four answers are asserted in pairs, because a check that called
everything stale, or nothing, would pass a one-sided test (6.7): an
untouched copy is current, a copy behind a newer checkout is stale, a copy
changed here is modified locally - never stale, since that edit was the
adopter's to make - and a deleted one is missing.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

import sutradhar_guards

REPO_ROOT = Path(sutradhar_guards.__path__[0]).parent.parent
RECORD = ".sutradhar-bootstrap"
VERSION = sutradhar_guards.__version__

#: What bootstrap.sh reads from a checkout. Copied explicitly rather than the
#: whole tree, which in a maintainer's clone can hold worktrees and caches.
_CHECKOUT_FILES = ("bootstrap.sh", "DOCTRINE.md", "NOTICE")
_CHECKOUT_DIRS = ("python/sutradhar_guards", "js", "ci", "agent", "docs/templates")


def bootstrap(*args, checkout: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(checkout / "bootstrap.sh"), *map(str, args)],
        capture_output=True, text=True, timeout=180,
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(target: Path) -> dict:
    """{dest: (sha256, release, source)} from the record, read independently
    of bootstrap.sh so the test does not trust the parser it is testing."""
    out = {}
    for line in (target / RECORD).read_text().splitlines():
        cells = line.split("\t")
        if cells[0] == "file":
            assert len(cells) == 5, f"malformed record row: {line!r}"
            out[cells[3]] = (cells[1], cells[2], cells[4])
    return out


def state_of(output: str, dest: str) -> str:
    """The state word printed for one file, e.g. `stale`."""
    for line in output.splitlines():
        if f" {dest} (taken from release " in line:
            return line.split(f" {dest} ", 1)[0].strip()
    raise AssertionError(f"{dest} is not in the --check report:\n{output}")


@pytest.fixture
def adopter(tmp_path: Path) -> Path:
    target = tmp_path / "adopter"
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True,
                   capture_output=True, text=True)
    return target.resolve()


def newer_checkout(tmp_path: Path, change: str, version: str = "9.9.9") -> Path:
    newer = tmp_path / "newer-sutradhar"
    for rel in _CHECKOUT_FILES:
        (newer / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, newer / rel)
    for rel in _CHECKOUT_DIRS:
        shutil.copytree(REPO_ROOT / rel, newer / rel,
                        ignore=shutil.ignore_patterns("__pycache__"))
    guard = newer / change
    guard.write_text(guard.read_text() + "\n# a detection added after the copy was taken\n")
    init = newer / "python" / "sutradhar_guards" / "__init__.py"
    before = init.read_text()
    init.write_text(before.replace(f'__version__ = "{VERSION}"', f'__version__ = "{version}"'))
    assert init.read_text() != before, "the simulated checkout kept the old release"
    return newer.resolve()


# ── the record ──────────────────────────────────────────────────────────────

def test_bootstrap_records_every_file_it_copies(adopter: Path):
    proc = bootstrap(adopter)
    assert proc.returncode == 0, proc.stderr
    copied = sorted(line.split("copied:", 1)[1].strip()
                    for line in proc.stdout.splitlines() if "copied:" in line)
    assert len(copied) >= 20, "bootstrap copied almost nothing - vacuous"
    recorded = rows(adopter)
    assert sorted(recorded) == copied
    for dest, (digest, release, source) in recorded.items():
        assert digest == sha(adopter / dest) == sha(REPO_ROOT / source), dest
        # The release is read by sed in bash; this pins it to the package's
        # own __version__, so a reformatted __init__.py cannot silently
        # record "unknown" for every file.
        assert release == VERSION, dest


def test_rerunning_bootstrap_keeps_the_rows_it_did_not_replace(adopter: Path):
    assert bootstrap(adopter, "--layers", "python").returncode == 0
    first = rows(adopter)
    assert bootstrap(adopter, "--layers", "docs").returncode == 0
    second = rows(adopter)
    assert set(first) < set(second)
    assert all(second[dest] == first[dest] for dest in first)


def test_an_existing_copy_is_recorded_only_when_it_is_provably_this_release(adopter: Path):
    (adopter / "scripts").mkdir()
    shutil.copy2(REPO_ROOT / "python/sutradhar_guards/budget.py", adopter / "scripts/budget.py")
    (adopter / "scripts/rounds.py").write_text("# somebody's own rounds.py\n")
    proc = bootstrap(adopter, "--layers", "python")
    assert proc.returncode == 0, proc.stderr
    recorded = rows(adopter)
    assert recorded["scripts/budget.py"][1] == VERSION
    assert "scripts/rounds.py" not in recorded
    assert "1 existing file(s) differ from this checkout" in proc.stdout
    assert f"--track {adopter}" in proc.stdout


# ── --check: the four answers ───────────────────────────────────────────────

def test_a_fresh_tree_is_current_and_names_the_release_it_took(adopter: Path):
    bootstrap(adopter)
    proc = bootstrap("--check", adopter)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    n = len(rows(adopter))
    assert f"{n} current, 0 stale, 0 modified locally, 0 missing" in proc.stdout
    assert f"this tree took release(s) {VERSION}; this checkout is release {VERSION}" in proc.stdout


def test_a_newer_checkout_tells_stale_from_modified_locally(adopter: Path, tmp_path: Path):
    """The pair in one tree: the guard the newer checkout changed is stale,
    the guard the adopter changed is modified locally, and neither is
    mistaken for the other."""
    bootstrap(adopter)
    edited = adopter / "scripts" / "swallow_lint.py"
    edited.write_text(edited.read_text() + "\n# our own change\n")
    newer = newer_checkout(tmp_path, "python/sutradhar_guards/interpolation_lint.py")
    proc = bootstrap("--check", adopter, checkout=newer)
    out = proc.stdout
    assert proc.returncode == 1, out + proc.stderr
    assert state_of(out, "scripts/interpolation_lint.py") == "stale"
    assert state_of(out, "scripts/swallow_lint.py") == "modified locally"
    assert state_of(out, "scripts/budget.py") == "current"
    n = len(rows(adopter))
    assert f"{n - 2} current, 1 stale, 1 modified locally, 0 missing" in out
    assert f"took release(s) {VERSION}; this checkout is release 9.9.9" in out
    assert (f"diff {adopter}/scripts/interpolation_lint.py "
            f"{newer}/python/sutradhar_guards/interpolation_lint.py") in out


def test_a_copy_changed_here_is_reported_and_never_fails(adopter: Path):
    bootstrap(adopter)
    edited = adopter / "scripts" / "swallow_lint.py"
    edited.write_text(edited.read_text() + "\n# our own change\n")
    proc = bootstrap("--check", adopter)
    assert proc.returncode == 0, proc.stdout
    assert state_of(proc.stdout, "scripts/swallow_lint.py") == "modified locally"


def test_a_deleted_copy_is_missing_and_never_fails(adopter: Path):
    bootstrap(adopter)
    (adopter / "scripts" / "obsgate.py").unlink()
    proc = bootstrap("--check", adopter)
    assert proc.returncode == 0, proc.stdout
    assert state_of(proc.stdout, "scripts/obsgate.py") == "missing"


# ── a tree with no record, and starting one ─────────────────────────────────

def test_an_untracked_tree_is_not_red_and_gets_the_exact_command(adopter: Path):
    bootstrap(adopter)
    (adopter / RECORD).unlink()
    proc = bootstrap("--check", adopter)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "not tracked" in proc.stdout
    assert f"bash {REPO_ROOT.resolve()}/bootstrap.sh --track {adopter}" in proc.stdout


def test_track_records_what_is_there_and_check_can_then_see_it_fall_behind(adopter: Path):
    bootstrap(adopter)
    (adopter / RECORD).unlink()
    older = adopter / "scripts" / "budget.py"
    older.write_text(older.read_text() + "\n# an older copy, or an edit - nobody can tell\n")
    proc = bootstrap("--track", adopter)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    recorded = rows(adopter)
    assert recorded["scripts/budget.py"][1] == "unknown"
    assert recorded["scripts/swallow_lint.py"][1] == VERSION
    check = bootstrap("--check", adopter)
    assert check.returncode == 1, check.stdout
    assert state_of(check.stdout, "scripts/budget.py") == "stale"
    assert state_of(check.stdout, "scripts/swallow_lint.py") == "current"


# ── what --check refuses (2.9) ──────────────────────────────────────────────

def test_check_refuses_a_target_that_is_not_a_directory(tmp_path: Path):
    proc = bootstrap("--check", tmp_path / "nope")
    assert proc.returncode == 2, proc.stdout + proc.stderr


@pytest.mark.parametrize("body,why", [
    ("# a header and nothing else\n", "lists no file"),
    ("file\tnot-a-hash\t0.5.2\tscripts/x.py\tpython/sutradhar_guards/x.py\n", "malformed"),
    ("somethingelse\tx\n", "not a record row"),
])
def test_check_refuses_a_record_it_cannot_read(adopter: Path, body: str, why: str):
    """A row skipped because it could not be parsed is a file never checked,
    and an empty record reads exactly like a tree with nothing behind."""
    (adopter / RECORD).write_text(body)
    proc = bootstrap("--check", adopter)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert why in proc.stderr
