# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""A stage that touches another agent's path is refused (7.3, register B-16).

7.3 carried the manifest sentence from round 17 and nothing enforced it.
These are the tests that make the enforcement real, and the load-bearing
ones are the three that prove the guard can produce each of its three
different answers - refuse, allow, and "I did not run" - because a guard
that can only ever say one of them is decoration whichever one it says.

The blinding test is the wiring half: it makes the path from "the matcher
went vacuous" to "the CLI goes red" itself a test, exactly as
`test_detectors_and_wiring.py` does for the two older lints.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import ownership_lint as ol  # noqa: E402
from sutradhar_guards.ownership_lint import (  # noqa: E402
    OwnershipError,
    audit,
    main,
    owners_of,
    parse_manifest,
)

MANIFEST = (
    "# two agents, one tree\n"
    "alice: python/guards/* README.md\n"
    "bob:   js/\n"
)


def _repo(tmp_path: Path, manifest: str = MANIFEST) -> Path:
    root = tmp_path / "tree"
    root.mkdir()
    (root / ol.DEFAULT_MANIFEST).write_text(manifest, encoding="utf-8")
    return root


# ── the three answers ───────────────────────────────────────────────────────

def test_a_path_owned_by_another_owner_is_refused(tmp_path, capsys):
    root = _repo(tmp_path)
    rc = main(["--owner", "bob", "--repo", str(root), "python/guards/a.py"])
    assert rc == 1
    said = capsys.readouterr()
    assert "python/guards/a.py" in said.err
    assert "alice" in said.err, (
        "a refusal that does not name the owner leaves the reader with "
        "nobody to hand the file back to")


def test_the_owners_own_path_is_allowed(tmp_path):
    root = _repo(tmp_path)
    assert main(["--owner", "alice", "--repo", str(root),
                 "python/guards/a.py"]) == 0


def test_an_unowned_path_is_allowed_and_counted(tmp_path, capsys):
    """Allowed is easy; counted is the part that rots. An exclusion the
    operator cannot see is the same class of silence 6.7 is about."""
    root = _repo(tmp_path)
    rc = main(["--owner", "alice", "--repo", str(root), "docs/notes.md"])
    assert rc == 0
    assert "1 unowned" in capsys.readouterr().out


def test_a_missing_manifest_is_an_instrument_condition_not_a_violation(
        tmp_path, capsys):
    """Opt-in, and it must SAY it is not measuring. A silent 0 here cannot
    be told from a clean stage, which is the empty-200 lie (6.6)."""
    root = tmp_path / "bare"
    root.mkdir()
    rc = main(["--owner", "bob", "--repo", str(root), "python/guards/a.py"])
    assert rc == 0
    assert "no ownership manifest" in capsys.readouterr().out


def test_a_manifest_declaring_no_owner_is_a_refusal_not_a_pass(tmp_path):
    """2.9: an empty manifest and a satisfied one look identical from here."""
    root = _repo(tmp_path, "# nobody has declared anything yet\n")
    assert main(["--owner", "bob", "--repo", str(root), "a.py"]) == 2


# ── the manifest is refused, never half-read ────────────────────────────────

@pytest.mark.parametrize("bad", [
    "alice python/guards/*\n",          # no colon at all
    ": python/guards/*\n",              # globs with nobody in front of them
    "carol:\n",                         # an owner who owns nothing
    "alice: python/guards/*\nbob\n",    # a good row followed by a bad one
])
def test_an_unreadable_manifest_row_is_refused(bad):
    """The row that cannot be read must not be spelled the same as no row.
    An owner dropped by a typo owns nothing, and every path they hold then
    reads as unowned - the guard reporting green over the exact collision
    it exists to refuse."""
    with pytest.raises(OwnershipError):
        parse_manifest(bad, "<test>")


def test_a_repeated_owner_accumulates_rather_than_replacing():
    m = parse_manifest("alice: a/*\nalice: b/*\n", "<test>")
    assert sorted(m["alice"]) == ["a/*", "b/*"]


def test_comments_and_blank_lines_are_not_owners():
    assert sorted(parse_manifest(MANIFEST, "<test>")) == ["alice", "bob"]


# ── matching, stated rather than discovered ─────────────────────────────────

def test_a_trailing_slash_is_the_whole_subtree():
    m = parse_manifest(MANIFEST, "<test>")
    assert owners_of("js/probe/core.mjs", m) == ["bob"]


def test_an_exact_filename_does_not_claim_its_neighbour():
    m = parse_manifest(MANIFEST, "<test>")
    assert owners_of("README.md", m) == ["alice"]
    assert owners_of("README.md.bak", m) == []


