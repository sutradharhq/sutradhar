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

`severity` is high/med/low, `status` is fixed/deferred/closed, and `rule` is
a doctrine id (`2.7`) or `-`. A deferred finding stays in the residual
register until a later round lists the same id as closed or fixed.

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
from pathlib import Path

SEVERITIES = ("high", "med", "low")
STATUSES = ("fixed", "deferred", "closed")
COLUMNS = ("id", "severity", "rule", "found-by", "status", "summary")

_HEADING = re.compile(r"^#\s+Round\s+(\d+)\s*[-–—]\s*(\d{4}-\d{2}-\d{2})\s*$",
                      re.MULTILINE)
_LENSES = re.compile(r"^Lenses:\s*(.+)$", re.IGNORECASE)
_DOCTRINE_RULE = re.compile(r"^\*\*(\d+\.\d+)\s")
# "Thin data" floor: below this many rounds, an attribution claim is noise.
MIN_ROUNDS_FOR_ATTRIBUTION = 5


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
                   and f.status != "closed")

    def new_findings(self) -> list[Finding]:
        """Findings this round surfaced, excluding bookkeeping rows that
        merely close an earlier deferral."""
        return [f for f in self.findings if f.status != "closed"]


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
    """Deferred findings never subsequently closed or fixed."""
    open_items: dict[str, Finding] = {}
    for rnd in rounds:
        for f in rnd.findings:
            if f.status == "deferred":
                open_items[f.id] = f
            elif f.status in ("closed", "fixed") and f.id in open_items:
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
    """
    last_seen: dict[str, int] = {}
    saves: dict[str, int] = {}
    counted: set[str] = set()
    for rnd in rounds:
        for f in rnd.new_findings():
            if f.rule and f.id not in counted:
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
    if len(rounds) < MIN_ROUNDS_FOR_ATTRIBUTION:
        out.append(
            f"    deletion candidates: NOT REPORTED. {len(rounds)} round(s) is "
            f"too thin to conclude a rule earns nothing; 8.1 asks for months of "
            f"silence, not a quiet week. Needs {MIN_ROUNDS_FOR_ATTRIBUTION}+."
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

ROUND_TEMPLATE = """# Round {n} - 2026-0{n}-01

Lenses: authz, scale

| id | severity | rule | found-by | status | summary |
|---|---|---|---|---|---|
{rows}
"""


def _plant(tmp: Path, n: int, rows: list[str]) -> None:
    (tmp / f"round-{n:03d}.md").write_text(
        ROUND_TEMPLATE.format(n=n, rows="\n".join(rows))
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
            ("bad severity", ROUND_TEMPLATE.format(n=9, rows="| R9-1 | critical | 2.7 | x | fixed | y |")),
            ("bad status", ROUND_TEMPLATE.format(n=9, rows="| R9-1 | high | 2.7 | x | pending | y |")),
            ("wrong cell count", ROUND_TEMPLATE.format(n=9, rows="| R9-1 | high | 2.7 |")),
            ("duplicate id in round", ROUND_TEMPLATE.format(
                n=9, rows="| R9-1 | high | 2.7 | x | fixed | a |\n| R9-1 | low | 2.7 | x | fixed | b |")),
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
        (tmp / "dupe.md").write_text(ROUND_TEMPLATE.format(n=1, rows=""))
        try:
            load_rounds(tmp)
            print("[rounds] SELFCHECK FAILED: two records claimed the same round",
                  file=sys.stderr)
            ok = False
        except RoundError:
            pass
    if ok:
        print(
            "[rounds] selfcheck ok: records parsed, stop rule converges, residual "
            "register held, attribution refused below the evidence floor"
        )
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--check", "--doctrine", "--floors", "--selfcheck", "--help", "-h"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    if "--selfcheck" in argv:
        return 0 if selfcheck() else 1

    doctrine = "DOCTRINE.md"
    floors_root = None
    check_only = "--check" in argv
    positional: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--doctrine":
            doctrine = argv[i + 1]; i += 2
        elif argv[i] == "--floors":
            floors_root = argv[i + 1]; i += 2
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

    if check_only:
        print(f"[rounds] OK - {len(rounds)} record(s) valid, "
              f"{sum(len(r.findings) for r in rounds)} finding(s), rule ids known")
        return 0

    floors = sample_floors(floors_root) if floors_root else None
    print(report(rounds, all_rules, floors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
