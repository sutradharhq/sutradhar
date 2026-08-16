"""obsgate - the observability floor as a provenance gate (doctrine 6.6).

A claim about a running system is worth exactly what the surface that
witnessed it is worth. This tool checks the surface, not the system: given
a metrics payload (Prometheus text format, from a file or an endpoint) and
a declared floor, it answers whether every surface a claim will later lean
on actually has live series behind it.

The incident that earned it, twice over: a verification read a queryable
proxy repeatedly while the surface that mattered disagreed throughout
(round 3); a review read exit 0 from five selfchecks that did not exist
(round 4). Both times the proxy agreed, so the looking stopped. The gate
exists so that "observable" is a checked claim, not a believed one.

Usage:

  python obsgate.py --metrics http://localhost:9090/metrics --floor obs_floor.json
  python obsgate.py --metrics metrics.txt --floor obs_floor.json
  python obsgate.py --selfcheck

The floor manifest is JSON, one entry per surface the floor requires:

  {
    "surfaces": [
      {"name": "requests",
       "pattern": "^http_requests_(total|duration_.*)$",
       "min_series": 1,
       "max_label_cardinality": {"route": 200}},
      {"name": "jobs",     "pattern": "^jobs_(fired|succeeded|failed)_total$"},
      {"name": "ingest",   "pattern": "^ingest_lag_seconds$"},
      {"name": "deps",     "pattern": "^dependency_up$", "min_series": 2}
    ]
  }

`max_label_cardinality` mechanises the by-route-template-never-raw-path
line: a `route` label carrying every raw URL blows past any honest cap and
is a memory bomb in the metrics store (the 1.1 class, relocated).

Verdicts are tri-state, and the third state is the point:

  WITNESSED     every declared surface has live series within bounds
  UNWITNESSED   the payload was READ and a surface is missing, empty, or
                past its cardinality cap - including the empty-200 case,
                which is a lie, not an absence
  INCONCLUSIVE  the payload could not be read at all. Not a pass. A dead
                endpoint witnesses nothing, and reporting it as anything
                other than "could not tell" is the round-3 mistake again.

Exit codes: 0 WITNESSED, 1 UNWITNESSED, 2 usage error, 3 INCONCLUSIVE.
Stdlib only, copy-in like everything else here.
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

WITNESSED = "WITNESSED"
UNWITNESSED = "UNWITNESSED"
INCONCLUSIVE = "INCONCLUSIVE"

_SAMPLE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)"      # metric name
    r"(?:\{(.*)\})?"                    # optional {labels}
    r"\s+(-?[0-9.eE+\-]+|NaN|[+-]Inf)"  # value
    r"(?:\s+\d+)?$"                     # optional timestamp
)
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


@dataclass
class Sample:
    name: str
    labels: dict
    value: float


@dataclass
class FloorResult:
    verdict: str
    violations: list = field(default_factory=list)
    series_seen: int = 0

    def report(self) -> str:
        lines = [f"[obsgate] {self.verdict} ({self.series_seen} series read)"]
        lines += [f"  - {v}" for v in self.violations]
        return "\n".join(lines)


def parse_metrics(text: str) -> list[Sample]:
    """Parse Prometheus text exposition format. Lenient on purpose about
    lines it does not understand - a parser that dies on one exotic line
    would report an entire live surface as absent - but strict about what
    it accepts as a sample."""
    samples: list[Sample] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SAMPLE_RE.match(line)
        if not m:
            continue
        name, labelstr, value = m.group(1), m.group(2), m.group(3)
        labels = dict(_LABEL_RE.findall(labelstr)) if labelstr else {}
        try:
            samples.append(Sample(name, labels, float(value)))
        except ValueError:
            continue
    return samples


def load_floor(path: str | Path) -> list[dict]:
    """Read and validate the floor manifest. A malformed manifest raises;
    a gate that shrugged at its own configuration would pass vacuously on
    the day the manifest rotted (the R2-1 class)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"floor manifest unreadable: {exc}") from exc
    surfaces = data.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError(
            "floor manifest has no 'surfaces' list - an empty floor gates "
            "nothing, declare at least one surface or do not run the gate"
        )
    for s in surfaces:
        if not isinstance(s, dict) or "pattern" not in s or "name" not in s:
            raise ValueError(f"surface entry needs 'name' and 'pattern': {s!r}")
        try:
            re.compile(s["pattern"])
        except re.error as exc:
            raise ValueError(f"surface {s['name']!r} pattern invalid: {exc}") from exc
    return surfaces


