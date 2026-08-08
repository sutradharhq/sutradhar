"""The repo's own declared envelopes, enforced.

Doctrine 1.1: the design note names the N; this file makes the number
binding. Nothing here hand-picks a comfortable size - `b.n` IS the figure
in docs/design/lint-scan.md, so raising the design N automatically makes
this test harder and lowering it is a diff someone reviews.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards.budget import budget
from sutradhar_guards.swallow_lint import check_source

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design"

SAMPLE = '''
import os

def handler(payload):
    try:
        return compute(payload)
    except Exception:
        return {}

def compute(payload):
    return {"value": payload}
''' * 6


def test_lint_scan_holds_its_declared_envelope():
    with budget("lint-scan", root=DESIGN) as b:
        for _ in range(b.n):
            check_source(SAMPLE, set())
