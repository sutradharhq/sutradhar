# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
#!/usr/bin/env python3
"""Guard: the framework must not start speaking an adopter's business domain.

``framework_only.py`` gates the promise "a framework, not a product" along
two axes that cannot be fudged - an import list and the presence of a
manifest. Round 18 found the same promise broken along an axis neither of
them can see. The guards had come to speak one adopter's domain:
``claim_check.py`` cited a "regulator-facing document", witnessed
kilowatt-hours beside rupees, asserted on "Losses improved to 84.5%" in its
own selfcheck, and the worked example was a meter-billing app. Every one of
those files imported stdlib only and declared no dependency. The gate was
green and the promise was broken.

R18-5 was found by hand, by building a term-frequency vocabulary of the
private tree and testing this one against it. This module is that finding
turned into a mechanism, in three checks with three different reaches -
stated separately because two of them are floors and one of them is not
shipped-and-automatic at all.

**This gate does not decide what counts as "product code" or "domain
code".** That is the ungameable trap ``framework_only``'s docstring names,
and ``budget.py`` warns about: a definition of "product" is either noisy or
trivially satisfied. So this notices, it does not judge. Check 1 counts one
mechanical thing - a numeric literal immediately followed by a unit the
framework does not measure in, and a currency symbol - and hands every hit
to a person. Whether a hit is a leak or a capability is a HUMAN call, and
the place that call is recorded is the baseline's reason column, which is
required and cannot be auto-generated.

Check 1 - domain units and currency in the framework surface (SHIPPED)
----------------------------------------------------------------------
The line this encodes: **engineering units are the framework's own subject;
domain units belong to whatever the adopter measures.** Milliseconds, bytes,
megabytes, percent, seconds and requests-per-second are the framework's
vocabulary - it declares budgets in them and it always will (``_ENGINEERING_
UNITS``). Kilowatt-hours, barrels, tonnes, acres, hectares, bushels,
patients, beds and currency amounts are somebody's business
(``_DOMAIN_UNITS``, deliberately spanning several industries so this is a
framework check and not a detector for one adopter).

Backed by a baseline file the way ``swallow_lint`` is, so today's legitimate
entries are banked and a NEW one fails. **Every banked entry carries a
one-line reason, and an entry with no reason is refused** - not skipped, not
passed. A baseline row without a reason is an ignore-list row with better
punctuation, and this is the guard whose entire subject is a judgement
somebody has to make out loud.

There is no ``--update-baseline``. Banking here is an act of writing a
sentence, and a flag that banks a finding without one is the reflexive
escape R18-1 was filed to remove.

**Surface scope**: what ships and what teaches - the guards, their tests,
``examples/``, ``js/``, ``plugin/``, the top-level ``README.md``,
``DOCTRINE.md``, ``SECURITY.md`` and ``docs/``.

**``docs/rounds/`` and ``CHANGELOG.md`` are exempt, and the exemption is the
point.** A round record must be free to name the term it removed - round 18's
record says "``meter`` came back at 3,688 occurrences there and 12 here", and
a gate that refused that sentence would teach people to describe incidents
vaguely, which is the opposite of what the record is for. That is the
difference between a RECORD and a LEAK: the record names the term as
something removed, in a document that exists to say so. The same asymmetry
is already in this repository, in ``test_stable_keys.py``, which judges only
code in shipped documents and exempts round records for the same reason.

Check 2 - ``--against <corpus>`` (NOT shipped as a gate; see below)
-------------------------------------------------------------------
The honest framing is that **check 1 cannot find an ordinary business
noun.** Nothing self-contained can tell ``device`` (fine) from ``meter`` (a
leak): the signal does not exist inside this repository at all. It exists
only relative to a corpus. So ``--against`` takes a path to a tree, builds
its term frequency, and reports the terms that are central THERE and present
HERE, ranked by centrality there. It needs a corpus the public repository
does not have, it is for the maintainer to run before publishing, it prints
a ranked list for a person to read rather than a verdict, and **check 1
alone is not sufficient**. It is never run in CI.

Check 3 - ``--diff <ref>`` (the entry gate)
--------------------------------------------
Check 1 over ADDED lines only, so the gate is about what is entering rather
than a re-litigation of what is already banked. This is the mode the
pre-commit hook uses: ``--diff HEAD`` gates the working tree about to be
committed.

Usage:
    python framework_shape.py .                       # gate the repo
    python framework_shape.py . --baseline b.json
    python framework_shape.py . --diff origin/main    # added lines only
    python framework_shape.py . --against ../private  # maintainer report
    python framework_shape.py --selfcheck

Exit 0 clean, 1 a finding (or a banked entry that is no longer found), 2 the
check could not run - an unknown flag, a missing tree, a baseline that
cannot be read, a baseline row with no reason. 2 is not a pass: "could not
measure" and "did not fail" are different answers (2.9).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# ── the two vocabularies ────────────────────────────────────────────────────

#: The framework's OWN subject. It declares budgets in these and always
#: will, so a number in front of one of them is this repository talking
#: about itself. Listed rather than inferred: an allowlist that is written
#: down can be argued with, and one that is derived from "everything not in
#: the other list" silently grows whenever somebody adds a word.
_ENGINEERING_UNITS = frozenset({
    # time
    "ns", "us", "ms", "s", "sec", "secs", "second", "seconds",
    "min", "mins", "minute", "minutes", "h", "hr", "hrs", "hour", "hours",
    "day", "days", "week", "weeks", "month", "months", "year", "years",
    # size
    "b", "kb", "mb", "gb", "tb", "kib", "mib", "gib",
    "byte", "bytes", "bit", "bits", "char", "chars",
    # rate and ratio
    "rps", "qps", "x", "px", "em", "rem", "fps", "hz", "khz",
    # things a program counts
    "req", "reqs", "request", "requests", "row", "rows", "file", "files",
    "line", "lines", "call", "calls", "test", "tests", "commit", "commits",
    "entity", "entities", "user", "users", "session", "sessions",
    "record", "records", "item", "items", "case", "cases", "run", "runs",
    "round", "rounds", "guard", "guards", "module", "modules",
})

#: Somebody's business. Several industries on purpose: a list that was only
#: energy would be a detector for one adopter, and this is a framework
#: check. The value is the industry, so the message can say WHOSE domain the
#: literal came from rather than only that it is not ours.
_DOMAIN_UNITS = {
    # energy and utilities
    "kwh": "energy", "mwh": "energy", "gwh": "energy", "twh": "energy",
    "kw": "energy", "mw": "energy", "gw": "energy",
    "kva": "energy", "mva": "energy",
    "therm": "energy", "therms": "energy",
    "btu": "energy", "mmbtu": "energy",
    # oil and gas
    "barrel": "oil and gas", "barrels": "oil and gas",
    "bbl": "oil and gas", "bbls": "oil and gas",
    "bpd": "oil and gas", "boe": "oil and gas",
    # agriculture and land
    "acre": "agriculture", "acres": "agriculture",
    "hectare": "agriculture", "hectares": "agriculture",
    "bushel": "agriculture", "bushels": "agriculture",
    "tonne": "agriculture", "tonnes": "agriculture",
    "ton": "agriculture", "tons": "agriculture",
    "quintal": "agriculture", "quintals": "agriculture",
    # healthcare
    "patient": "healthcare", "patients": "healthcare",
    "bed": "healthcare", "beds": "healthcare",
    "dose": "healthcare", "doses": "healthcare",
    "admission": "healthcare", "admissions": "healthcare",
    # freight and retail
    "teu": "freight", "pallet": "freight", "pallets": "freight",
    "sku": "retail", "skus": "retail",
    "sqft": "real estate",
    # money, as a magnitude or a code
    "lakh": "currency", "lakhs": "currency",
    "crore": "currency", "crores": "currency", "cr": "currency",
    "rs": "currency", "rupee": "currency", "rupees": "currency",
    "dollar": "currency", "dollars": "currency",
    "cent": "currency", "cents": "currency", "paise": "currency",
    "inr": "currency", "usd": "currency", "eur": "currency",
    "gbp": "currency", "jpy": "currency", "cad": "currency",
    "aud": "currency",
}

#: Written as escapes, with the name beside each, so this file does not
#: itself carry a currency symbol for its own gate to find. The alternative
#: - banking four entries per copy of this file - would spend the baseline's
#: reason column on the instrument instead of on the repository. The
#: selfcheck proves every symbol here is actually detected, so the escaping
#: cannot quietly blind the list.
_CURRENCY_SYMBOLS = (
    "\u20b9",  # rupee
    "\u20ac",  # euro
    "\u00a3",  # pound
    "\u00a5",  # yen
)

#: A number, western or Indian grouping, not preceded by a word character or
#: a dot (so `python3.9` and `v0.3.0` are versions, not quantities), then at
#: most one space, then a short alphabetic unit.
_UNIT_HIT = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)[ \t]?([A-Za-z]{1,12})\b"
)

#: Named in the message so a reader sees the contrast rather than a
#: category name. Pinned to the list by the selfcheck, so the sentence
#: cannot drift away from what the gate actually allows (6.10).
_MESSAGE_EXEMPLARS = ("ms", "mb", "rows", "requests")

_CURRENCY_HIT = re.compile("[" + "".join(_CURRENCY_SYMBOLS) + "]")

#: `$` is currency ONLY immediately before a number of at least two
#: characters. Measured before this was written: `$` on its own matches 427
#: times in the surface and nearly every one is `$?`, `$HOME` or `$1` in
#: shell. The two-character floor is what separates a grouped or decimal
#: amount from `$1`..`$9`, which are shell positional parameters and
#: nothing else.
#: The price is that a one-digit amount (`$5`) is missed; that is stated
#: here and in the round record rather than left for a reader to discover,
#: because this whole gate is a floor and a floor with an unlisted hole is
#: not one.
_DOLLAR_HIT = re.compile(r"\$\d[\d,.]*\d")

# ── the surface ─────────────────────────────────────────────────────────────

#: What ships and what teaches, relative to the repository root.
SURFACE_DIRS = (
    "python/sutradhar_guards", "python/tests",
    "examples", "js", "plugin", "docs",
)
SURFACE_FILES = (
    "README.md", "DOCTRINE.md", "SECURITY.md", "python/README.md",
)
#: A record must be able to name the term it removed. See the docstring.
EXEMPT = ("docs/rounds", "CHANGELOG.md")

SKIP_DIRS = frozenset({
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "site-packages", ".eggs",
})


class ShapeError(Exception):
    """The check could not run. Never a verdict on the tree."""


class Finding:
    """One literal that speaks a domain, and where it is today.

    ``key`` is what a baseline banks and carries no line number (R18-1);
    ``message`` carries the line, for the reader. One key per (file, matched
    text): the identity of a finding here is "this file uses this term", not
    "the fourth occurrence of it". A second legitimate rupee example in a
    file already banked for rupee parsing is not a new leak, and a gate that
    called it one would be muted inside a week (B-2).
    """

    __slots__ = ("key", "path", "line", "text", "why")

    def __init__(self, path: str, line: int, text: str, why: str) -> None:
        self.key = "{}::{}".format(path, text)
        self.path = path
        self.line = line
        self.text = text
        self.why = why

    @property
    def message(self) -> str:
        return "{}:{}: {!r} - {}".format(self.path, self.line, self.text,
                                         self.why)

    def __str__(self) -> str:
        return self.key


# ── check 1: the detector ───────────────────────────────────────────────────

def scan_text(text: str, path: str = "<src>") -> list:
    """Every domain-unit literal and currency symbol in ``text``.

    De-duplicated per (path, matched text), first occurrence winning, so the
    line printed is the first one a reader will find.
    """
    out: list = []
    seen = set()

    def add(line_no: int, matched: str, why: str) -> None:
        if (path, matched) in seen:
            return
        seen.add((path, matched))
        out.append(Finding(path, line_no, matched, why))

    for line_no, line in enumerate(text.splitlines(), 1):
        for m in _UNIT_HIT.finditer(line):
            unit = m.group(2).lower()
            industry = _DOMAIN_UNITS.get(unit)
            if industry is None:
                continue
            add(line_no, m.group(0),
                "a domain unit ({}). Engineering units ({}) are this "
                "framework's own subject; domain units belong to whatever "
                "the adopter measures".format(
                    industry, ", ".join(_MESSAGE_EXEMPLARS)))
        for m in _CURRENCY_HIT.finditer(line):
            add(line_no, m.group(0),
                "a currency symbol. Money is the adopter's subject, never "
                "the framework's")
        for m in _DOLLAR_HIT.finditer(line):
            add(line_no, m.group(0),
                "a currency amount. Money is the adopter's subject, never "
                "the framework's")
    return out


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return b"\0" in fh.read(8192)
    except OSError:
        return True


def surface_files(repo: Path, dirs=SURFACE_DIRS, files=SURFACE_FILES,
                  exempt=EXEMPT) -> list:
    """Every readable text file in the framework surface, sorted.

    Exemptions are matched on the path RELATIVE TO THE REPOSITORY, prefix
    first, so ``docs/rounds`` covers the directory and ``CHANGELOG.md``
    covers the file.
    """
    def exempted(rel: str) -> bool:
        return any(rel == e or rel.startswith(e.rstrip("/") + "/")
                   for e in exempt)

    found: list = []
    for name in files:
        p = repo / name
        if p.is_file() and not exempted(name) and not _is_binary(p):
            found.append(p)
    for name in dirs:
        root = repo / name
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(repo).parts
            if any(part in SKIP_DIRS for part in rel_parts[:-1]):
                continue
            rel = "/".join(rel_parts)
            if exempted(rel) or _is_binary(p):
                continue
            found.append(p)
    return sorted(set(found))


def scan_surface(repo: Path, dirs=SURFACE_DIRS, files=SURFACE_FILES,
                 exempt=EXEMPT) -> tuple:
    """(findings, files read) over the whole framework surface."""
    paths = surface_files(repo, dirs, files, exempt)
    out: list = []
    for p in paths:
        rel = "/".join(p.relative_to(repo).parts)
        out.extend(scan_text(p.read_text(encoding="utf-8", errors="replace"),
                             rel))
    return out, paths


# ── check 3: added lines only ───────────────────────────────────────────────

def added_lines(repo: Path, ref: str) -> list:
    """[(path relative to the repo, line number, text)] for every ADDED line
    in ``git diff -U0 <ref>``.

    ``<ref>`` is handed to git verbatim, so a bare ref compares it with the
    WORKING TREE (what a pre-commit hook wants) and a range like
    ``origin/main..HEAD`` compares the range. Getting this wrong in either
    direction produces a green over an empty diff, which is why the caller
    is told how many lines were read.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "diff", "-U0", "--no-color", ref],
            capture_output=True, text=True, timeout=120,
        )
    except OSError as exc:
        raise ShapeError("git could not be run: {}: {}".format(
            type(exc).__name__, exc))
    except subprocess.TimeoutExpired:
        raise ShapeError("`git diff {}` exceeded 120s".format(ref))
    if proc.returncode != 0:
        raise ShapeError("`git diff -U0 {}` exited {}: {}".format(
            ref, proc.returncode, (proc.stderr or "").strip()[:400]))

    out: list = []
    path = None
    line_no = 0
    for raw in proc.stdout.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else target[2:] \
                if target.startswith(("a/", "b/")) else target
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line_no = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            if path is not None:
                out.append((path, line_no, raw[1:]))
            line_no += 1
    return out


