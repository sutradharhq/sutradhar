"""rounds - the flight recorder: make doctrine 8.1 and 8.3 computable.

Two rules in this framework ask a question nobody can currently answer.

**8.1** says a rule nobody can cite a save from is a candidate for deletion.
Answering that needs to know which rule caught what, over time. Nothing
recorded it, so no rule has ever been deleted for lack of evidence and the
doctrine can only grow.

**8.3** says stop when the marginal round yields less than the next cheapest
activity. *Scar: it took us 24 rounds to ask that question. Ask by round 5.*
Answering it needs findings-per-round. That was felt, not computed, which is
precisely why it took 24 rounds.

There is a third gap: the robustness-loop skill instructs you to keep a
"residual register" and ships no format for one.

This module reads round records - the artifact that skill already tells you
to write - and computes all three. It is a REPORTER first and a gate second:

    python rounds.py docs/rounds/            # the report
    python rounds.py docs/rounds/ --check    # gate: are the records valid?
    python rounds.py docs/rounds/ --floors . # add the mechanically-sampled half

## The round record

Prose first, because the record is a document a human writes and reads. The
machine only needs the table:

    # Round 7 - 2026-08-08

    Lenses: authz, numeric, scale

    | id | severity | rule | found-by | status | summary |
    |---|---|---|---|---|---|
    | R7-1 | high | 2.7 | swallow-lint | fixed | metering read swallowed to {} |
    | R7-2 | med  | 2.6 | scale lens   | deferred | sweep uncapped above 50k |
    | R6-3 | med  | 3.1 | -            | closed | picker effect asserted |

    ...then the prose the skill asks for: corrected premises, harness
    gotchas, what you ruled out.

`severity` is high/med/low, `status` is fixed/deferred/closed/retracted,
and `rule` is a doctrine id (`2.7`) or `-`. A deferred finding stays in the
residual register until a later round lists the same id as closed, fixed or
retracted. `closed` resolves a finding whose save stands; `retracted` marks
the original finding as WRONG, so it leaves the register AND takes its
rule-attribution save with it.

## Provenance, because this tool reports numbers (doctrine 5.1)

Findings are **recorded**: a human or agent typed them, and a logbook can be
wrong or lazy in ways telemetry cannot. Floors (`--floors`) are **measured**:
sampled from the baseline files themselves with nobody's judgement in the
loop. The report labels which is which, and never presents one as the other.

The honest limit that follows: this measures the loop, not the codebase. A
round that found nothing because nobody looked hard produces the same row as
a round that found nothing because there was nothing to find. The stop-rule
verdict is evidence for a decision, not the decision.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

SEVERITIES = ("high", "med", "low")
STATUSES = ("fixed", "deferred", "closed", "retracted")
COLUMNS = ("id", "severity", "rule", "found-by", "status", "summary")

# ── backflow register ───────────────────────────────────────────────────────
# Doctrine distilled from several independent builds goes stale in one
# direction: the threads keep inventing, and nothing carries the inventions
# home. Four threads independently solved problems the doctrine still listed
# as open, and every crossing that did happen was a side-effect of somebody
# building a tool, never a decision. The register makes an unmoved item cost
# something: an entry past its by-round fails the gate until somebody adopts
# it, rejects it with a reason, or re-defers it to a new round with a reason.
BACKFLOW_STATUSES = ("owed", "adopted", "rejected", "deferred")
# 8.1: a rule enters with the incident that paid for it. A documented
# intention is not an incident, so `practice` items may strengthen the
# mechanism of a rule that already has a scar - they may not found a new one.
BACKFLOW_EVIDENCE = ("scar", "practice")
BACKFLOW_COLUMNS = (
    "id", "source", "what", "evidence", "rule", "status", "by-round", "note",
)

# ── design-note scar admission ──────────────────────────────────────────────
# 8.1 says a rule enters with the incident that paid for it. The backflow
# register mechanises that for RULES. Nothing mechanised it for MECHANISMS: a
# design note could enter on argument alone. Every note in this repo happened
# to cite a scar in its prose, one cited nothing, and no gate would have
# refused a note that cited nothing - which is the difference between a
# discipline and a habit.
#
# `sutradhar_scar` makes the admission explicit and machine-checkable. Its
# value is either finding ids that must RESOLVE against the round records, or
# the literal `distribution`, which is an honest admission that the mechanism
# entered on an adoption argument rather than an incident - and which then
# owes a sentence saying so. `distribution` is a legitimate answer; an
# unstated one is not.
SCAR_KEY = "sutradhar_scar"
SCAR_ARGUMENT_KEY = "sutradhar_scar_argument"
SCAR_DISTRIBUTION = "distribution"
# The template ships with placeholder frontmatter and is reference material,
# not a design note. Skipped by name, exactly as budget.py skips it, so a
# fresh bootstrap does not open on a false red.
DESIGN_TEMPLATE_NAME = "TEMPLATE.md"
_FINDING_ID = re.compile(r"R\d+-\d+")

_HEADING = re.compile(r"^#\s+Round\s+(\d+)\s*[-–—]\s*(\d{4}-\d{2}-\d{2})\s*$",
                      re.MULTILINE)
_LENSES = re.compile(r"^Lenses:\s*(.+)$", re.IGNORECASE)
_DOCTRINE_RULE = re.compile(r"^\*\*(\d+\.\d+)\s")
# "Thin data" floor: below this many rounds, an attribution claim is noise.
MIN_ROUNDS_FOR_ATTRIBUTION = 5
# 8.1 asks for MONTHS of silence, not a quiet week. Round count alone is
# gameable: six rounds in nine days satisfied the floor above while the
# rule's own condition had not begun to run. Both floors must clear.
MIN_SPAN_DAYS_FOR_ATTRIBUTION = 60


class RoundError(ValueError):
    pass


@dataclass
class Finding:
    id: str
    severity: str
    rule: str          # "" when none cited
    found_by: str
    status: str
    summary: str
    round: int = 0


@dataclass
class Round:
    number: int
    date: str
    source: str = ""
    lenses: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity
                   and f.status not in ("closed", "retracted"))

    def new_findings(self) -> list[Finding]:
        """Findings this round surfaced, excluding bookkeeping rows that
        merely close an earlier deferral or retract an earlier finding."""
        return [f for f in self.findings if f.status not in ("closed", "retracted")]


# ── parsing ─────────────────────────────────────────────────────────────────

def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_round(text: str, source: str = "") -> Round:
    """Parse one round record. Refuses what it cannot read exactly: a
    silently half-read register is worse than no register."""
    lines = text.splitlines()
    heading = next((_HEADING.match(l) for l in lines if _HEADING.match(l)), None)
    if heading is None:
        raise RoundError(
            f"{source}: no round heading. The first heading must read exactly "
            f"`# Round <n> - <YYYY-MM-DD>`."
        )
    rnd = Round(number=int(heading.group(1)), date=heading.group(2), source=source)

    for line in lines:
        lens_match = _LENSES.match(line.strip())
        if lens_match:
            rnd.lenses = [x.strip() for x in lens_match.group(1).split(",") if x.strip()]
            break

    header_at = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|") and tuple(
            c.lower() for c in _split_row(line)
        ) == COLUMNS:
            header_at = i
            break
    if header_at is None:
        raise RoundError(
            f"{source}: no findings table. Expected a header row of exactly "
            f"| {' | '.join(COLUMNS)} |. A round with genuinely nothing to "
            f"report still writes the table, with no rows - that is the "
            f"difference between 'we looked and found nothing' and 'nobody "
            f"wrote it down'."
        )

    seen: set[str] = set()
    for lineno, line in enumerate(lines[header_at + 2:], start=header_at + 3):
        stripped = line.strip()
        if not stripped.startswith("|"):
            break                                   # table ended
        cells = _split_row(stripped)
        if len(cells) != len(COLUMNS):
            raise RoundError(
                f"{source}:{lineno}: {len(cells)} cells, expected "
                f"{len(COLUMNS)} ({', '.join(COLUMNS)})"
            )
        ident, severity, rule, found_by, status, summary = cells
        if set(ident) <= {"-", " "}:
            continue                                # separator row
        severity, status = severity.lower(), status.lower()
        if severity not in SEVERITIES:
            raise RoundError(
                f"{source}:{lineno}: severity {severity!r} is not one of "
                f"{'/'.join(SEVERITIES)}"
            )
        if status not in STATUSES:
            raise RoundError(
                f"{source}:{lineno}: status {status!r} is not one of "
                f"{'/'.join(STATUSES)}"
            )
        if ident in seen:
            raise RoundError(f"{source}:{lineno}: finding id {ident!r} repeated "
                             f"within round {rnd.number}")
        seen.add(ident)
        rnd.findings.append(Finding(
            id=ident, severity=severity, rule="" if rule in ("-", "") else rule,
            found_by=found_by, status=status, summary=summary, round=rnd.number,
        ))
    return rnd


def load_rounds(root: str | Path) -> list[Round]:
    root = Path(root)
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    rounds = [
        parse_round(p.read_text(encoding="utf-8", errors="replace"), source=str(p))
        for p in files
        if _HEADING.search(p.read_text(encoding="utf-8", errors="replace")) or p == root
    ]
    numbers = [r.number for r in rounds]
    dupes = {n for n in numbers if numbers.count(n) > 1}
    if dupes:
        raise RoundError(
            f"round number(s) {sorted(dupes)} recorded more than once. Round "
            f"numbers order the history; a duplicate makes the trend a lie."
        )
    return sorted(rounds, key=lambda r: r.number)


@dataclass
class BackflowItem:
    id: str
    source: str
    what: str
    evidence: str      # "scar" | "practice"
    rule: str          # a doctrine rule id, or "new" for a proposed rule
    status: str
    by_round: int
    note: str


BACKFLOW_HEADING = "## The register"


def parse_backflow(text: str, source: str = "") -> list[BackflowItem]:
    """Parse the backflow register. Refuses what it cannot read exactly.

    Only the table under `## The register` is read, so the explanatory tables
    above it are not mistaken for entries - and, more importantly, so a
    malformed row inside the register can be REFUSED rather than skipped. An
    earlier draft skipped any row without exactly eight cells; the first real
    register written against it contained a note with an escaped pipe, the row
    split into nine, and the item vanished while the gate printed OK. That is
    2.9 in the instrument itself: "cannot read this row" was spelled the same
    as "no row here".
    """
    items: list[BackflowItem] = []
    seen: set[str] = set()
    where = f" in {source}" if source else ""
    if BACKFLOW_HEADING not in text:
        raise RoundError(
            f"no {BACKFLOW_HEADING!r} heading{where}. The register table must "
            f"live under it so a malformed row can be told from prose."
        )
    body = text.split(BACKFLOW_HEADING, 1)[1]
    for line in body.splitlines():
        st = line.strip()
        if not st.startswith("|"):
            continue
        cells = _split_row(st)
        low = [c.lower() for c in cells]
        if low == list(BACKFLOW_COLUMNS):
            continue
        if set("".join(cells)) <= set("-: "):
            continue  # the markdown separator row
        if len(cells) != len(BACKFLOW_COLUMNS):
            raise RoundError(
                f"register row{where} has {len(cells)} cell(s), expected "
                f"{len(BACKFLOW_COLUMNS)}: {st[:90]!r}\n  A pipe inside a "
                f"note splits the row. Rewrite the note without it - escaping "
                f"it as \\| does not help, the cell split happens first."
            )
        cid, src, what, evidence, rule, status, by_round, note = cells
        if not re.fullmatch(r"B-\d+", cid):
            raise RoundError(
                f"backflow id {cid!r}{where} is not of the form B-<n>."
            )
        if cid in seen:
            raise RoundError(f"backflow id {cid!r} appears twice{where}.")
        seen.add(cid)
        if status.lower() not in BACKFLOW_STATUSES:
            raise RoundError(
                f"{cid}{where}: status {status!r} is not one of "
                f"{', '.join(BACKFLOW_STATUSES)}."
            )
        if evidence.lower() not in BACKFLOW_EVIDENCE:
            raise RoundError(
                f"{cid}{where}: evidence {evidence!r} is not one of "
                f"{', '.join(BACKFLOW_EVIDENCE)}. `scar` means an incident "
                f"with a recorded cost; `practice` means a documented "
                f"intention. The distinction is what keeps 8.1 honest."
            )
        try:
            n = int(by_round)
        except ValueError:
            raise RoundError(
                f"{cid}{where}: by-round {by_round!r} is not a round number. "
                f"An item with no deadline is a wish, and this register "
                f"exists because wishes do not move."
            ) from None
        items.append(BackflowItem(
            cid, src, what, evidence.lower(), rule, status.lower(), n, note,
        ))
    return items


def backflow_problems(
    items: list[BackflowItem], latest_round: int, all_rules: set[str],
) -> list[str]:
    """Everything wrong with the register, as lines a reader can act on.

    This is the mechanism R7-1 asked for. Recording an owed item is not the
    hard part - the hard part is that recording it costs nothing, so it sits.
    Here an item past its by-round fails the gate, and the only ways out are
    decisions: adopt it, reject it with a reason, or re-defer it to a new
    round with a reason.
    """
    problems: list[str] = []
    for it in items:
        if it.status in ("owed", "deferred") and it.by_round <= latest_round:
            problems.append(
                f"  {it.id} ({it.source}): {it.status} since round "
                f"{it.by_round}, and round {latest_round} is recorded. "
                f"Decide it - adopt, reject with a reason, or re-defer to a "
                f"later round with a reason.\n      {it.what}"
            )
        if it.status in ("rejected", "deferred") and not it.note.strip("- "):
            problems.append(
                f"  {it.id}: {it.status} with no reason. 7.4 - an unrecorded "
                f"dead end gets re-explored at full price."
            )
        if it.status == "adopted":
            if it.rule.lower() in ("", "-", "new"):
                problems.append(
                    f"  {it.id}: adopted but cites no doctrine rule. An "
                    f"adoption that landed nowhere is not an adoption."
                )
            elif all_rules and it.rule not in all_rules:
                problems.append(
                    f"  {it.id}: adopted against rule {it.rule}, which is not "
                    f"in the doctrine."
                )
        if it.evidence == "practice" and it.rule.lower() == "new":
            problems.append(
                f"  {it.id}: `practice` evidence proposed as a NEW rule. "
                f"8.1 - a rule enters with the incident that paid for it, and "
                f"a documented intention is not an incident. A practice item "
                f"may strengthen the mechanism of a rule that already has a "
                f"scar; cite that rule instead."
            )
    return problems


@dataclass
class ScarCitation:
    source: str
    findings: list[str] = field(default_factory=list)
    distribution: bool = False
    argument: str = ""


# The strict frontmatter parser below MIRRORS `parse_frontmatter` in
# budget.py, deliberately duplicated rather than imported. These files are
# copy-in: an adopter who took rounds.py and not budget.py must still get a
# working gate, and an import between two single-file guards is a dependency
# the copier cannot see until it fails at runtime in their repo. Twenty-five
# lines is a cheaper price than that. The strictness IS the contract - flat
# `key: value` scalars only, no nesting, no unclosed block, no duplicate key -
# because a parser that guesses turns an unreadable note into "no note here"
# (2.9). If either copy changes, change both; they read the same documents.
_SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


def parse_note_frontmatter(text: str, source: str = "") -> dict | None:
    """Parse a leading `---` fenced block of flat `key: value` pairs.

    Returns None when the document has no frontmatter. Raises RoundError on a
    block it cannot parse strictly."""
    where = f"{source}: " if source else ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise RoundError(
            f"{where}frontmatter opened with '---' but never closed"
        ) from None

    out: dict = {}
    for lineno, raw in enumerate(lines[1:end], start=2):
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        match = _SCALAR.match(line.strip())
        if not match:
            raise RoundError(
                f"{where}line {lineno}: cannot parse {line.strip()!r}. "
                f"Design-note frontmatter takes flat `key: value` scalars "
                f"only - no lists, no nesting."
            )
        key, value = match.group(1), match.group(2).strip().strip('"').strip("'")
        if key in out:
            raise RoundError(f"{where}line {lineno}: {key!r} declared twice")
        out[key] = value
    return out


def parse_scar(text: str, source: str = "") -> ScarCitation:
    """Read one design note's admission of what paid for it.

    Refuses rather than skips, in every direction: no frontmatter, no
    `sutradhar_scar`, an empty value, an id that is not of the form R<n>-<m>,
    or `distribution` with no argument. A note that entered on nothing and a
    note the parser could not read must not be spelled the same as a note
    that passed.
    """
    where = source or "<note>"
    data = parse_note_frontmatter(text, source=source)
    missing = (
        f"{where}: no `{SCAR_KEY}:` in the frontmatter. 8.1 - a mechanism "
        f"enters with the incident that paid for it. Name the finding id(s) "
        f"from the round records, or say `{SCAR_DISTRIBUTION}` and add "
        f"`{SCAR_ARGUMENT_KEY}:` stating why this entered on an adoption "
        f"argument instead. Both are answers; silence is not."
    )
    if data is None or SCAR_KEY not in data:
        raise RoundError(missing)
    raw = data[SCAR_KEY].strip()
    if not raw:
        raise RoundError(missing)
    argument = data.get(SCAR_ARGUMENT_KEY, "").strip()

    if raw == SCAR_DISTRIBUTION:
        if not argument:
            raise RoundError(
                f"{where}: `{SCAR_KEY}: {SCAR_DISTRIBUTION}` with no "
                f"`{SCAR_ARGUMENT_KEY}:`. Entering on distribution is an "
                f"allowed answer and an unstated one is not - a bare "
                f"`{SCAR_DISTRIBUTION}` is the argument-alone admission this "
                f"gate exists to make somebody write down."
            )
        return ScarCitation(source=where, distribution=True, argument=argument)

    ids = [part.strip() for part in raw.split(",") if part.strip()]
    if not ids:
        raise RoundError(missing)
    for ident in ids:
        if not _FINDING_ID.fullmatch(ident):
            raise RoundError(
                f"{where}: {ident!r} is not a finding id. Expected R<n>-<m> "
                f"(comma-separated for several) or the literal "
                f"`{SCAR_DISTRIBUTION}`."
            )
    return ScarCitation(source=where, findings=ids, argument=argument)


def load_design_notes(root: str | Path) -> list[Path]:
    root = Path(root)
    files = [root] if root.is_file() else sorted(root.rglob("*.md"))
    return [p for p in files if p.name != DESIGN_TEMPLATE_NAME]


def scar_problems(
    citations: list[ScarCitation], known_findings: set[str],
) -> list[str]:
    """Cited findings that no round record contains.

    A citation nobody can resolve is the same failure as no citation with a
    better disguise: it reads as provenance and carries none. Any status
    counts - a finding deferred for six rounds is still an incident that was
    paid for, and refusing those would push notes towards citing nothing.
    """
    problems: list[str] = []
    for c in citations:
        for ident in c.findings:
            if ident not in known_findings:
                problems.append(
                    f"  {c.source}: cites {ident}, which is not a finding in "
                    f"any round record. An id nobody can resolve reads as "
                    f"provenance and carries none (8.1)."
                )
    return problems


def doctrine_rule_ids(path: str | Path) -> set[str]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return {m.group(1) for line in text.splitlines()
            if (m := _DOCTRINE_RULE.match(line))}


# ── the three questions ─────────────────────────────────────────────────────

def stop_rule(rounds: list[Round]) -> tuple[str, str]:
    """Doctrine 8.3, using the robustness loop's own exit criterion: the
    loop rests when two consecutive rounds surface zero HIGH findings."""
    if len(rounds) < 2:
        return "INSUFFICIENT", (
            f"{len(rounds)} round(s) recorded. The stop rule needs two "
            f"consecutive rounds before it can say anything."
        )
    last_two = rounds[-2:]
    highs = [r.count("high") for r in last_two]
    if highs == [0, 0]:
        return "REST", (
            f"rounds {last_two[0].number} and {last_two[1].number} both "
            f"surfaced zero HIGH findings. The loop has converged: move to a "
            f"longer cadence and spend the time elsewhere (doctrine 8.3). "
            f"Converged areas regrow, so schedule the re-audit rather than "
            f"declaring it done (6.5)."
        )
    trend = " -> ".join(str(r.count("high")) for r in rounds[-6:])
    return "CONTINUE", (
        f"HIGH findings per round: {trend}. Not yet two consecutive zeroes. "
        f"Ask each round whether the marginal yield still beats the next "
        f"cheapest activity - the scar behind 8.3 is 24 rounds before anyone "
        f"asked."
    )


def residual_register(rounds: list[Round]) -> list[Finding]:
    """Deferred findings never subsequently closed, fixed or retracted."""
    open_items: dict[str, Finding] = {}
    for rnd in rounds:
        for f in rnd.findings:
            if f.status == "deferred":
                open_items[f.id] = f
            elif f.status in ("closed", "fixed", "retracted") and f.id in open_items:
                del open_items[f.id]
    return sorted(open_items.values(), key=lambda f: (f.round, f.id))


def rule_attribution(rounds: list[Round], all_rules: set[str]) -> dict:
    """Which doctrine rules can cite a save, and when (doctrine 8.1).

    A finding is attributed ONCE, on its first appearance. Later rows with
    the same id are bookkeeping: `residual_register` already carries open
    deferrals forward, so a round that also re-lists them for readability
    would otherwise pay its rule a fresh save every round the deferral stays
    open - and the longer something goes unfixed, the better its rule would
    look. Found this way: round 2 re-listed three of round 1's deferrals and
    inflated 2.2 to five saves and 1.1 to four, of which three were copies.

    A RETRACTED finding is attributed never: a later row with status
    `retracted` marks the original finding as wrong, and a save paid by a
    wrong finding is not a save. `closed` resolves a finding whose save
    stands; `retracted` withdraws finding and save together. Found this way
    too: a retracted adoption-audit finding left its rule a save that round
    6 could only ask readers to mentally discount.
    """
    retracted = {f.id for rnd in rounds for f in rnd.findings
                 if f.status == "retracted"}
    last_seen: dict[str, int] = {}
    saves: dict[str, int] = {}
    counted: set[str] = set()
    for rnd in rounds:
        for f in rnd.new_findings():
            if f.rule and f.id not in counted and f.id not in retracted:
                counted.add(f.id)
                last_seen[f.rule] = max(last_seen.get(f.rule, 0), rnd.number)
                saves[f.rule] = saves.get(f.rule, 0) + 1
    return {
        "saves": saves,
        "last_seen": last_seen,
        "never_cited": sorted(all_rules - set(last_seen), key=_rule_key),
        "unknown_rules": sorted(set(last_seen) - all_rules, key=_rule_key),
    }


def _rule_key(rule: str) -> tuple:
    try:
        major, minor = rule.split(".")
        return (int(major), int(minor))
    except ValueError:
        return (99, 99)


def _history_span_days(rounds: list[Round]) -> int | None:
    """Days between the first and last round record, None if unparseable.

    The heading regex guarantees the SHAPE (\\d{4}-\\d{2}-\\d{2}) but not a
    real calendar date; refusing on None keeps a malformed date from
    silently widening the span to "long enough"."""
    try:
        first = _date.fromisoformat(rounds[0].date)
        last = _date.fromisoformat(rounds[-1].date)
    except ValueError:
        return None
    return (last - first).days


# ── the measured half ───────────────────────────────────────────────────────

def sample_floors(repo: str | Path) -> dict:
    """Mechanically sampled guard floors - no judgement in the loop.

    Baseline files are the toolkit's shrink-only allowlists, so their totals
    over time are the one number here that nobody can talk up."""
    repo = Path(repo)
    floors: dict[str, int] = {}
    for path in sorted(repo.rglob("*baseline*.json")):
        if ".git" in path.parts:
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict) and all(isinstance(v, int) for v in data.values()):
            floors[str(path.relative_to(repo))] = sum(data.values())
        elif isinstance(data, list):
            floors[str(path.relative_to(repo))] = len(data)
    return floors


# ── report ──────────────────────────────────────────────────────────────────

def report(rounds: list[Round], all_rules: set[str], floors: dict | None = None) -> str:
    bar = "-" * 70
    out = [f"\n[rounds] {bar}", f"  {len(rounds)} round(s) recorded  "
           f"({rounds[0].date} -> {rounds[-1].date})", ""]

    out.append("  findings per round        [RECORDED - a logbook, not telemetry]")
    for r in rounds[-8:]:
        bars = "".join(
            sym * r.count(sev) for sev, sym in (("high", "#"), ("med", "+"), ("low", "."))
        )
        out.append(f"    round {r.number:<3} {r.date}  "
                   f"{r.count('high')}H {r.count('med')}M {r.count('low')}L  {bars}")

    verdict, why = stop_rule(rounds)
    out += ["", f"  STOP RULE (8.3): {verdict}", f"    {why}"]

    residual = residual_register(rounds)
    out += ["", f"  RESIDUAL REGISTER: {len(residual)} open deferral(s)"]
    for f in residual[:12]:
        out.append(f"    R{f.round} {f.id:<8} [{f.severity}] {f.summary[:54]}")
    if len(residual) > 12:
        out.append(f"    ... and {len(residual) - 12} more")

    attribution = rule_attribution(rounds, all_rules)
    out += ["", "  RULE ATTRIBUTION (8.1)"]
    if attribution["saves"]:
        top = sorted(attribution["saves"].items(), key=lambda kv: -kv[1])[:6]
        out.append("    rules that earned their keep: "
                   + ", ".join(f"{r} ({n})" for r, n in top))
    else:
        out.append("    no finding cites a doctrine rule yet - fill the `rule` "
                   "column and this becomes answerable")
    span_days = _history_span_days(rounds)
    if len(rounds) < MIN_ROUNDS_FOR_ATTRIBUTION:
        out.append(
            f"    deletion candidates: NOT REPORTED. {len(rounds)} round(s) is "
            f"too thin to conclude a rule earns nothing; 8.1 asks for months of "
            f"silence, not a quiet week. Needs {MIN_ROUNDS_FOR_ATTRIBUTION}+."
        )
    elif span_days is None or span_days < MIN_SPAN_DAYS_FOR_ATTRIBUTION:
        shown = "unparseable dates" if span_days is None else f"{span_days} day(s)"
        out.append(
            f"    deletion candidates: NOT REPORTED. {len(rounds)} rounds "
            f"spanning {shown} clears the round floor but not the clock: 8.1 "
            f"asks for months of silence, and a burst of rounds in one week "
            f"is a busy week, not a silent rule. Needs "
            f"{MIN_SPAN_DAYS_FOR_ATTRIBUTION}+ days of history."
        )
    else:
        never = attribution["never_cited"]
        out.append(f"    never cited in {len(rounds)} rounds: "
                   + (", ".join(never) if never else "(none - every rule has a save)"))
        if never:
            out.append("    -> 8.1 candidates for DELETION. Read each one first: a "
                       "rule can\n       also be uncited because its guard is so good "
                       "the class never recurs.")

    if floors is not None:
        out += ["", "  GUARD FLOORS            [MEASURED - sampled from the baselines]"]
        if floors:
            for name, total in sorted(floors.items()):
                out.append(f"    {total:>6}  {name}")
            out.append("    (ratchets only shrink; a rising floor is a regression)")
        else:
            out.append("    no baseline files found")

    out.append(f"[rounds] {bar}\n")
    return "\n".join(out)


# ── selfcheck ───────────────────────────────────────────────────────────────

ROUND_TEMPLATE = """# Round {n} - {date}