def check_floor(samples: list[Sample], surfaces: list[dict]) -> FloorResult:
    """The gate. Empty payload fails loudly: an endpoint that answers with
    nothing has not reported zero traffic, it has reported nothing, and
    those must never read the same."""
    if not samples:
        return FloorResult(
            UNWITNESSED,
            ["payload contains no series at all - an empty 200 reads as "
             '"all zero" to every consumer, which is a fabricated claim, '
             "not an absence of one (doctrine 2.4)"],
            0,
        )

    violations: list[str] = []
    for surface in surfaces:
        pat = re.compile(surface["pattern"])
        matched = [s for s in samples if pat.search(s.name)]
        needed = int(surface.get("min_series", 1))
        if len(matched) < needed:
            violations.append(
                f"surface {surface['name']!r}: {len(matched)} series match "
                f"{surface['pattern']!r}, floor requires {needed} - any claim "
                f"about this surface is currently unwitnessable"
            )
            continue
        for label, cap in (surface.get("max_label_cardinality") or {}).items():
            values = {s.labels[label] for s in matched if label in s.labels}
            if len(values) > int(cap):
                sample_vals = ", ".join(sorted(values)[:3])
                violations.append(
                    f"surface {surface['name']!r}: label {label!r} carries "
                    f"{len(values)} distinct values (cap {cap}) - raw paths "
                    f"where route templates belong (e.g. {sample_vals}, ...); "
                    f"this is the unbounded-cardinality memory bomb"
                )

    verdict = UNWITNESSED if violations else WITNESSED
    return FloorResult(verdict, violations, len(samples))