def test_a_leading_dot_slash_is_the_same_path():
    m = parse_manifest(MANIFEST, "<test>")
    assert owners_of("./python/guards/a.py", m) == ["alice"]


def test_a_shared_claim_is_allowed_and_reported(tmp_path, capsys):
    """Two agents who both believe they own a file collide exactly the way
    B-16 did. Resolving that silently in favour of whoever ran first is the
    behaviour, not the fix."""
    root = _repo(tmp_path, "alice: shared/*\nbob: shared/*\n")
    rc = main(["--owner", "alice", "--repo", str(root), "shared/x.py"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "shared claim" in out and "bob" in out


# ── the real seam: the stage itself (2.3) ───────────────────────────────────

def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=T",
         "-c", "user.email=t@example.invalid", *args],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (args, proc.stderr)


def test_with_no_paths_named_it_reads_the_index(tmp_path):
    """The default path is `git diff --cached --name-only`, and a test that
    only ever passes paths on the command line would never touch it."""
    root = _repo(tmp_path)
    _git(root, "init", "-q", "-b", "main")
    (root / "python").mkdir()
    (root / "python" / "guards").mkdir()
    (root / "python" / "guards" / "a.py").write_text("x = 1\n")
    (root / "unowned.txt").write_text("hello\n")

    _git(root, "add", "unowned.txt")
    assert main(["--owner", "bob", "--repo", str(root)]) == 0

    _git(root, "add", "python/guards/a.py")
    assert main(["--owner", "bob", "--repo", str(root)]) == 1
    assert main(["--owner", "alice", "--repo", str(root)]) == 0


def test_git_failing_is_reported_as_the_guards_failure(tmp_path, capsys):
    """6.8: an error branch must say WHOSE failure it is. Outside a
    repository this guard has learned nothing about anybody's stage, and
    must not be able to say otherwise."""
    root = _repo(tmp_path)
    rc = main(["--owner", "bob", "--repo", str(root)])
    assert rc == 2
    assert "git" in capsys.readouterr().err


# ── the CLI's own honesty ───────────────────────────────────────────────────

def test_no_owner_named_is_not_a_pass(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(ol.OWNER_ENV, raising=False)
    root = _repo(tmp_path)
    assert main(["--repo", str(root), "a.py"]) == 2
    assert "nothing was checked" in capsys.readouterr().err


def test_the_owner_can_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(ol.OWNER_ENV, "bob")
    root = _repo(tmp_path)
    assert main(["--repo", str(root), "python/guards/a.py"]) == 1


def test_an_unknown_flag_exits_two(capsys):
    assert main(["--owner", "bob", "--not-a-flag"]) == 2
    assert "unknown flag" in capsys.readouterr().err


def test_a_flag_missing_its_value_exits_two():
    assert main(["--owner"]) == 2
    assert main(["--owner", "bob", "--manifest"]) == 2
    assert main(["--owner", "bob", "--repo"]) == 2


def test_the_known_flag_set_is_pinned_by_hand():
    """R19-4: a configuration list parametrised over itself cannot see a
    deletion. Written out here so removing `--manifest` from the parser
    fails this line rather than quietly deleting the case that would
    object."""
    assert ol._KNOWN_FLAGS == {
        "--owner", "--manifest", "--repo", "--selfcheck", "--help", "-h",
    }


@pytest.mark.parametrize("flag", ["--owner", "--manifest", "--repo"])
def test_every_value_taking_flag_is_actually_parsed(flag, tmp_path):
    """Presence in the set is not reachability (3.6): each flag is driven
    through the parser and must not come back as `unknown flag` (exit 2 with
    a value present would mean the branch is gone)."""
    root = _repo(tmp_path)
    args = {"--owner": "alice", "--manifest": str(root / ol.DEFAULT_MANIFEST),
            "--repo": str(root)}
    argv = ["--owner", "alice", "--repo", str(root)]
    if flag not in ("--owner", "--repo"):
        argv += [flag, args[flag]]
    argv.append("docs/notes.md")
    assert main(argv) == 0


# ── selfcheck and its wiring ────────────────────────────────────────────────

def test_selfcheck_passes():
    assert ol.selfcheck()


def test_a_blinded_matcher_fails_the_cli(tmp_path, monkeypatch):
    """The wiring: from "the matcher went vacuous" to "the CLI goes red".

    Sanity first, so the red below is a change and not the only state this
    input has ever produced."""
    root = _repo(tmp_path)
    assert main(["--owner", "alice", "--repo", str(root), "docs/notes.md"]) == 0
    monkeypatch.setattr(ol, "owners_of", lambda *a, **k: [])
    assert main(["--owner", "alice", "--repo", str(root), "docs/notes.md"]) == 1