Lenses: authz, scale

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
{rows}
"""


def _plant(tmp: Path, n: int, rows: list[str], date: str | None = None) -> None:
    (tmp / f"round-{n:03d}.md").write_text(
        ROUND_TEMPLATE.format(n=n, date=date or f"2026-0{n}-01",
                              rows="\n".join(rows))
    )


def selfcheck() -> bool:
    try:
        return _selfcheck_body()
    except Exception as exc:  # noqa: BLE001
        print(f"[rounds] SELFCHECK FAILED: the selfcheck itself raised "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return False


def _selfcheck_body() -> bool:
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        _plant(tmp, 1, ["| R1-1 | high | 2.7 | swallow-lint | fixed | swallowed read |",
                        "| R1-2 | med | 2.6 | scale | deferred | uncapped sweep |"])
        _plant(tmp, 2, ["| R2-1 | high | 3.1 | ui | fixed | picker did nothing |"])
        rounds = load_rounds(tmp)

        if [r.number for r in rounds] != [1, 2]:
            print(f"[rounds] SELFCHECK FAILED: parsed {[r.number for r in rounds]}",
                  file=sys.stderr)
            ok = False

        # The stop rule must NOT rest while HIGH findings are still landing.
        verdict, _ = stop_rule(rounds)
        if verdict != "CONTINUE":
            print(f"[rounds] SELFCHECK FAILED: stop rule said {verdict} with "
                  f"HIGH findings in the last round", file=sys.stderr)
            ok = False

        # ...and MUST rest after two clean rounds.
        _plant(tmp, 3, ["| R3-1 | low | 3.5 | ui | fixed | missing testid |"])
        _plant(tmp, 4, [])
        verdict, _ = stop_rule(load_rounds(tmp))
        if verdict != "REST":
            print(f"[rounds] SELFCHECK FAILED: stop rule said {verdict} after two "
                  f"rounds with zero HIGH findings", file=sys.stderr)
            ok = False

        # The residual register must hold an open deferral...
        register = residual_register(load_rounds(tmp))
        if [f.id for f in register] != ["R1-2"]:
            print(f"[rounds] SELFCHECK FAILED: residual register held "
                  f"{[f.id for f in register]}, expected ['R1-2']", file=sys.stderr)
            ok = False

        # A re-listed deferral must not pay its rule a second save. Its own
        # directory: load_rounds walks recursively and would read these as
        # duplicate round numbers of the history above.
        with tempfile.TemporaryDirectory() as relisted_s:
            relisted = Path(relisted_s)
            row = "| R1-1 | med | 2.6 | scale | deferred | uncapped sweep |"
            _plant(relisted, 1, [row])
            _plant(relisted, 2, [row])          # round 2 re-lists it, open still
            saves = rule_attribution(load_rounds(relisted), {"2.6"})["saves"]
            if saves.get("2.6") != 1:
                print(f"[rounds] SELFCHECK FAILED: one deferral listed in two "
                      f"rounds paid rule 2.6 {saves.get('2.6')} saves. A "
                      f"re-listed deferral is bookkeeping; counting it again "
                      f"makes a rule look better the longer it goes unfixed",
                      file=sys.stderr)
                ok = False

        # A retracted finding must leave the register AND lose its save -
        # and its bookkeeping row must not ride the severity counts.
        with tempfile.TemporaryDirectory() as retracted_s:
            rdir = Path(retracted_s)
            _plant(rdir, 1, ["| R1-1 | med | 2.6 | audit | deferred | wrong count |"])
            _plant(rdir, 2, ["| R1-1 | med | 2.6 | - | retracted | the count was the auditor's bug |"])
            rr = load_rounds(rdir)
            if rule_attribution(rr, {"2.6"})["saves"]:
                print("[rounds] SELFCHECK FAILED: a retracted finding kept its "
                      "save; a save paid by a wrong finding is not a save",
                      file=sys.stderr)
                ok = False
            if residual_register(rr):
                print("[rounds] SELFCHECK FAILED: a retracted finding stayed in "
                      "the residual register", file=sys.stderr)
                ok = False
            if rr[1].count("med") != 0:
                print("[rounds] SELFCHECK FAILED: a retraction bookkeeping row "
                      "rode the severity count", file=sys.stderr)
                ok = False

        # Enough rounds inside a short span must still refuse deletion
        # candidates: 8.1 asks for months, and a burst of rounds in one
        # week satisfies the round floor without the rule's condition.
        with tempfile.TemporaryDirectory() as span_s:
            sdir = Path(span_s)
            for n in range(1, MIN_ROUNDS_FOR_ATTRIBUTION + 2):
                _plant(sdir, n, [], date=f"2026-06-{n:02d}")
            burst = report(load_rounds(sdir), {"9.9"})
            if "NOT REPORTED" not in burst or "9.9" in burst:
                print(f"[rounds] SELFCHECK FAILED: {MIN_ROUNDS_FOR_ATTRIBUTION + 1} "
                      f"rounds in six days named deletion candidates; the "
                      f"{MIN_SPAN_DAYS_FOR_ATTRIBUTION}-day clock never ran",
                      file=sys.stderr)
                ok = False

        # Attribution must refuse to name deletion candidates on thin data.
        # Both sides of the threshold are checked: a refusal that never lifts
        # is as useless as one that never fires.
        rules = {"2.7", "2.6", "3.1", "3.5", "9.9"}
        thin = report(load_rounds(tmp), rules)          # 4 rounds
        if "NOT REPORTED" not in thin:
            print(f"[rounds] SELFCHECK FAILED: named deletion candidates from "
                  f"4 rounds, below the {MIN_ROUNDS_FOR_ATTRIBUTION}-round floor",
                  file=sys.stderr)
            ok = False

        # ...and must release the deferral when a later round closes it.
        _plant(tmp, 5, ["| R1-2 | med | 2.6 | scale | closed | cap shipped |"])
        if residual_register(load_rounds(tmp)) != []:
            print("[rounds] SELFCHECK FAILED: a closed deferral stayed in the "
                  "register", file=sys.stderr)
            ok = False

        thick = report(load_rounds(tmp), rules)         # 5 rounds: the floor
        if "NOT REPORTED" in thick:
            print(f"[rounds] SELFCHECK FAILED: still refusing attribution at "
                  f"{MIN_ROUNDS_FOR_ATTRIBUTION} rounds - the refusal never lifts",
                  file=sys.stderr)
            ok = False
        if "9.9" not in thick:
            print("[rounds] SELFCHECK FAILED: rule 9.9 was never cited by any "
                  "finding and was not named as a deletion candidate",
                  file=sys.stderr)
            ok = False

        # Malformed records must be refused, not half-read.
        malformed = [
            ("no heading", "Lenses: x\n\n| id | severity | rule | found-by | status | summary |\n|---|---|---|---|---|---|\n"),
            ("no findings table", "# Round 9 - 2026-01-01\n\nsome prose\n"),
            ("bad severity", ROUND_TEMPLATE.format(n=9, date="2026-09-01", rows="| R9-1 | critical | 2.7 | x | fixed | y |")),
            ("bad status", ROUND_TEMPLATE.format(n=9, date="2026-09-01", rows="| R9-1 | high | 2.7 | x | pending | y |")),
            ("wrong cell count", ROUND_TEMPLATE.format(n=9, date="2026-09-01", rows="| R9-1 | high | 2.7 |")),
            ("duplicate id in round", ROUND_TEMPLATE.format(
                n=9, date="2026-09-01", rows="| R9-1 | high | 2.7 | x | fixed | a |\n| R9-1 | low | 2.7 | x | fixed | b |")),
        ]
        for label, text_bad in malformed:
            try:
                parse_round(text_bad, source="<selfcheck>")
                print(f"[rounds] SELFCHECK FAILED: parser accepted {label}",
                      file=sys.stderr)
                ok = False
            except RoundError:
                pass

        # A duplicated round number would silently reorder history.
        (tmp / "dupe.md").write_text(ROUND_TEMPLATE.format(n=1, date="2026-01-01", rows=""))
        try:
            load_rounds(tmp)
            print("[rounds] SELFCHECK FAILED: two records claimed the same round",
                  file=sys.stderr)
            ok = False
        except RoundError:
            pass

        # ── the backflow gate ────────────────────────────────────────────
        # Planted known-bad cases, because the gate's whole value is that an
        # undecided item eventually costs something. A gate that always
        # answered OK would restore R7-1 exactly.
        head = ("## The register\n\n| " + " | ".join(BACKFLOW_COLUMNS) +
                " |\n|" + "|".join(["---"] * len(BACKFLOW_COLUMNS)) + "|\n")

        def _bf(row: str) -> list[BackflowItem]:
            return parse_backflow(head + row + "\n")

        overdue = _bf("| B-1 | T | a thing | scar | 2.1 | owed | 5 | |")
        if not backflow_problems(overdue, latest_round=5, all_rules={"2.1"}):
            print("[rounds] SELFCHECK FAILED: an item owed past its round "
                  "did not fail the gate", file=sys.stderr)
            ok = False
        if backflow_problems(overdue, latest_round=4, all_rules={"2.1"}):
            print("[rounds] SELFCHECK FAILED: an item not yet due was "
                  "reported as overdue", file=sys.stderr)
            ok = False

        founding = _bf("| B-1 | T | a thing | practice | new | owed | 99 | |")
        if not backflow_problems(founding, latest_round=1, all_rules=set()):
            print("[rounds] SELFCHECK FAILED: a `practice` item was allowed "
                  "to found a new rule (8.1)", file=sys.stderr)
            ok = False

        # A row it cannot read must be refused, never skipped (2.9).
        try:
            _bf("| B-1 | T | a | b | thing | scar | 2.1 | owed | 99 | |")
            print("[rounds] SELFCHECK FAILED: a malformed register row was "
                  "skipped instead of refused", file=sys.stderr)
            ok = False
        except RoundError:
            pass

        # ── the scar admission gate ──────────────────────────────────────
        # Planted known-bad cases, because this gate's whole value is that a
        # mechanism entering on argument alone eventually costs something. A
        # gate that always answered OK would be the habit it replaced.
        known_findings = {"R10-1"}

        def _scar(front: str) -> ScarCitation:
            return parse_scar(f"---\n{front}---\n\n# Design note: planted\n",
                              source="<selfcheck>")

        if scar_problems([_scar("sutradhar_scar: R10-1\n")], known_findings):
            print("[rounds] SELFCHECK FAILED: a note citing a finding that "
                  "exists in the records was refused", file=sys.stderr)
            ok = False

        if not scar_problems([_scar("sutradhar_scar: R99-9\n")], known_findings):
            print("[rounds] SELFCHECK FAILED: a note cited a finding id no "
                  "round record contains and the gate passed it. An id "
                  "nobody can resolve reads as provenance and carries none",
                  file=sys.stderr)
            ok = False

        for label, front in (
            ("no scar key at all", "sutradhar_budget: planted\n"),
            ("`distribution` with no argument", "sutradhar_scar: distribution\n"),
        ):
            try:
                _scar(front)
                print(f"[rounds] SELFCHECK FAILED: accepted a design note with "
                      f"{label}", file=sys.stderr)
                ok = False
            except RoundError:
                pass

        honest = _scar("sutradhar_scar: distribution\n"
                       "sutradhar_scar_argument: adopters need a worked example\n")
        if not honest.distribution or scar_problems([honest], known_findings):
            print("[rounds] SELFCHECK FAILED: an honest distribution admission "
                  "carrying its argument was refused; the gate must leave a "
                  "way to say it out loud", file=sys.stderr)
            ok = False

    if ok:
        print(
            "[rounds] selfcheck ok: records parsed, stop rule converges, residual "
            "register held, attribution refused below the evidence floor, "
            "backflow gate bites on an overdue item, scar gate refuses a design "
            "note that names no incident"
        )
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--check", "--doctrine", "--floors", "--selfcheck", "--help", "-h",
                "--backflow", "--designs"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    doctrine = "DOCTRINE.md"
    floors_root = None
    backflow_path = None
    designs_root = None
    check_only = "--check" in argv
    positional: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--doctrine":
            doctrine = argv[i + 1]; i += 2
        elif argv[i] == "--floors":
            floors_root = argv[i + 1]; i += 2
        elif argv[i] == "--backflow":
            backflow_path = argv[i + 1]; i += 2
        elif argv[i] == "--designs":
            designs_root = argv[i + 1]; i += 2
        elif argv[i].startswith("--"):
            # An unrecognised flag must NOT be ignored. Silently
            # skipping it means a typo like `--selfchek` runs the
            # default scan and exits 0, which reads as a pass.
            if argv[i] not in _KNOWN_FLAGS:
                print(
                    f"[rounds] unknown flag: {argv[i]}", file=sys.stderr
                )
                return 2
            i += 1
        else:
            positional.append(argv[i]); i += 1
    root = positional[0] if positional else "docs/rounds"

    if not selfcheck():
        return 1

    if not Path(root).exists():
        print(f"[rounds] no round records at {root}. The robustness loop's "
              f"phase 6 writes them; see the module docstring for the format.")
        return 2
    try:
        rounds = load_rounds(root)
    except RoundError as exc:
        print(f"\n[rounds] {exc}\n")
        return 1
    if not rounds:
        print(f"[rounds] no round records found under {root}.")
        return 2

    all_rules = doctrine_rule_ids(doctrine) if Path(doctrine).exists() else set()
    unknown = rule_attribution(rounds, all_rules)["unknown_rules"] if all_rules else []
    if unknown:
        print(f"\n[rounds] finding(s) cite rule id(s) not in {doctrine}: "
              f"{', '.join(unknown)}.\n  A mistyped rule id silently loses the "
              f"attribution 8.1 depends on.\n")
        return 1

    if backflow_path is not None:
        bf = Path(backflow_path)
        if not bf.exists():
            # Not a pass. A register that is not there has told us nothing
            # about what is owed - the same silence as a register full of
            # undecided items, which is what this gate exists to break.
            print(f"\n[rounds] no backflow register at {bf}. Asked to check "
                  f"one and found none; nothing was checked.\n")
            return 2
        try:
            items = parse_backflow(bf.read_text(encoding="utf-8"), source=str(bf))
        except RoundError as exc:
            print(f"\n[rounds] {exc}\n")
            return 1
        if not items:
            print(f"\n[rounds] {bf} has no register rows. An empty register "
                  f"and a satisfied one look identical from here, so this is "
                  f"a refusal rather than a pass.\n")
            return 2
        latest = max(r.number for r in rounds)
        problems = backflow_problems(items, latest, all_rules)
        if problems:
            print(f"\n[rounds] backflow register: {len(problems)} item(s) "
                  f"need a decision\n")
            print("\n".join(problems))
            print()
            return 1
        by_status = {st: sum(1 for i in items if i.status == st)
                     for st in BACKFLOW_STATUSES}
        print(f"[rounds] backflow OK - {len(items)} item(s): "
              + ", ".join(f"{n} {st}" for st, n in by_status.items() if n))

    if designs_root is not None:
        droot = Path(designs_root)
        notes = load_design_notes(droot) if droot.exists() else []
        if not notes:
            # Not a pass. Asked which incident paid for each mechanism and
            # given nothing to read, the honest answer is "I did not check",
            # and 2.9 says that is not the same as "they all passed".
            missing = "no design notes directory" if not droot.exists() else \
                      "no design notes"
            print(f"\n[rounds] {missing} at {droot}. Asked to check the scar "
                  f"each note cites and found none; nothing was checked.\n")
            return 2
        citations: list[ScarCitation] = []
        try:
            for note in notes:
                citations.append(parse_scar(
                    note.read_text(encoding="utf-8", errors="replace"),
                    source=str(note),
                ))
        except RoundError as exc:
            print(f"\n[rounds] {exc}\n")
            return 1
        known_findings = {f.id for r in rounds for f in r.findings}
        problems = scar_problems(citations, known_findings)
        if problems:
            print(f"\n[rounds] design note(s) cite {len(problems)} finding id(s) "
                  f"no round record contains\n")
            print("\n".join(problems))
            print()
            return 1
        on_scars = sum(1 for c in citations if c.findings)
        on_distribution = sum(1 for c in citations if c.distribution)
        print(f"[rounds] scars OK - {len(notes)} note(s), {on_scars} cite "
              f"finding(s), {on_distribution} enter on distribution")

    if check_only:
        print(f"[rounds] OK - {len(rounds)} record(s) valid, "
              f"{sum(len(r.findings) for r in rounds)} finding(s), rule ids known")
        return 0

    floors = sample_floors(floors_root) if floors_root else None
    print(report(rounds, all_rules, floors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