def scan_diff(repo: Path, ref: str, dirs=SURFACE_DIRS, files=SURFACE_FILES,
              exempt=EXEMPT) -> tuple:
    """(findings, lines read) over the added lines of a diff.

    Only lines in files that are in the framework surface are judged - the
    same scope as a full scan, decided by path rather than by what happens
    to exist on disk, so a file deleted in this diff is still scoped
    correctly.
    """
    in_surface = set()
    for p in surface_files(repo, dirs, files, exempt):
        in_surface.add("/".join(p.relative_to(repo).parts))

    def scoped(rel: str) -> bool:
        if rel in in_surface:
            return True
        if any(rel == e or rel.startswith(e.rstrip("/") + "/")
               for e in exempt):
            return False
        return (rel in files
                or any(rel.startswith(d.rstrip("/") + "/") for d in dirs))

    lines = added_lines(repo, ref)
    out: list = []
    seen = set()
    for rel, line_no, text in lines:
        if not scoped(rel):
            continue
        for f in scan_text(text, rel):
            if f.key in seen:
                continue
            seen.add(f.key)
            out.append(Finding(rel, line_no, f.text, f.why))
    return out, lines


# ── the baseline: every entry carries a reason ──────────────────────────────

def load_baseline(path: Path) -> dict:
    """{key: reason}. Refuses a row with no reason, and says which row.

    A banked entry is a judgement somebody made - "this is the guard's
    documented cross-unit example", "this demonstrates lakh/crore parsing".
    An entry with no reason has recorded the outcome of the judgement and
    thrown the judgement away, which is an ignore-list row. Refusing it is
    2.9 pointed at the baseline: a row that cannot say why it is there has
    not been decided, and undecided must not read the same as allowed.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShapeError("cannot read the baseline {}: {}: {}".format(
            path, type(exc).__name__, exc))
    if not isinstance(data, dict):
        raise ShapeError(
            "the baseline {} is a {}, not an object of key -> reason".format(
                path, type(data).__name__))
    bad = [k for k, v in data.items()
           if not isinstance(v, str) or not v.strip()]
    if bad:
        raise ShapeError(
            "{} baseline entr(ies) carry no reason: {}. Every banked entry "
            "states why it is legitimate, in one line, or it is an "
            "ignore-list row.".format(len(bad), ", ".join(sorted(bad)[:6])))
    return data


def compare(found: list, baseline: dict) -> tuple:
    """(findings not banked, banked keys no longer found).

    The second half is the guard-the-guard that separates a ratchet from an
    ignore-list (``ratchet.py``): an entry that quietly stopped being a
    finding must leave the baseline, or the floor stops meaning anything.
    """
    keys = {f.key for f in found}
    new = sorted((f for f in found if f.key not in baseline),
                 key=lambda f: f.key)
    stale = sorted(k for k in baseline if k not in keys)
    return new, stale


# ── check 2: the corpus-relative report ─────────────────────────────────────

_TERM = re.compile(r"[A-Za-z][A-Za-z_]{2,}")

#: Ordinary English and ordinary programming. Explicit, because the ranking
#: is meant to be read by a person and a list topped by `that`, `with` and
#: `return` is a list nobody reads to the bottom of. This is a readability
#: aid on a REPORT, not a filter on a gate: nothing here changes a verdict,
#: because this mode does not produce one.
_STOPWORDS = frozenset("""
about above after again against all also always and any are because been
before being below between both but came can cannot come could did does
doing done down during each either else even ever every for from further
gets give given goes had has have here hers herself him himself his how
however into its itself just like made make many may might more most much
must never new nor not now off once only onto other others ought our ours
out over own put rather same shall she should since some such than that the
their theirs them then there these they this those through thus too under
until upon use used uses using very want was way well were what when where
which while who whom whose why will with within without would you your yours
nothing one two three four five six seven eight nine ten another thing
things first second third last next still yet real simply actually
args assert async await bool break call called caller calls case cases class
code data def default dict elif else except false file files float for from
func function functions get given global has here import in index init int
is iter json key keys lambda len line lines list local main map module name
none not null obj object only open param params pass path paths print raise
range read result results return returns run runs self set src str string
strings sys test tests text then this true try tuple type types util utils
value values var while with write yield none true false
""".split())


def corpus_terms(root: Path) -> tuple:
    """(Counter of terms in the tree, number of files read).

    Lowercased, at least four letters, stopwords dropped. Deliberately not
    tokenised per language: the point is what the tree TALKS ABOUT, and an
    identifier, a comment and a docstring are all evidence of that.
    """
    from collections import Counter
    counts: "Counter" = Counter()
    files = 0
    if not root.is_dir():
        raise ShapeError(
            "no corpus tree at {} - nothing was read, and this is not a "
            "pass (2.9)".format(root))
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if _is_binary(p):
            continue
        files += 1
        for word in _TERM.findall(p.read_text(encoding="utf-8",
                                              errors="replace")):
            low = word.lower()
            if low not in _STOPWORDS:
                counts[low] += 1
    return counts, files


def against_report(repo: Path, corpus: Path, top: int = 40,
                   min_count: int = 5) -> tuple:
    """([(term, count there, count here)], corpus files, surface files).

    Ranked by centrality in the CORPUS, which is the whole method: a
    blocklist written from memory is a test of the author's recall, and it
    passed this repository twice while `meter` sat in it 12 times.
    """
    from collections import Counter
    counts, corpus_files = corpus_terms(corpus)
    here: "Counter" = Counter()
    paths = surface_files(repo)
    for p in paths:
        for word in _TERM.findall(p.read_text(encoding="utf-8",
                                              errors="replace")):
            low = word.lower()
            if low not in _STOPWORDS:
                here[low] += 1
    rows = [
        (term, n, here[term])
        for term, n in counts.most_common()
        if n >= min_count and here.get(term)
    ]
    return rows[:top], corpus_files, len(paths)


# ── selfcheck ───────────────────────────────────────────────────────────────

def selfcheck() -> bool:
    """Known-good and known-bad for every claim this guard makes.

    An exit code is evidence only in pairs (6.7), and the fixtures below are
    BUILT from the shipped lists rather than written out: that way every
    declared unit and every declared currency symbol is exercised (a typo in
    either list is caught here, not by a leak getting through), and this
    file carries no domain literal of its own for its own gate to find.
    """
    problems: list = []

    def fail(msg: str) -> None:
        problems.append(msg)

    # Every declared domain unit must be detected, spaced and unspaced.
    for unit, industry in sorted(_DOMAIN_UNITS.items()):
        spaced = scan_text("peak was 1,240 {} last week".format(unit), "a.md")
        tight = scan_text("peak was 980{} last week".format(unit), "a.md")
        if not spaced:
            fail("the domain unit {!r} ({}) is declared and not detected "
                 "with a space".format(unit, industry))
        if not tight:
            fail("the domain unit {!r} ({}) is declared and not detected "
                 "without a space".format(unit, industry))

    # Every declared currency symbol must be detected.
    for sym in _CURRENCY_SYMBOLS:
        if not scan_text("revenue rose {}4,200 this quarter".format(sym),
                         "a.md"):
            fail("the currency symbol U+{:04X} is declared and not "
                 "detected".format(ord(sym)))

    # Every declared engineering unit must NOT be. This is the half that
    # keeps the guard usable: a gate that flagged `500 ms` would be gone by
    # Friday, and the two lists must not overlap for either half to mean
    # anything.
    drifted = [u for u in _MESSAGE_EXEMPLARS if u not in _ENGINEERING_UNITS]
    if drifted:
        fail("the message names {} as engineering units and the list does "
             "not carry them; the sentence and the gate disagree".format(
                 drifted))
    overlap = sorted(set(_ENGINEERING_UNITS) & set(_DOMAIN_UNITS))
    if overlap:
        fail("{} unit(s) are in both lists, so the gate contradicts "
             "itself: {}".format(len(overlap), overlap))
    for unit in sorted(_ENGINEERING_UNITS):
        if scan_text("the sweep took 250 {} at 12{}".format(unit, unit),
                     "a.md"):
            fail("the engineering unit {!r} was flagged; the framework "
                 "measures itself in it".format(unit))

    # Shapes that must stay quiet, each one a false positive that would have
    # got this guard switched off.
    for label, text in (
        ("a percentage", "coverage improved to 84.5% this round"),
        ("a version", "python3.9 and v0.3.0 still parse"),
        ("a date", "Round 18 - 2026-09-07"),
        ("a finding id", "R18-5 and R16-1 both landed"),
        ("a shell positional parameter", 'printf "%s" "$1" && exit $?'),
        ("a shell variable", "cd $HOME && echo $0 $9"),
        ("a scale figure", "200,000 rows and 1,400 point pins"),
        ("a bare unit word with no number", "the kwh column and crore text"),
    ):
        hits = scan_text(text, "a.md")
        if hits:
            fail("{} was flagged: {}".format(label, [h.text for h in hits]))

    # Shapes that must be caught, spelled out so the dollar rule's edge is
    # under test rather than in a comment.
    for label, text in (
        ("a grouped dollar amount",
         "the invoice came to ${} last month".format("1,240")),
        ("a decimal dollar amount",
         "unit price is ${} today".format("12.50")),
    ):
        if not scan_text(text, "a.md"):
            fail("{} was NOT flagged".format(label))

    # De-duplication: the identity is the file plus the term, not the
    # occurrence, and the key never carries a line number (R18-1).
    unit = sorted(_DOMAIN_UNITS)[0]
    repeated = scan_text("1,240 {u}\nnoise\n1,240 {u}\n".format(u=unit), "a.md")
    if len(repeated) != 1:
        fail("the same literal twice in one file produced {} findings, not "
             "one".format(len(repeated)))
    shifted = scan_text("# pushed down\n" * 7 + "1,240 {}\n".format(unit),
                        "a.md")
    flat = scan_text("1,240 {}\n".format(unit), "a.md")
    # Shapes are validated BEFORE they are indexed. A selfcheck that raises
    # has reported nothing and takes every later case in the run down with
    # it, which is 6.11 and is exactly how the round-18 CI guard failed.
    if not flat or not shifted:
        fail("the detector found nothing in its own planted fixture, so "
             "every case below it would be vacuous")
    elif shifted[0].line == flat[0].line:
        fail("the fixture did not move; the key-stability case is vacuous")
    elif {f.key for f in shifted} != {f.key for f in flat}:
        fail("lines inserted above a finding changed its key")
    for f in flat:
        # The key is the file plus the matched text and nothing else. Checked
        # structurally rather than by hunting `:\d+` in the whole key, because
        # the matched text may legitimately begin with a digit - `a.md::1,240
        # kwh` is a stable key, and a regex would call it a position.
        if f.key != "{}::{}".format(f.path, f.text):
            fail("a key is not <path>::<text>: {!r}".format(f.key))
        if re.search(r":\d+", f.key.split("::", 1)[0]):
            fail("a key's path half carries a line number: {!r}".format(f.key))

    # The baseline refuses a row with no reason, and accepts one with.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        good = tmp / "good.json"
        good.write_text(json.dumps({"a.md::1,240 " + unit: "why it is fine"}))
        try:
            if load_baseline(good) == {}:
                fail("a well-formed baseline was read as empty")
        except ShapeError as exc:
            fail("a well-formed baseline was refused: {}".format(exc))
        for label, body in (("an empty reason", {"a.md::x": "  "}),
                            ("a null reason", {"a.md::x": None}),
                            ("a list instead of an object", ["a.md::x"])):
            bad = tmp / "bad.json"
            bad.write_text(json.dumps(body))
            try:
                load_baseline(bad)
            except ShapeError:
                pass
            else:
                fail("a baseline with {} was accepted".format(label))

        # A banked entry is not a finding; an unbanked one is; a banked
        # entry that has gone is reported for banking.
        found = scan_text("1,240 {}\n".format(unit), "a.md")
        if found:
            new, stale = compare(found, {found[0].key: "banked"})
            if new or stale:
                fail("a banked finding was reported: new={} stale={}".format(
                    [f.key for f in new], stale))
            new, stale = compare(found, {})
            if len(new) != 1 or stale:
                fail("an unbanked finding was not reported")
        new, stale = compare([], {"a.md::gone": "banked"})
        if new or stale != ["a.md::gone"]:
            fail("a banked entry that is no longer found was not reported")

        # The surface: exemptions apply, and the rest of the tree is read.
        repo = tmp / "repo"
        (repo / "docs" / "rounds").mkdir(parents=True)
        (repo / "docs").joinpath("guide.md").write_text("x\n")
        (repo / "docs" / "rounds" / "round-001.md").write_text("x\n")
        (repo / "CHANGELOG.md").write_text("x\n")
        (repo / "README.md").write_text("x\n")
        (repo / "elsewhere").mkdir()
        (repo / "elsewhere" / "notes.md").write_text("x\n")
        rels = {"/".join(p.relative_to(repo).parts)
                for p in surface_files(repo)}
        if "docs/guide.md" not in rels or "README.md" not in rels:
            fail("the surface missed a file it must read: {}".format(
                sorted(rels)))
        if "docs/rounds/round-001.md" in rels:
            fail("docs/rounds/ was scanned; a round record must be free to "
                 "name the term it removed")
        if "CHANGELOG.md" in rels:
            fail("CHANGELOG.md was scanned; a release note records a removal")
        if "elsewhere/notes.md" in rels:
            fail("a path outside the declared surface was scanned")

    for p in problems:
        print("[framework-shape] SELFCHECK FAILED: {}".format(p),
              file=sys.stderr)
    if not problems:
        print(
            "[framework-shape] selfcheck ok: {} domain unit(s) across {} "
            "industr(ies) each caught spaced and unspaced, {} currency "
            "symbol(s) caught, {} engineering unit(s) left alone and "
            "disjoint from the domain list, percentages/versions/dates/"
            "finding ids/shell positionals not flagged, grouped and decimal "
            "dollar amounts flagged, one key per file+term with no line "
            "number in it, a reasonless baseline row refused, and "
            "docs/rounds/ and CHANGELOG.md exempt from the surface".format(
                len(_DOMAIN_UNITS), len(set(_DOMAIN_UNITS.values())),
                len(_CURRENCY_SYMBOLS), len(_ENGINEERING_UNITS)))
    return not problems


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {
    "--baseline", "--against", "--diff", "--top", "--min-count",
    "--selfcheck", "--help", "-h",
}

_HELP = (
    "usage: framework_shape.py [REPO] [--baseline FILE]\n"
    "                          [--diff REF] [--against CORPUS]\n"
    "                          [--top N] [--min-count N] [--selfcheck]\n"
    "\n"
    "REPO is the repository root (default: the working directory).\n"
    "The baseline defaults to <REPO>/framework_shape_baseline.json.\n"
    "Exit 0 clean, 1 a finding, 2 the check could not run.\n"
)

_ADVICE = (
    "\nEngineering units are this framework's own subject; domain units and "
    "money belong to whatever the adopter measures. If a hit is a real "
    "capability rather than a leak, bank it in the baseline WITH A REASON - "
    "there is no --update-baseline, because the reason is the decision.\n"
)


def _print_findings(findings: list) -> None:
    for f in findings:
        print("  {}".format(f.message))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # No arguments is a selfcheck, not a scan of some assumed directory: a
    # default path nobody named would report OK over a tree nothing read.
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(_HELP)
        print(__doc__)
        return 0

    baseline_path = None
    against = None
    diff_ref = None
    top = 40
    min_count = 5
    positional: list = []
    i = 0
    # A flag whose value is missing or unreadable is a caller error, and it
    # is reported as one rather than as a traceback: a guard that crashes has
    # not reported anything (6.11).
    try:
        while i < len(argv):
            a = argv[i]
            if a == "--baseline":
                baseline_path = Path(argv[i + 1]); i += 2
            elif a == "--against":
                against = Path(argv[i + 1]); i += 2
            elif a == "--diff":
                diff_ref = argv[i + 1]; i += 2
            elif a == "--top":
                top = int(argv[i + 1]); i += 2
            elif a == "--min-count":
                min_count = int(argv[i + 1]); i += 2
            elif a.startswith("-"):
                # Refused, never ignored: a dropped `--selfchek` would run
                # the default scan and exit 0, which reads as a pass and
                # proves only that the module imported (R17-2).
                if a not in _KNOWN_FLAGS:
                    print("[framework-shape] unknown flag: {}".format(a),
                          file=sys.stderr)
                    return 2
                i += 1
            else:
                positional.append(Path(a)); i += 1
    except (IndexError, ValueError) as exc:
        print("[framework-shape] bad argument after {!r}: {}: {}. Nothing "
              "was checked.".format(argv[i], type(exc).__name__, exc),
              file=sys.stderr)
        return 2

    if len(positional) > 1:
        print("[framework-shape] name at most one repository root; "
              "nothing was checked", file=sys.stderr)
        return 2
    repo = positional[0] if positional else Path(".")
    if baseline_path is None:
        # Beside the repository being gated, not beside the caller's cwd: a
        # baseline resolved against the working directory is silently empty
        # when the tool is run from anywhere else, and an empty baseline
        # turns every banked entry into a fresh finding.
        baseline_path = repo / "framework_shape_baseline.json"
    if not repo.is_dir():
        print("[framework-shape] no repository at {} - nothing was read, "
              "and this is not a pass (2.9)".format(repo), file=sys.stderr)
        return 2

    if not selfcheck():
        return 1

    try:
        if against is not None:
            return _run_against(repo, against, top, min_count)
        baseline = load_baseline(baseline_path)
        if diff_ref is not None:
            return _run_diff(repo, diff_ref, baseline)
        return _run_full(repo, baseline, baseline_path)
    except ShapeError as exc:
        print("[framework-shape] could not run: {}".format(exc),
              file=sys.stderr)
        return 2


def _run_full(repo: Path, baseline: dict, baseline_path: Path) -> int:
    found, paths = scan_surface(repo)
    if not paths:
        print("[framework-shape] the framework surface under {} is empty - "
              "nothing was read, and this is not a pass (2.9)".format(repo),
              file=sys.stderr)
        return 2
    new, stale = compare(found, baseline)
    if new:
        print("\n[framework-shape] {} domain literal(s) in the framework "
              "surface are not banked:\n".format(len(new)))
        _print_findings(new)
        print(_ADVICE)
        return 1
    if stale:
        print("\n[framework-shape] {} banked entr(ies) are no longer found; "
              "remove them from {} so the floor drops:\n".format(
                  len(stale), baseline_path))
        for k in stale:
            print("  {}".format(k))
        print()
        return 1
    print("[framework-shape] OK - {} file(s) of framework surface, {} banked "
          "entr(ies), no unbanked domain unit or currency amount. "
          "docs/rounds/ and CHANGELOG.md are exempt: a record names the term "
          "it removed.".format(len(paths), len(baseline)))
    print("[framework-shape] this is a FLOOR, not a proof - it cannot see an "
          "ordinary business noun. Run --against <corpus> before publishing.")
    return 0


def _run_diff(repo: Path, ref: str, baseline: dict) -> int:
    found, lines = scan_diff(repo, ref)
    new, _ = compare(found, baseline)
    if new:
        print("\n[framework-shape] {} domain literal(s) in lines ADDED "
              "against {}:\n".format(len(new), ref))
        _print_findings(new)
        print(_ADVICE)
        return 1
    # The stale half is deliberately NOT applied here: a diff sees added
    # lines only, so every banked entry outside it would read as fixed.
    print("[framework-shape] OK - {} added line(s) across {} file(s) "
          "against {}, none carrying an unbanked domain unit or currency "
          "amount ({} banked entr(ies)).".format(
              len(lines), len({rel for rel, _, _ in lines}), ref,
              len(baseline)))
    print("[framework-shape] what a diff cannot see, said out loud: a file "
          "git is not tracking yet is in no diff, and the stale-entry check "
          "belongs to a full scan. Run `framework_shape.py <repo>` for both.")
    return 0


def _run_against(repo: Path, corpus: Path, top: int, min_count: int) -> int:
    rows, corpus_files, surface_count = against_report(
        repo, corpus, top=top, min_count=min_count)
    print("[framework-shape] corpus check - a REPORT, never a gate, and "
          "never run in CI.")
    print("  corpus:  {} ({} file(s))".format(corpus, corpus_files))
    print("  surface: {} file(s) under {}".format(surface_count, repo))
    print(
        "\nWhy this mode exists: check 1 CANNOT find an ordinary business "
        "noun.\nNothing self-contained can tell `device` (fine) from `meter` "
        "(a leak) -\nthe signal only exists relative to a corpus, and the "
        "public repository\ndoes not have one. This is for the maintainer to "
        "run before publishing,\nagainst the private tree the framework was "
        "distilled from. Check 1 alone\nis NOT sufficient.\n"
        "\nMethod (R18-5): derive the vocabulary from the source you are "
        "protecting,\nnot from what you remember about it. A blocklist "
        "written from memory passed\nthis repository twice while `meter` sat "
        "in it 12 times.\n")
    inside = str(corpus.resolve()).startswith(str(repo.resolve()))
    if inside:
        print("NOTE: the corpus is INSIDE the repository being checked, so "
              "every term is\ntrivially 'present here'. This run calibrates "
              "the ranking; it is not a leak\nreport.\n")
    if not rows:
        print("  (no term is central in the corpus and present here at "
              "these thresholds)")
    else:
        print("  {:>4}  {:>8}  {:>6}  {}".format(
            "rank", "corpus", "here", "term"))
        for n, (term, there, here_n) in enumerate(rows, 1):
            print("  {:>4}  {:>8}  {:>6}  {}".format(n, there, here_n, term))
    print("\n[framework-shape] REPORT ONLY - a ranked list for a person to "
          "read, not a verdict. Exit 0 means the report was produced, not "
          "that the surface is clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
