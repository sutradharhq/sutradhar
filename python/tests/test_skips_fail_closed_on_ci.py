"""Class ratchet for B-66: no test in this suite can skip its way to green
on CI.

A skip is not a pass (2.9). Off CI a contributor without bash may skip a
module and is told why; on CI a skipped module reads as a green suite, which
is the check that could not run reporting that it passed. So every test
module that can skip must also say what CI does about it, by reading the CI
variable and failing there. The ratchet is textual and over-wide on purpose:
any skip spelling in a test file obliges that file, and a new one is caught
the day it is written, whether or not it ever skips.

Mutation: add `pytest.importorskip("tomllib")` to test_corpus.py - red.
"""
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
SKIP = re.compile(r"\bskipif\s*\(|\bpytest\.skip\s*\(|\bimportorskip\s*\(|"
                  r"\.skipTest\s*\(|@unittest\.skip")
FAILS_ON_CI = re.compile(r"""os\.environ\.get\(\s*["']CI["']""")


def test_every_module_that_can_skip_fails_instead_on_ci():
    own = Path(__file__).name
    skipping = sorted(p.name for p in TESTS.glob("test_*.py")
                      if p.name != own and SKIP.search(p.read_text()))
    # The suite has exactly one such module today; an empty list would mean
    # the pattern stopped matching, and the ratchet would pass vacuously.
    assert "test_examples.py" in skipping, skipping
    unguarded = [n for n in skipping
                 if not FAILS_ON_CI.search((TESTS / n).read_text())]
    assert not unguarded, (
        f"{unguarded} can skip and never fail on CI; read the CI variable "
        f"and fail there, as test_examples.py does (2.9, B-66)")
