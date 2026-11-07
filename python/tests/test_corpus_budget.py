"""The repo's own declared envelope for the defect-corpus scorer, enforced.

Doctrine 1.1: the design note names the N; this file makes the number
binding. Nothing here hand-picks a comfortable size - `b.n` IS the figure
in docs/design/defect-corpus.md, so raising the design N automatically
makes this test harder and lowering it is a diff someone reviews.

This test asserts genuinely, not by mention (R22-4): it builds the full
declared N of twin pairs and scores them through the real `main()`, so
the wall-clock and heap ceilings in the `with` block measure the work,
and a breach raises instead of passing.
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sutradhar_guards import corpus
from sutradhar_guards.budget import budget

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design"

SWALLOW = (
    "def latest_total(store):\n"
    "    try:\n"
    "        return store.fetch()\n"
    "    except Exception:\n"
    "        return {}\n"
)
PLAIN = (
    "def latest_total(store):\n"
    "    return store.fetch()\n"
)


def test_defect_corpus_holds_its_declared_envelope(tmp_path):
    """Mutation: halving the synthetic case count still passes the gate
    (the id is mentioned either way), so the count must come from `b.n`
    itself - and widening the ceilings in the note is the only way to move
    a breach, never an edit here."""
    doctrine = tmp_path / "DOCTRINE.md"
    doctrine.write_text("**2.7 exceptions\n")
    with budget("defect-corpus", root=DESIGN) as b:
        root = tmp_path / "corpus"
        cases = root / "cases"
        cases.mkdir(parents=True)
        for i in range(b.n):
            (cases / f"case-{i:02d}.md").write_text(
                f"---\ncase: case-{i:02d}\nguard: swallow_lint\nrule: 2.7\n"
                f"scar: distribution\nscar_argument: envelope probe\n"
                f"expected: caught\n---\n"
                f"\n## defective\n\n```python path=app/units.py\n{SWALLOW}```\n"
                f"\n## clean\n\n```python path=app/units.py\n{PLAIN}```\n",
                encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = corpus.main([str(root), "--doctrine", str(doctrine)])
        assert code == 0, (
            f"the full declared corpus did not score clean:\n{out.getvalue()}"
            f"\n{err.getvalue()}"
        )