def read_payload(source: str, timeout: float = 10.0) -> tuple[str | None, str]:
    """Fetch the metrics text. Returns (text, "") or (None, why) - the
    caller maps failure to INCONCLUSIVE, never to a pass or a fail."""
    if source.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(source, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace"), ""
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return None, f"endpoint unreadable: {exc}"
    try:
        return Path(source).read_text(encoding="utf-8"), ""
    except OSError as exc:
        return None, f"file unreadable: {exc}"


def gate(source: str, floor_path: str | Path, timeout: float = 10.0) -> FloorResult:
    """One-call form: fetch, parse, check. Library twin of the CLI."""
    surfaces = load_floor(floor_path)
    text, why = read_payload(source, timeout)
    if text is None:
        return FloorResult(INCONCLUSIVE, [why + " - witnessed nothing; this is "
                                          "not a pass and must not be reported "
                                          "as one"], 0)
    return check_floor(parse_metrics(text), surfaces)


# ── selfcheck ───────────────────────────────────────────────────────────────

_GOOD_PAYLOAD = """\
# HELP http_requests_total requests by route template
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
jobs_fired_total 40
jobs_succeeded_total 38
jobs_failed_total 2
ingest_lag_seconds 1.4
dependency_up{dep="db"} 1
dependency_up{dep="queue"} 0
"""

_FLOOR = [
    {"name": "requests", "pattern": "^http_requests_total$",
     "max_label_cardinality": {"route": 50}},
    {"name": "jobs", "pattern": "^jobs_(fired|succeeded|failed)_total$",
     "min_series": 3},
    {"name": "ingest", "pattern": "^ingest_lag_seconds$"},
    {"name": "deps", "pattern": "^dependency_up$", "min_series": 2},
]


def selfcheck() -> bool:
    """Every verdict is exercised, and the two refusals are the point:
    an empty payload must FAIL and an unreadable source must be
    INCONCLUSIVE. A gate that read a dead endpoint as WITNESSED would be
    the round-3 proxy mistake shipped as a tool."""
    import tempfile

    ok = True

    def _fail(msg: str) -> None:
        nonlocal ok
        print(f"[obsgate] SELFCHECK FAILED: {msg}")
        ok = False

    samples = parse_metrics(_GOOD_PAYLOAD)
    if len(samples) != 8:
        _fail(f"parser read {len(samples)} of 8 planted samples")
    by_name = {}
    for s in samples:
        by_name.setdefault(s.name, []).append(s)
    if by_name.get("http_requests_total", [None])[0] and \
       by_name["http_requests_total"][0].labels.get("route") != "/api/users/:id":
        _fail("labels not parsed from a planted sample")

    res = check_floor(samples, _FLOOR)
    if res.verdict != WITNESSED:
        _fail(f"a complete floor reported {res.verdict}: {res.violations}")

    res = check_floor([], _FLOOR)
    if res.verdict != UNWITNESSED:
        _fail(f"an EMPTY payload reported {res.verdict} - the empty-200 lie "
              f"passed the gate built to catch it")
    elif not any("no series at all" in v for v in res.violations):
        # The verdict alone is not enough: with the dedicated empty-payload
        # branch blinded, per-surface misses still say UNWITNESSED, and the
        # one diagnosis that names the lie ("empty 200 reads as all zero")
        # is silently gone. Assert the reason, not just the outcome - the
        # first mutation run survived on exactly this gap.
        _fail(f"an empty payload was refused for the wrong reason: "
              f"{res.violations}")

    partial = [s for s in samples if not s.name.startswith("jobs_")]
    res = check_floor(partial, _FLOOR)
    if res.verdict != UNWITNESSED or not any("jobs" in v for v in res.violations):
        _fail(f"a missing surface was not named: {res.verdict} {res.violations}")

    bomb = parse_metrics(_GOOD_PAYLOAD) + [
        Sample("http_requests_total", {"route": f"/api/users/{i}", "method": "GET"}, 1.0)
        for i in range(60)
    ]
    res = check_floor(bomb, _FLOOR)
    if res.verdict != UNWITNESSED or not any("cardinality" in v or "distinct" in v
                                             for v in res.violations):
        _fail(f"a raw-path cardinality bomb passed: {res.verdict}")

    with tempfile.TemporaryDirectory() as td:
        floor_path = Path(td) / "floor.json"
        floor_path.write_text(json.dumps({"surfaces": _FLOOR}))

        res = gate(str(Path(td) / "no-such-file.txt"), floor_path)
        if res.verdict != INCONCLUSIVE:
            _fail(f"an unreadable source reported {res.verdict}, not "
                  f"INCONCLUSIVE - a dead endpoint must never read as a pass")

        res = gate("http://127.0.0.1:1/metrics", floor_path, timeout=0.5)
        if res.verdict != INCONCLUSIVE:
            _fail(f"a dead endpoint reported {res.verdict}, not INCONCLUSIVE")

        good_path = Path(td) / "metrics.txt"
        good_path.write_text(_GOOD_PAYLOAD)
        res = gate(str(good_path), floor_path)
        if res.verdict != WITNESSED:
            _fail(f"end-to-end on a good payload reported {res.verdict}")

        try:
            load_floor(Path(td) / "absent.json")
            _fail("an unreadable manifest was accepted")
        except ValueError:
            pass
        bad = Path(td) / "empty.json"
        bad.write_text('{"surfaces": []}')
        try:
            load_floor(bad)
            _fail("an EMPTY floor was accepted - it would gate nothing forever")
        except ValueError:
            pass

    if ok:
        print(
            "[obsgate] selfcheck ok: floor witnessed, empty payload refused, "
            "missing surface named, cardinality bomb caught, dead endpoint "
            "INCONCLUSIVE, empty floor refused"
        )
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

_KNOWN_FLAGS = {"--metrics", "--floor", "--timeout", "--selfcheck", "--help", "-h"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0

    source, floor_path, timeout = None, None, 10.0
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--metrics":
            source = argv[i + 1]; i += 2
        elif a == "--floor":
            floor_path = argv[i + 1]; i += 2
        elif a == "--timeout":
            timeout = float(argv[i + 1]); i += 2
        elif a.startswith("--"):
            if a not in _KNOWN_FLAGS:
                print(f"[obsgate] unknown flag: {a}", file=sys.stderr)
                return 2
            i += 1
        else:
            print(f"[obsgate] unexpected argument: {a}", file=sys.stderr)
            return 2

    if not source or not floor_path:
        print("[obsgate] need both --metrics <file-or-url> and --floor "
              "<manifest.json> (or --selfcheck)", file=sys.stderr)
        return 2

    if not selfcheck():
        return 1

    try:
        result = gate(source, floor_path, timeout)
    except ValueError as exc:
        print(f"[obsgate] {exc}", file=sys.stderr)
        return 2
    print(result.report())
    return {WITNESSED: 0, UNWITNESSED: 1, INCONCLUSIVE: 3}[result.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
