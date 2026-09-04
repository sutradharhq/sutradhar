"""obsgate - the observability floor as a provenance gate (doctrine 6.6).

A claim about a running system is worth exactly what the surface that
witnessed it is worth. This tool checks the surface, not the system: given
a metrics payload (Prometheus text format, from a file or an endpoint) and
a declared floor, it answers whether every surface a claim will later lean
on actually has live series behind it - and, since round 12, whether a
change you made can actually be SEEN there.

The incident that earned it, twice over: a verification read a queryable
proxy repeatedly while the surface that mattered disagreed throughout
(round 3); a review read exit 0 from five selfchecks that did not exist
(round 4). Both times the proxy agreed, so the looking stopped. The gate
exists so that "observable" is a checked claim, not a believed one.

Usage:

  # 1. the floor: does the surface exist at all (unchanged, still the default)
  python obsgate.py --metrics http://localhost:9090/metrics --floor obs_floor.json
  python obsgate.py check --metrics metrics.txt --floor obs_floor.json
  python obsgate.py check --metrics http://svc/metrics --floor f.json \
                          --samples 3 --interval-ms 500      # frozen-exporter probe

  # 2. snapshot: a deterministic digest of the surface at a moment
  python obsgate.py snapshot --metrics http://svc/metrics --out before.json
  ...do the thing...
  python obsgate.py snapshot --metrics http://svc/metrics --out after.json

  # 3. effects: was the change WITNESSED (doctrine 6.6, mechanised)
  python obsgate.py effects --before before.json --after after.json \
                            --floor obs_floor.json

  python obsgate.py --selfcheck

The floor manifest is JSON: one entry per surface the floor requires, plus
an optional `effects` list saying what a change must be seen to do.

  {
    "surfaces": [
      {"name": "requests",
       "pattern": "^http_requests_(total|duration_.*)$",
       "min_series": 1,
       "max_label_cardinality": {"route": 200}},
      {"name": "jobs",     "pattern": "^jobs_(fired|succeeded|failed)_total$"},
      {"name": "ingest",   "pattern": "^ingest_lag_seconds$"},
      {"name": "deps",     "pattern": "^dependency_up$", "min_series": 2}
    ],
    "effects": [
      {"kind": "increased", "family": "http_requests_total", "min_delta": 1},
      {"kind": "appeared",  "family": "http_requests_total",
       "label": "route", "value": "/api/exports"},
      {"kind": "no_vanished_series"},
      {"kind": "stable_labels", "family": "http_requests_total"}
    ]
  }

`max_label_cardinality` mechanises the by-route-template-never-raw-path
line: a `route` label carrying every raw URL blows past any honest cap and
is a memory bomb in the metrics store (the 1.1 class, relocated).

Floor verdicts are tri-state, and the third state is the point:

  WITNESSED     every declared surface has live series within bounds
  UNWITNESSED   the payload was READ and a surface is missing, empty, or
                past its cardinality cap - including the empty-200 case,
                which is a lie, not an absence
  FROZEN        the floor is met and the endpoint served byte-identical
                bytes across every sample while declaring counters that
                must move. Stale truth wearing a 200. Its own word on
                purpose: filing it as UNWITNESSED would send the reader
                to add metrics that already exist (doctrine 2.4)
  INCONCLUSIVE  the payload could not be read at all. Not a pass. A dead
                endpoint witnesses nothing, and reporting it as anything
                other than "could not tell" is the round-3 mistake again.

Effect verdicts, one per declared effect:

  WITNESSED       the effect is visible in the before/after pair
  NOT_WITNESSED   it is not, and the message names the DIRECTION
                  (expected-increase-but-fell, expected-appear-but-absent,
                  ...) because a miss without a direction is a verdict
                  whose word is wrong (doctrine 2.4)
  COUNTER_RESET   a counter family's sum FELL. That is not a decline, it
                  is a restart, and it has its own name because the fix
                  is a different fix
  UNANSWERABLE    the snapshots cannot answer. Never a pass, never a
                  generic failure - the honest third state again

Every failure message names WHICH OF THREE PARTIES failed:

  instrument:  obsgate itself (bad flag, parser raised, snapshot cap hit)
  endpoint:    the metrics surface (unreachable, empty, frozen, vanished)
  floor:       the surface is fine, the declaration is not met

*Scar (doctrine 6.4): a polling loop printed ten "no response" lines about
a production API that was serving 200s in 0.27s, because a backslash in an
f-string raised and a shell `||` fallback spoke on the server's behalf. An
instrument that cannot say whose failure it is always blames the system.*

Exit codes: 0 pass, 1 UNWITNESSED / an effect not witnessed, 2 instrument
or usage failure, 3 INCONCLUSIVE / endpoint unreadable, 4 FROZEN.
Stdlib only, copy-in like everything else here.

Design note: docs/design/obsgate-depth.md (budgets, failure story, non-goals).
"""
# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

WITNESSED = "WITNESSED"
UNWITNESSED = "UNWITNESSED"
INCONCLUSIVE = "INCONCLUSIVE"
FROZEN = "FROZEN"

NOT_WITNESSED = "NOT_WITNESSED"
COUNTER_RESET = "COUNTER_RESET"
UNANSWERABLE = "UNANSWERABLE"

# The three parties. Nothing this tool prints is allowed to be unattributed.
INSTRUMENT = "instrument"
ENDPOINT = "endpoint"
FLOOR = "floor"

SNAPSHOT_VERSION = 1
# Doctrine 2.6, aimed at this tool's own output: a snapshot that recorded
# every distinct label value would rebuild the cardinality bomb inside the
# snapshot file. Past the cap the snapshot records that it STOPPED LOOKING,
# and questions about that key answer UNANSWERABLE rather than guessing.
LABEL_VALUE_CAP = 64

EFFECT_KINDS = ("increased", "appeared", "no_vanished_series", "stable_labels")

_SAMPLE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)"      # metric name
    r"(?:\{(.*)\})?"                    # optional {labels}
    r"\s+(-?[0-9.eE+\-]+|NaN|[+-]Inf)"  # value
    r"(?:\s+\d+)?$"                     # optional timestamp
)
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')
_TYPE_RE = re.compile(r"^#\s*TYPE\s+([a-zA-Z_:][a-zA-Z0-9_:]*)\s+([a-zA-Z]+)\s*$")


class UsageError(ValueError):
    """A caller mistake or an obsgate mistake. Party: instrument."""


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
    notes: list = field(default_factory=list)
    samples_taken: int = 1

    def report(self) -> str:
        head = f"[obsgate] {self.verdict} ({self.series_seen} series read"
        if self.samples_taken > 1:
            head += f", {self.samples_taken} samples"
        head += ")"
        lines = [head]
        lines += [f"  - {v}" for v in self.violations]
        lines += [f"  . {n}" for n in self.notes]
        return "\n".join(lines)


@dataclass
class EffectResult:
    kind: str
    subject: str      # what the effect is about, for the report
    verdict: str
    party: str        # "" when WITNESSED
    detail: str

    @property
    def ok(self) -> bool:
        return self.verdict == WITNESSED

    def line(self) -> str:
        head = f"{self.verdict:<14} {self.kind} {self.subject}"
        body = self.detail if self.ok else f"{self.party}: {self.detail}"
        return f"{head}\n      {body}"


@dataclass
class EffectsResult:
    results: list = field(default_factory=list)

    @property
    def witnessed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def all_ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    def report(self) -> str:
        lines = [f"[obsgate] effects: {self.witnessed} of {len(self.results)} "
                 f"witnessed"]
        lines += [f"  - {r.line()}" for r in self.results]
        return "\n".join(lines)


# ── parsing ─────────────────────────────────────────────────────────────────

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


def parse_types(text: str) -> dict:
    """The `# TYPE` lines. A counter is the only family for which "the
    number went down" has a second meaning (a restart), so the type is not
    decoration - it is what separates COUNTER_RESET from a plain fall."""
    types: dict = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("#"):
            continue
        m = _TYPE_RE.match(line)
        if m:
            types[m.group(1)] = m.group(2).lower()
    return types


def type_for(name: str, types: dict) -> str:
    """Resolve a family's type, including the children a histogram or
    summary declares under its base name (`foo_bucket` is `foo`'s type),
    and the OpenMetrics spelling where `# TYPE foo counter` exposes
    `foo_total`."""
    if name in types:
        return types[name]
    for suffix in ("_bucket", "_sum", "_count"):
        if name.endswith(suffix) and types.get(name[: -len(suffix)]) in (
            "histogram", "summary"
        ):
            return types[name[: -len(suffix)]]
    if name.endswith("_total") and types.get(name[:-6]) == "counter":
        return "counter"
    return "untyped"


def looks_like_counter(name: str, mtype: str) -> bool:
    """Typed counter, or the `_total` convention when the exporter shipped
    no `# TYPE` lines at all - which is common and must not silently turn
    the frozen check off."""
    return mtype == "counter" or name.endswith("_total")


def safe_parse(text: str, parser=parse_metrics) -> tuple[list, str]:
    """Run the parser inside a narrow blast radius (doctrine 2.4 + 6.4).

    Returns (samples, "") or ([], why) where `why` is attributed to the
    INSTRUMENT and names the exception TYPE. This branch exists so that a
    crash in obsgate's own parser can never be printed as a claim about
    someone else's server - which is exactly the scar in the module
    docstring. `parser` is injectable so the selfcheck can plant a raising
    parser and prove the branch says "instrument", not "endpoint".
    """
    try:
        return parser(text), ""
    except Exception as exc:  # noqa: BLE001 - deliberately the outer wall
        return [], (
            f"{INSTRUMENT}: the metrics parser raised "
            f"{type(exc).__name__}: {exc}. This is obsgate's failure and is "
            f"NOT evidence about the endpoint - the surface may be perfectly "
            f"healthy. Do not report an outage from this line (doctrine 6.4)"
        )


# ── the floor manifest ──────────────────────────────────────────────────────

def _validate_effects(effects) -> list:
    """An effect this tool cannot check must be REFUSED, not skipped. A
    skipped effect is a silent pass, which is the disease the whole gate
    exists to treat (doctrine 2.4)."""
    if not isinstance(effects, list) or not effects:
        raise UsageError(
            f"{INSTRUMENT}: floor manifest has an 'effects' key that is not a "
            f"non-empty list - an empty effects list witnesses nothing; delete "
            f"the key or declare an effect"
        )
    for e in effects:
        if not isinstance(e, dict):
            raise UsageError(f"{INSTRUMENT}: effect entry is not an object: {e!r}")
        kind = e.get("kind")
        if kind not in EFFECT_KINDS:
            raise UsageError(
                f"{INSTRUMENT}: effect kind {kind!r} is not one of "
                f"{', '.join(EFFECT_KINDS)}. An unknown kind is refused rather "
                f"than skipped: a skipped effect passes vacuously"
            )
        if kind in ("increased", "appeared") and not isinstance(e.get("family"), str):
            raise UsageError(
                f"{INSTRUMENT}: effect {kind!r} needs a 'family' string: {e!r}"
            )
        if kind == "appeared" and (("label" in e) != ("value" in e)):
            raise UsageError(
                f"{INSTRUMENT}: effect 'appeared' takes 'label' and 'value' "
                f"together or neither: {e!r}"
            )
        if kind == "increased" and "min_delta" in e:
            try:
                float(e["min_delta"])
            except (TypeError, ValueError):
                raise UsageError(
                    f"{INSTRUMENT}: min_delta={e['min_delta']!r} is not a number"
                ) from None
        if kind == "no_vanished_series" and "allow" in e:
            if not isinstance(e["allow"], list) or not all(
                isinstance(x, str) for x in e["allow"]
            ):
                raise UsageError(
                    f"{INSTRUMENT}: no_vanished_series 'allow' must be a list of "
                    f"family names: {e!r}"
                )
        if kind == "stable_labels" and "family" in e and not isinstance(
            e["family"], str
        ):
            raise UsageError(f"{INSTRUMENT}: stable_labels 'family' must be a string")
    return effects


def load_floor_doc(path: str | Path) -> dict:
    """Read and validate the whole manifest. A malformed manifest raises;
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
    effects = data.get("effects")
    if effects is not None:
        _validate_effects(effects)
    return {"surfaces": surfaces, "effects": effects}


def load_floor(path: str | Path) -> list[dict]:
    """The surfaces list. Unchanged signature: this is the seam every
    existing caller uses."""
    return load_floor_doc(path)["surfaces"]


def load_effects(path: str | Path) -> list:
    """The declared effects, or [] when the manifest declares none. The
    caller must treat [] as a REFUSAL, not as "all effects passed"."""
    return load_floor_doc(path)["effects"] or []


# ── the floor check ─────────────────────────────────────────────────────────

def check_floor(samples: list[Sample], surfaces: list[dict]) -> FloorResult:
    """The gate. Empty payload fails loudly: an endpoint that answers with
    nothing has not reported zero traffic, it has reported nothing, and
    those must never read the same."""
    if not samples:
        return FloorResult(
            UNWITNESSED,
            [f"{ENDPOINT}: payload contains no series at all - an empty 200 "
             'reads as "all zero" to every consumer, which is a fabricated '
             "claim, not an absence of one (doctrine 2.4)"],
            0,
        )

    violations: list[str] = []
    for surface in surfaces:
        pat = re.compile(surface["pattern"])
        matched = [s for s in samples if pat.search(s.name)]
        needed = int(surface.get("min_series", 1))
        if len(matched) < needed:
            violations.append(
                f"{FLOOR}: surface {surface['name']!r}: {len(matched)} series "
                f"match {surface['pattern']!r}, floor requires {needed} - any "
                f"claim about this surface is currently unwitnessable"
            )
            continue
        for label, cap in (surface.get("max_label_cardinality") or {}).items():
            values = {s.labels[label] for s in matched if label in s.labels}
            if len(values) > int(cap):
                sample_vals = ", ".join(sorted(values)[:3])
                violations.append(
                    f"{FLOOR}: surface {surface['name']!r}: label {label!r} "
                    f"carries {len(values)} distinct values (cap {cap}) - raw "
                    f"paths where route templates belong (e.g. {sample_vals}, "
                    f"...); this is the unbounded-cardinality memory bomb"
                )

    verdict = UNWITNESSED if violations else WITNESSED
    return FloorResult(verdict, violations, len(samples))


def _payload_has_content(text: str) -> bool:
    """True when the payload carried non-comment, non-blank lines - i.e.
    the endpoint said something, whatever it was."""
    return any(
        line.strip() and not line.strip().startswith("#")
        for line in text.splitlines()
    )


# ── reading the surface ─────────────────────────────────────────────────────

def read_payload(source: str, timeout: float = 10.0) -> tuple[str | None, str]:
    """Fetch the metrics text. Returns (text, "") or (None, why) - the
    caller maps failure to INCONCLUSIVE, never to a pass or a fail."""
    if source.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(source, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace"), ""
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return None, (f"{ENDPOINT}: unreachable after {timeout:g}s - "
                          f"{type(exc).__name__}: {exc}")
    try:
        return Path(source).read_text(encoding="utf-8"), ""
    except OSError as exc:
        return None, f"{ENDPOINT}: file unreadable - {type(exc).__name__}: {exc}"


def sample_payloads(
    source: str, samples: int = 1, interval_ms: float = 0.0, timeout: float = 10.0
) -> tuple[list, str]:
    """Scrape `samples` times, `interval_ms` apart. Returns (texts, "") or
    ([], why). Any single failed scrape fails the whole read: a partial
    sample set cannot answer the frozen question and must not pretend to."""
    if samples < 1:
        raise UsageError(f"{INSTRUMENT}: --samples must be >= 1, got {samples}")
    texts: list[str] = []
    for i in range(samples):
        if i and interval_ms > 0:
            time.sleep(interval_ms / 1000.0)
        text, why = read_payload(source, timeout)
        if text is None:
            return [], (f"{why} (on sample {i + 1} of {samples}; a partial "
                        f"sample set cannot answer the frozen question)")
        texts.append(text)
    return texts, ""


# ── frozen-exporter detection ───────────────────────────────────────────────

def _counters_that_should_move(
    text: str, surfaces: list[dict], effects: list | None
) -> list[str]:
    """Families on this surface for which "unchanged" is a claim, not a
    fact: a counter the floor points at, or a family an `increased` effect
    names. Without at least one of these, identical bytes are merely
    identical bytes and FROZEN would be a false accusation."""
    types = parse_types(text)
    names = {s.name for s in parse_metrics(text)}
    named: set = set()
    for e in effects or []:
        if e.get("kind") == "increased" and e.get("family") in names:
            named.add(e["family"])
    for name in names:
        if not looks_like_counter(name, type_for(name, types)):
            continue
        if any(re.search(s["pattern"], name) for s in surfaces):
            named.add(name)
    return sorted(named)


def frozen_check(
    texts: list, surfaces: list[dict], effects: list | None
) -> tuple[bool, str]:
    """(is_frozen, why). Byte-identical payloads across every sample, on a
    surface that declares a counter which ought to move, is FROZEN: a
    cached or wedged exporter serving stale truth behind a 200. It gets
    its own verdict word because the fix is not "add metrics" (doctrine
    2.4); the metrics are there and they are lying about the present."""
    if len(texts) < 2:
        return False, ""
    distinct = len({hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts})
    if distinct > 1:
        return False, (f"{ENDPOINT} moved between samples: {distinct} distinct "
                       f"payloads across {len(texts)} scrapes - not frozen")
    movers = _counters_that_should_move(texts[0], surfaces, effects)
    if not movers:
        return False, (
            f"{len(texts)} byte-identical samples, but no counter on this "
            f"surface is declared as one that must move, so identical bytes "
            f"are not evidence of staleness here. Declare an `increased` "
            f"effect if you want this checked"
        )
    shown = ", ".join(movers[:3]) + ("..." if len(movers) > 3 else "")
    return True, (
        f"{ENDPOINT}: FROZEN - {len(texts)} scrapes returned byte-identical "
        f"payloads while the floor declares {len(movers)} counter(s) that "
        f"should move ({shown}). Either the exporter is caching, its "
        f"collection loop is wedged, or the service is idle. In every case "
        f"nothing here can witness an effect right now, and a 200 from this "
        f"endpoint is stale truth, not fresh truth"
    )


# ── the one-call gate ───────────────────────────────────────────────────────

def gate(
    source: str,
    floor_path: str | Path,
    timeout: float = 10.0,
    samples: int = 1,
    interval_ms: float = 0.0,
) -> FloorResult:
    """One-call form: fetch, parse, check. Library twin of the CLI."""
    doc = load_floor_doc(floor_path)
    surfaces, effects = doc["surfaces"], doc["effects"]

    texts, why = sample_payloads(source, samples, interval_ms, timeout)
    if not texts:
        return FloorResult(
            INCONCLUSIVE,
            [why + " - witnessed nothing; this is not a pass and must not be "
                   "reported as one"],
            0,
            samples_taken=0,
        )

    text = texts[-1]
    parsed, parse_why = safe_parse(text)
    if parse_why:
        return FloorResult(INCONCLUSIVE, [parse_why], 0, samples_taken=len(texts))
    if not parsed and _payload_has_content(text):
        lines = sum(
            1 for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )
        return FloorResult(
            UNWITNESSED,
            [f"{ENDPOINT}: served {lines} non-comment line(s), none of which "
             f"parse as Prometheus text-exposition samples. The endpoint "
             f"answered with something that is not metrics (an error page, a "
             f"JSON body, a redirect) - which reads as an empty surface to "
             f"every scraper and therefore as zero to every dashboard"],
            0,
            samples_taken=len(texts),
        )

    result = check_floor(parsed, surfaces)
    result.samples_taken = len(texts)

    is_frozen, note = frozen_check(texts, surfaces, effects)
    if note:
        if is_frozen:
            # The floor's own violations win the verdict: a missing surface is
            # the more fundamental fact, and burying it under FROZEN would send
            # the reader to the wrong fix. Frozen is still stated, always.
            if result.verdict == UNWITNESSED:
                result.violations.append(note)
            else:
                result.verdict = FROZEN
                result.violations.append(note)
        else:
            result.notes.append(note)
    return result


# ── snapshot ────────────────────────────────────────────────────────────────

def _fmt_value(v: float) -> str:
    """Canonical, round-trip-stable text for one sample value. `repr` on a
    float has been the shortest round-tripping representation since 3.1, so
    this is stable across interpreters, which is what makes the digest a
    digest and not a mood."""
    if v != v:
        return "NaN"
    if v == math.inf:
        return "+Inf"
    if v == -math.inf:
        return "-Inf"
    if v == int(v) and abs(v) < 1e16:
        return str(int(v))
    return repr(v)


def _canonical_series(labels: dict, value: float) -> str:
    inner = ",".join(f"{k}={json.dumps(labels[k])}" for k in sorted(labels))
    return "{" + inner + "} " + _fmt_value(value)


def _value_sum(values: list):
    """Order-independent sum, so two scrapes that list the same series in a
    different order digest to the same number. Non-finite values become a
    token: `NaN` is not JSON, and more importantly a NaN sum cannot answer
    "did it increase" and must say so rather than compare false."""
    if any(v != v or v in (math.inf, -math.inf) for v in values):
        if any(v != v for v in values):
            return "NaN"
        return "+Inf" if math.inf in values else "-Inf"
    return math.fsum(sorted(values))


def build_snapshot(text: str, source: str = "", captured_at: str | None = None) -> dict:
    """A deterministic digest of the metrics surface at a moment.

    Everything except `captured_at` is a pure function of the payload, so
    two snapshots of an identical surface are byte-identical apart from
    that one field - and `captured_at` is excluded from the digests by
    construction, not by a comparison that remembers to skip it (1.2).
    """
    samples, why = safe_parse(text)
    if why:
        raise UsageError(why)
    if not samples:
        party = ENDPOINT
        detail = (
            "served a payload with no parseable series"
            if _payload_has_content(text)
            else 'served an EMPTY payload - "no data" and "all zero" must never '
                 "read the same (doctrine 6.6)"
        )
        raise UsageError(
            f"{party}: {detail}. Refusing to write a snapshot of nothing: a "
            f"snapshot of an empty surface would later diff cleanly against "
            f"another empty surface and report a change as witnessed"
        )

    types = parse_types(text)
    grouped: dict = {}
    for s in samples:
        grouped.setdefault(s.name, []).append(s)

    families: dict = {}
    for name in sorted(grouped):
        series = grouped[name]
        lines = sorted(_canonical_series(s.labels, s.value) for s in series)
        keys = sorted({k for s in series for k in s.labels})
        values: dict = {}
        truncated: list = []
        for k in keys:
            distinct = sorted({s.labels[k] for s in series if k in s.labels})
            if len(distinct) > LABEL_VALUE_CAP:
                truncated.append(k)
            else:
                values[k] = distinct
        families[name] = {
            "type": type_for(name, types),
            "series": len(series),
            "label_keys": keys,
            "label_values": values,
            "label_values_truncated": truncated,
            "value_sum": _value_sum([s.value for s in series]),
            "sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
        }

    surface = hashlib.sha256(
        "\n".join(
            f"{n}\t{f['type']}\t{f['series']}\t{f['sha256']}"
            for n, f in sorted(families.items())
        ).encode("utf-8")
    ).hexdigest()

    return {
        "obsgate_snapshot": SNAPSHOT_VERSION,
        "captured_at": captured_at or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "source": source,
        "series_total": len(samples),
        "family_total": len(families),
        "surface_sha256": surface,
        "families": families,
    }


def load_snapshot(path: str | Path) -> dict:
    """Read a snapshot, refusing anything that is not one. The version
    field exists so a future format change is a refusal rather than a
    confidently wrong answer (1.2)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(
            f"{INSTRUMENT}: snapshot {str(path)!r} unreadable - "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(data, dict) or "obsgate_snapshot" not in data:
        raise UsageError(
            f"{INSTRUMENT}: {str(path)!r} is not an obsgate snapshot (no "
            f"'obsgate_snapshot' version field). Produce one with "
            f"`obsgate snapshot --metrics ... --out {path}`"
        )
    if data["obsgate_snapshot"] != SNAPSHOT_VERSION:
        raise UsageError(
            f"{INSTRUMENT}: snapshot {str(path)!r} is format version "
            f"{data['obsgate_snapshot']}, this obsgate speaks version "
            f"{SNAPSHOT_VERSION}. Refusing rather than half-reading it"
        )
    if not isinstance(data.get("families"), dict):
        raise UsageError(f"{INSTRUMENT}: snapshot {str(path)!r} has no 'families'")
    return data


# ── effect checking: doctrine 6.6, mechanised ───────────────────────────────

def _subject(effect: dict) -> str:
    if effect.get("name"):
        return str(effect["name"])
    kind = effect.get("kind")
    if kind == "appeared" and "label" in effect:
        return f"{effect['family']}{{{effect['label']}={effect['value']!r}}}"
    if kind in ("increased", "appeared"):
        return str(effect["family"])
    if kind == "stable_labels":
        return str(effect.get("family", "(all families in both snapshots)"))
    return "(whole surface)"


def _numeric_sum(fam: dict):
    v = fam.get("value_sum")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _check_increased(effect: dict, before: dict, after: dict) -> EffectResult:
    fam = effect["family"]
    subject = _subject(effect)
    fb = before["families"].get(fam)
    fa = after["families"].get(fam)
    min_delta = float(effect.get("min_delta", 0)) or None

    if fb is None and fa is None:
        return EffectResult(
            "increased", subject, NOT_WITNESSED, FLOOR,
            f"expected-increase-but-family-absent: {fam!r} is in NEITHER "
            f"snapshot. Nothing increased because nothing is exported - a "
            f"metric that does not exist reads downstream as zero traffic, "
            f"not as a missing instrument (doctrine 6.6)",
        )
    if fa is None:
        return EffectResult(
            "increased", subject, NOT_WITNESSED, ENDPOINT,
            f"expected-increase-but-family-VANISHED: {fam!r} was present in "
            f"the before snapshot and is gone from the after snapshot. This "
            f"is how a deleted instrument reads as zero traffic instead of as "
            f"a deleted instrument",
        )

    after_sum = _numeric_sum(fa)
    if after_sum is None:
        return EffectResult(
            "increased", subject, UNANSWERABLE, ENDPOINT,
            f"{fam!r} has a non-finite value sum ({fa.get('value_sum')!r}) in "
            f"the after snapshot; 'did it increase' has no answer over NaN or "
            f"Inf, and comparing anyway would fabricate one",
        )

    if fb is None:
        before_sum = 0.0
        origin = (f"{fam!r} was absent from the before snapshot; a missing "
                  f"counter is read as 0, so ")
    else:
        before_sum = _numeric_sum(fb)
        if before_sum is None:
            return EffectResult(
                "increased", subject, UNANSWERABLE, ENDPOINT,
                f"{fam!r} has a non-finite value sum "
                f"({fb.get('value_sum')!r}) in the before snapshot",
            )
        origin = ""

    delta = after_sum - before_sum
    mtype = fa.get("type", "untyped")
    shape = f"sum {_fmt_value(before_sum)} -> {_fmt_value(after_sum)}"

    if delta < 0:
        if looks_like_counter(fam, mtype):
            return EffectResult(
                "increased", subject, COUNTER_RESET, ENDPOINT,
                f"counter-reset: {fam!r} ({mtype}) FELL, {shape} "
                f"({_fmt_value(delta)}). A counter does not decline - the "
                f"process restarted or the exporter was rebuilt. The effect "
                f"you asked about may well have happened; this surface can no "
                f"longer witness it, which is a different problem from the "
                f"effect not happening",
            )
        return EffectResult(
            "increased", subject, NOT_WITNESSED, ENDPOINT,
            f"expected-increase-but-fell: {fam!r} ({mtype}) went DOWN, "
            f"{shape} ({_fmt_value(delta)}). Not a counter, so this is a real "
            f"decline rather than a restart",
        )
    if delta == 0:
        return EffectResult(
            "increased", subject, NOT_WITNESSED, ENDPOINT,
            f"expected-increase-but-flat: {origin}{fam!r} is unchanged at "
            f"{_fmt_value(after_sum)} across the two snapshots. The change you "
            f"made left no trace here, so it is not done (doctrine 6.6)",
        )
    if min_delta is not None and delta < min_delta:
        return EffectResult(
            "increased", subject, NOT_WITNESSED, ENDPOINT,
            f"expected-increase-of-at-least-{_fmt_value(min_delta)}-but-rose-"
            f"by-{_fmt_value(delta)}: {fam!r} moved, {shape}, but by less than "
            f"the declared floor",
        )
    return EffectResult(
        "increased", subject, WITNESSED, "",
        f"{origin}{shape} (+{_fmt_value(delta)}), type {mtype}",
    )


def _check_appeared(effect: dict, before: dict, after: dict) -> EffectResult:
    fam = effect["family"]
    subject = _subject(effect)
    fb = before["families"].get(fam)
    fa = after["families"].get(fam)

    if "label" not in effect:
        if fa is None:
            return EffectResult(
                "appeared", subject, NOT_WITNESSED, FLOOR,
                f"expected-appear-but-absent: family {fam!r} is not in the "
                f"after snapshot. The instrument you expected to start "
                f"reporting is not reporting",
            )
        if fb is not None:
            return EffectResult(
                "appeared", subject, NOT_WITNESSED, FLOOR,
                f"expected-appear-but-was-already-present: {fam!r} existed in "
                f"the before snapshot too, so its presence witnesses nothing "
                f"about your change. This effect cannot discriminate and is "
                f"the wrong declaration for what you are trying to prove",
            )
        return EffectResult(
            "appeared", subject, WITNESSED, "",
            f"family {fam!r} is new: absent before, {fa['series']} series "
            f"after, type {fa.get('type', 'untyped')}",
        )

    label, want = effect["label"], effect["value"]
    if fa is None:
        return EffectResult(
            "appeared", subject, NOT_WITNESSED, FLOOR,
            f"expected-appear-but-family-absent: family {fam!r} is not in the "
            f"after snapshot at all, so label {label!r} cannot carry "
            f"{want!r} there",
        )
    for snap_name, f in (("after", fa), ("before", fb)):
        if f is not None and label in f.get("label_values_truncated", []):
            return EffectResult(
                "appeared", subject, UNANSWERABLE, INSTRUMENT,
                f"label {label!r} on {fam!r} carries more than "
                f"{LABEL_VALUE_CAP} distinct values, so the {snap_name} "
                f"snapshot STOPPED RECORDING them (LABEL_VALUE_CAP). obsgate "
                f"cannot tell whether {want!r} appeared. This is obsgate's own "
                f"limit, not a fact about the endpoint - and reporting it as "
                f"either a pass or a miss would be a fabricated answer",
            )
    after_vals = set(fa.get("label_values", {}).get(label, []))
    before_vals = set((fb or {}).get("label_values", {}).get(label, []))
    if want not in after_vals:
        return EffectResult(
            "appeared", subject, NOT_WITNESSED, FLOOR,
            f"expected-appear-but-absent: {label}={want!r} is not among the "
            f"{len(after_vals)} value(s) {fam!r} carries in the after "
            f"snapshot",
        )
    if want in before_vals:
        return EffectResult(
            "appeared", subject, NOT_WITNESSED, FLOOR,
            f"expected-appear-but-was-already-present: {label}={want!r} was "
            f"already on {fam!r} in the before snapshot",
        )
    return EffectResult(
        "appeared", subject, WITNESSED, "",
        f"{label}={want!r} is new on {fam!r} (absent before, present after)",
    )


def _check_no_vanished(effect: dict, before: dict, after: dict) -> EffectResult:
    subject = _subject(effect)
    allow = set(effect.get("allow") or [])
    was = set(before["families"])
    if not was:
        return EffectResult(
            "no_vanished_series", subject, UNANSWERABLE, INSTRUMENT,
            "the before snapshot lists no families, so nothing could vanish "
            "and a pass here would be vacuous. Check what produced it",
        )
    gone = sorted(was - set(after["families"]) - allow)
    if gone:
        shown = ", ".join(gone[:5]) + ("..." if len(gone) > 5 else "")
        return EffectResult(
            "no_vanished_series", subject, NOT_WITNESSED, ENDPOINT,
            f"{len(gone)} family(ies) present before are GONE after: {shown}. "
            f"A vanished metric is how a deleted instrument reads as zero "
            f"traffic: every consumer of these families is now being told "
            f"'nothing happened' by an absence",
        )
    return EffectResult(
        "no_vanished_series", subject, WITNESSED, "",
        f"all {len(was)} families in the before snapshot are still present "
        f"(family-level; a single series vanishing inside a surviving family "
        f"is out of scope - see docs/design/obsgate-depth.md)",
    )


def _check_stable_labels(effect: dict, before: dict, after: dict) -> EffectResult:
    subject = _subject(effect)
    named = effect.get("family")
    if named is not None:
        if named not in before["families"] or named not in after["families"]:
            missing = "before" if named not in before["families"] else "after"
            return EffectResult(
                "stable_labels", subject, UNANSWERABLE, ENDPOINT,
                f"family {named!r} is absent from the {missing} snapshot, so "
                f"its label shape cannot be compared. Absence is a different "
                f"finding - declare no_vanished_series if that is what you "
                f"want checked",
            )
        fams = [named]
    else:
        fams = sorted(set(before["families"]) & set(after["families"]))
        if not fams:
            return EffectResult(
                "stable_labels", subject, UNANSWERABLE, ENDPOINT,
                "the two snapshots share no families at all, so there is no "
                "label shape to compare and a pass would be vacuous",
            )

    drift: list = []
    for fam in fams:
        b = set(before["families"][fam]["label_keys"])
        a = set(after["families"][fam]["label_keys"])
        gained, lost = sorted(a - b), sorted(b - a)
        if gained:
            drift.append(f"{fam} GAINED label key(s) {', '.join(gained)}")
        if lost:
            drift.append(f"{fam} LOST label key(s) {', '.join(lost)}")
    if drift:
        shown = "; ".join(drift[:5]) + ("..." if len(drift) > 5 else "")
        return EffectResult(
            "stable_labels", subject, NOT_WITNESSED, ENDPOINT,
            f"cardinality-shape drift: {shown}. A new label key multiplies the "
            f"series count of the whole family and silently re-partitions "
            f"every existing dashboard query; a lost one silently merges "
            f"series that used to be separate",
        )
    return EffectResult(
        "stable_labels", subject, WITNESSED, "",
        f"label keys unchanged across {len(fams)} family(ies)",
    )


_EFFECT_DISPATCH = {
    "increased": _check_increased,
    "appeared": _check_appeared,
    "no_vanished_series": _check_no_vanished,
    "stable_labels": _check_stable_labels,
}


def check_effects(before: dict, after: dict, effects: list) -> EffectsResult:
    """Doctrine 6.6's sentence as an exit code: a change to a running
    system is done only when its effect can be witnessed at a runtime
    surface. `effects` must be non-empty - the caller refuses first."""
    if not effects:
        raise UsageError(
            f"{FLOOR}: the manifest declares no 'effects' section, so there is "
            f"NOTHING to check and this command has no answer to give. "
            f"Refusing rather than exiting 0: a vacuous pass here would be a "
            f"tool certifying that an unstated change was witnessed (doctrine "
            f"2.4). Declare at least one effect, or do not run this command"
        )
    return EffectsResult([_EFFECT_DISPATCH[e["kind"]](e, before, after)
                         for e in effects])


# ── selfcheck ───────────────────────────────────────────────────────────────

_GOOD_PAYLOAD = """\
# HELP http_requests_total requests by route template
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
# TYPE jobs_fired_total counter
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

_EFFECTS = [
    {"kind": "increased", "family": "http_requests_total"},
    {"kind": "appeared", "family": "http_requests_total",
     "label": "route", "value": "/api/exports"},
    {"kind": "no_vanished_series"},
    {"kind": "stable_labels", "family": "http_requests_total"},
]


def _moved_payload() -> str:
    """The same surface after a change that IS witnessable: the counter
    rose and a new route template appeared."""
    return _GOOD_PAYLOAD.replace(
        'http_requests_total{route="/api/orders",method="POST"} 112',
        'http_requests_total{route="/api/orders",method="POST"} 130\n'
        'http_requests_total{route="/api/exports",method="GET"} 7',
    )


def selfcheck() -> bool:
    """Every verdict is exercised, and the refusals are the point: an empty
    payload must FAIL, an unreadable source must be INCONCLUSIVE, a frozen
    exporter must not read as healthy, a counter that fell must be NAMED as
    a reset, and a manifest with no effects must REFUSE rather than pass. A
    gate that read any of those as WITNESSED would be the round-3 proxy
    mistake shipped as a tool."""
    try:
        return _selfcheck_body()
    except Exception as exc:  # noqa: BLE001
        # Doctrine 2.2: a guard that crashes has not reported anything. Say
        # so as a verdict, and say it is OUR crash, not the subject's.
        print(f"[obsgate] SELFCHECK FAILED: the selfcheck itself raised "
              f"{type(exc).__name__}: {exc} - this is obsgate's failure, and "
              f"nothing about any endpoint has been checked", file=sys.stderr)
        return False


def _selfcheck_body() -> bool:  # noqa: C901 - a checklist, read top to bottom
    import tempfile

    ok = True
    proved: list = []

    def _fail(msg: str) -> None:
        nonlocal ok
        print(f"[obsgate] SELFCHECK FAILED: {msg}")
        ok = False

    # ── 1. the parser ───────────────────────────────────────────────────
    samples = parse_metrics(_GOOD_PAYLOAD)
    if len(samples) != 8:
        _fail(f"parser read {len(samples)} of 8 planted samples")
    by_name: dict = {}
    for s in samples:
        by_name.setdefault(s.name, []).append(s)
    if by_name.get("http_requests_total", [None])[0] and \
       by_name["http_requests_total"][0].labels.get("route") != "/api/users/:id":
        _fail("labels not parsed from a planted sample")
    if type_for("http_requests_total", parse_types(_GOOD_PAYLOAD)) != "counter":
        _fail("# TYPE was not read: counter-reset detection would be blind")
    proved.append("parser + # TYPE")

    # A parser crash must accuse the INSTRUMENT, never the endpoint. This is
    # the R3-1 scar (2.4 + 6.4) as a planted case.
    def _exploding(_text):
        raise ZeroDivisionError("planted")

    _, why = safe_parse("whatever", parser=_exploding)
    if INSTRUMENT not in why or "ZeroDivisionError" not in why:
        _fail(f"a parser crash was not attributed to the instrument (or did "
              f"not name the exception type): {why!r}")
    if ENDPOINT in why.split(".")[0]:
        _fail(f"a parser crash blamed the endpoint in its headline: {why!r}")
    proved.append("parser crash blamed on the instrument, by exception type")

    # ── 2. the floor ────────────────────────────────────────────────────
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
    elif not any(v.startswith(ENDPOINT + ":") for v in res.violations):
        _fail("the empty-200 refusal did not name the endpoint as the party")

    partial = [s for s in samples if not s.name.startswith("jobs_")]
    res = check_floor(partial, _FLOOR)
    if res.verdict != UNWITNESSED or not any("jobs" in v for v in res.violations):
        _fail(f"a missing surface was not named: {res.verdict} {res.violations}")
    elif not any(v.startswith(FLOOR + ":") for v in res.violations):
        _fail("a missing surface was not attributed to the floor")

    bomb = parse_metrics(_GOOD_PAYLOAD) + [
        Sample("http_requests_total", {"route": f"/api/users/{i}", "method": "GET"}, 1.0)
        for i in range(60)
    ]
    res = check_floor(bomb, _FLOOR)
    if res.verdict != UNWITNESSED or not any("cardinality" in v or "distinct" in v
                                             for v in res.violations):
        _fail(f"a raw-path cardinality bomb passed: {res.verdict}")
    proved.append("floor: empty-200, missing surface, cardinality bomb, all "
                  "party-attributed")

    # ── 3. snapshot determinism ─────────────────────────────────────────
    s1 = build_snapshot(_GOOD_PAYLOAD, "a", captured_at="T1")
    s2 = build_snapshot(_GOOD_PAYLOAD, "a", captured_at="T2")
    d1, d2 = dict(s1), dict(s2)
    d1.pop("captured_at"), d2.pop("captured_at")
    if json.dumps(d1, sort_keys=True) != json.dumps(d2, sort_keys=True):
        _fail("two snapshots of ONE payload differ outside captured_at - the "
              "digest is not a digest")
    shuffled = "\n".join(reversed(_GOOD_PAYLOAD.strip().splitlines())) + "\n"
    if build_snapshot(shuffled, "a", captured_at="T1")["surface_sha256"] != \
       s1["surface_sha256"]:
        _fail("re-ordering the payload's lines changed the digest - a scrape "
              "that lists series in another order would read as a change")
    if build_snapshot(_moved_payload(), "a", captured_at="T1")["surface_sha256"] == \
       s1["surface_sha256"]:
        _fail("a CHANGED surface produced the same digest - the digest cannot "
              "see change, so it can certify anything")
    try:
        build_snapshot("# HELP only comments here\n")
        _fail("a snapshot of an EMPTY surface was written - it would later "
              "diff cleanly against another empty surface")
    except UsageError as exc:
        if ENDPOINT not in str(exc):
            _fail(f"the empty-snapshot refusal did not name the endpoint: {exc}")
    proved.append("snapshot determinism (order-independent, change-sensitive, "
                  "empty refused)")

    # label-value cap: past it, the snapshot must record that it stopped
    # looking, and questions about that key must be UNANSWERABLE.
    wide = "# TYPE wide_total counter\n" + "".join(
        f'wide_total{{id="v{i}"}} 1\n' for i in range(LABEL_VALUE_CAP + 5)
    )
    ws = build_snapshot(wide, "wide", captured_at="T1")
    if ws["families"]["wide_total"]["label_values_truncated"] != ["id"]:
        _fail("the label-value cap did not record that it stopped looking - "
              "the snapshot would silently claim a full value set")
    r = _check_appeared(
        {"kind": "appeared", "family": "wide_total", "label": "id", "value": "v3"},
        build_snapshot(wide, "wide", captured_at="T0"), ws,
    )
    if r.verdict != UNANSWERABLE or r.party != INSTRUMENT:
        _fail(f"a question about a truncated label answered {r.verdict}/"
              f"{r.party}, not UNANSWERABLE/instrument - obsgate guessed")
    proved.append("label-value cap refuses to guess (UNANSWERABLE, instrument)")

    # ── 4. effects ──────────────────────────────────────────────────────
    before = build_snapshot(_GOOD_PAYLOAD, "b", captured_at="T1")
    after = build_snapshot(_moved_payload(), "a", captured_at="T2")
    eres = check_effects(before, after, _EFFECTS)
    if not eres.all_ok:
        _fail(f"a genuinely witnessed change reported "
              f"{[(r.kind, r.verdict, r.detail) for r in eres.results if not r.ok]}")

    # ...and the same effects against a surface that did NOT move.
    flat = check_effects(before, before, _EFFECTS)
    if flat.all_ok:
        _fail("an UNCHANGED surface witnessed every effect - the effects "
              "checker passes vacuously")
    inc = [r for r in flat.results if r.kind == "increased"][0]
    if inc.verdict != NOT_WITNESSED or "flat" not in inc.detail:
        _fail(f"a flat counter was not named as flat: {inc.verdict} {inc.detail}")

    # counter reset: after < before on a counter is its OWN outcome.
    fell = build_snapshot(
        _GOOD_PAYLOAD.replace(
            'http_requests_total{route="/api/users/:id",method="GET"} 9042',
            'http_requests_total{route="/api/users/:id",method="GET"} 3'),
        "a", captured_at="T2")
    r = _check_increased({"kind": "increased", "family": "http_requests_total"},
                         before, fell)
    if r.verdict != COUNTER_RESET:
        _fail(f"a counter that FELL reported {r.verdict}, not COUNTER_RESET - "
              f"a restart and a missing effect would read the same")
    elif "reset" not in r.detail.lower() or r.party != ENDPOINT:
        _fail(f"the counter-reset verdict did not say reset / endpoint: {r}")

    # ...but a non-counter that falls is a fall, not a reset.
    g_before = build_snapshot("# TYPE q_depth gauge\nq_depth 10\n", "b", captured_at="T1")
    g_after = build_snapshot("# TYPE q_depth gauge\nq_depth 2\n", "a", captured_at="T2")
    r = _check_increased({"kind": "increased", "family": "q_depth"},
                         g_before, g_after)
    if r.verdict != NOT_WITNESSED or "fell" not in r.detail:
        _fail(f"a GAUGE that fell was reported as {r.verdict} - a gauge going "
              f"down is a decline, not a restart")

    # vanished family
    gone_after = build_snapshot(
        "\n".join(ln for ln in _GOOD_PAYLOAD.splitlines()
                  if not ln.startswith("jobs_")) + "\n", "a", captured_at="T2")
    r = _check_no_vanished({"kind": "no_vanished_series"}, before, gone_after)
    if r.verdict != NOT_WITNESSED or "jobs_fired_total" not in r.detail:
        _fail(f"a VANISHED family was not caught or not named: {r.verdict} "
              f"{r.detail}")
    r = _check_no_vanished({"kind": "no_vanished_series"},
                           {"families": {}}, gone_after)
    if r.verdict != UNANSWERABLE:
        _fail("an EMPTY before snapshot passed no_vanished_series vacuously")

    # label-shape drift
    drifted = build_snapshot(
        _GOOD_PAYLOAD.replace(
            'http_requests_total{route="/api/orders",method="POST"} 112',
            'http_requests_total{route="/api/orders",method="POST",tenant="t1"} 112'),
        "a", captured_at="T2")
    r = _check_stable_labels(
        {"kind": "stable_labels", "family": "http_requests_total"}, before, drifted)
    if r.verdict != NOT_WITNESSED or "tenant" not in r.detail:
        _fail(f"a NEW label key was not caught: {r.verdict} {r.detail}")
    r = _check_stable_labels(
        {"kind": "stable_labels", "family": "not_a_family"}, before, after)
    if r.verdict != UNANSWERABLE:
        _fail("stable_labels on an absent family did not answer UNANSWERABLE")

    # appeared: absent, and already-present
    r = _check_appeared({"kind": "appeared", "family": "http_requests_total",
                         "label": "route", "value": "/nope"}, before, after)
    if r.verdict != NOT_WITNESSED or "expected-appear-but-absent" not in r.detail:
        _fail(f"a label value that never appeared was not named with its "
              f"direction: {r.verdict} {r.detail}")
    r = _check_appeared({"kind": "appeared", "family": "http_requests_total",
                         "label": "route", "value": "/api/orders"}, before, after)
    if r.verdict != NOT_WITNESSED or "already-present" not in r.detail:
        _fail(f"an ALREADY-PRESENT label value was reported as an appearance: "
              f"{r.verdict} {r.detail}")

    # the refusal that must never be a pass
    try:
        check_effects(before, after, [])
        _fail("a manifest with NO effects section returned a result instead of "
              "refusing - a vacuous pass certifying an unstated change")
    except UsageError as exc:
        if "NOTHING to check" not in str(exc):
            _fail(f"the no-effects refusal did not say why: {exc}")
    for bad in ([], [{"kind": "teleported", "family": "x"}],
                [{"kind": "increased"}],
                [{"kind": "appeared", "family": "x", "label": "l"}]):
        try:
            _validate_effects(bad)
            _fail(f"a malformed effects section was accepted: {bad!r}")
        except UsageError:
            pass
    proved.append("effects: increase, counter-reset, gauge-fall, vanished, "
                  "label drift, appeared (absent/already-present), "
                  "no-effects refusal")

    # ── 5. frozen exporter ──────────────────────────────────────────────
    frozen, why = frozen_check([_GOOD_PAYLOAD, _GOOD_PAYLOAD, _GOOD_PAYLOAD],
                               _FLOOR, _EFFECTS)
    if not frozen or "FROZEN" not in why:
        _fail(f"three byte-identical scrapes of a counter-bearing surface were "
              f"not reported FROZEN: {frozen} {why!r}")
    frozen, why = frozen_check([_GOOD_PAYLOAD, _moved_payload()], _FLOOR, _EFFECTS)
    if frozen:
        _fail("a surface that MOVED between scrapes was reported FROZEN")
    frozen, _ = frozen_check(
        ["# TYPE g gauge\ng 1\n"] * 3,
        [{"name": "g", "pattern": "^g$"}], None)
    if frozen:
        _fail("a gauge-only surface with no counter that must move was accused "
              "of being FROZEN - a false accusation is worse than no finding")
    frozen, _ = frozen_check([_GOOD_PAYLOAD], _FLOOR, _EFFECTS)
    if frozen:
        _fail("a SINGLE sample was called FROZEN - one scrape cannot show "
              "staleness")
    proved.append("frozen exporter (identical bytes + must-move counter), and "
                  "the three cases that must NOT trip it")

    # ── 6. end to end, through files ────────────────────────────────────
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        floor_path = tmp / "floor.json"
        floor_path.write_text(json.dumps({"surfaces": _FLOOR, "effects": _EFFECTS}))

        res = gate(str(tmp / "no-such-file.txt"), floor_path)
        if res.verdict != INCONCLUSIVE:
            _fail(f"an unreadable source reported {res.verdict}, not "
                  f"INCONCLUSIVE - a dead endpoint must never read as a pass")
        elif not any(ENDPOINT in v for v in res.violations):
            _fail("an unreadable source did not name the endpoint as the party")

        res = gate("http://127.0.0.1:1/metrics", floor_path, timeout=0.5)
        if res.verdict != INCONCLUSIVE:
            _fail(f"a dead endpoint reported {res.verdict}, not INCONCLUSIVE")

        good_path = tmp / "metrics.txt"
        good_path.write_text(_GOOD_PAYLOAD)
        res = gate(str(good_path), floor_path)
        if res.verdict != WITNESSED:
            _fail(f"end-to-end on a good payload reported {res.verdict}")

        res = gate(str(good_path), floor_path, samples=3, interval_ms=0)
        if res.verdict != FROZEN:
            _fail(f"three identical scrapes through the real seam reported "
                  f"{res.verdict}, not FROZEN")

        junk = tmp / "junk.txt"
        junk.write_text("<html><body>502 Bad Gateway</body></html>\n")
        res = gate(str(junk), floor_path)
        if res.verdict != UNWITNESSED or not any(
                "not metrics" in v or "none of which parse" in v
                for v in res.violations):
            _fail(f"an HTML error page was not diagnosed as a non-metrics "
                  f"payload: {res.verdict} {res.violations}")

        try:
            load_floor(tmp / "absent.json")
            _fail("an unreadable manifest was accepted")
        except ValueError:
            pass
        bad = tmp / "empty.json"
        bad.write_text('{"surfaces": []}')
        try:
            load_floor(bad)
            _fail("an EMPTY floor was accepted - it would gate nothing forever")
        except ValueError:
            pass

        snap_path = tmp / "snap.json"
        snap_path.write_text(json.dumps(
            {"obsgate_snapshot": 999, "families": {}}))
        try:
            load_snapshot(snap_path)
            _fail("a snapshot from an UNKNOWN format version was half-read")
        except UsageError:
            pass
        snap_path.write_text('{"not": "a snapshot"}')
        try:
            load_snapshot(snap_path)
            _fail("an arbitrary JSON file was accepted as a snapshot")
        except UsageError:
            pass
    proved.append("end-to-end: dead endpoint INCONCLUSIVE, frozen through the "
                  "real seam, HTML error page diagnosed, bad manifests and "
                  "snapshots refused")

    if ok:
        print("[obsgate] selfcheck ok: " + "; ".join(proved))
    return ok


# ── CLI ─────────────────────────────────────────────────────────────────────

_SUBCOMMANDS = ("check", "snapshot", "effects")
_CHECK_FLAGS = {"--metrics", "--floor", "--timeout", "--samples", "--interval-ms"}
_SNAPSHOT_FLAGS = {"--metrics", "--out", "--timeout"}
_EFFECTS_FLAGS = {"--before", "--after", "--floor"}
_GLOBAL_FLAGS = {"--selfcheck", "--help", "-h"}
_KNOWN_FLAGS = (_CHECK_FLAGS | _SNAPSHOT_FLAGS | _EFFECTS_FLAGS | _GLOBAL_FLAGS)


def _parse_flags(argv: list, known: set) -> dict:
    """Flags this subcommand accepts, and nothing else. An unknown flag is a
    refusal, never a shrug: a tool that ignores flags makes its own exit 0
    mean only 'the process started' (the round-4 scar)."""
    out: dict = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if not a.startswith("-"):
            raise UsageError(f"{INSTRUMENT}: unexpected argument: {a}")
        if a not in known:
            hint = (" (it is a flag of another obsgate subcommand)"
                    if a in _KNOWN_FLAGS else "")
            raise UsageError(f"{INSTRUMENT}: unknown flag: {a}{hint}")
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise UsageError(f"{INSTRUMENT}: {a} needs a value")
        out[a] = argv[i + 1]
        i += 2
    return out


def _cmd_snapshot(argv: list) -> int:
    flags = _parse_flags(argv, _SNAPSHOT_FLAGS)
    source, out = flags.get("--metrics"), flags.get("--out")
    if not source or not out:
        raise UsageError(
            f"{INSTRUMENT}: snapshot needs --metrics <file-or-url> and --out "
            f"<snap.json>")
    timeout = float(flags.get("--timeout", 10.0))

    text, why = read_payload(source, timeout)
    if text is None:
        print(f"[obsgate] {why} - no snapshot written; a snapshot of nothing "
              f"would diff cleanly against anything", file=sys.stderr)
        return 3
    try:
        snap = build_snapshot(text, source=source)
    except UsageError as exc:
        print(f"[obsgate] {exc}", file=sys.stderr)
        return 2 if str(exc).startswith(INSTRUMENT) else 3
    try:
        Path(out).write_text(json.dumps(snap, sort_keys=True, indent=2) + "\n",
                             encoding="utf-8")
    except OSError as exc:
        print(f"[obsgate] {INSTRUMENT}: cannot write {out!r} - "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"[obsgate] snapshot: {snap['series_total']} series in "
          f"{snap['family_total']} families, surface "
          f"{snap['surface_sha256'][:16]}..., captured_at {snap['captured_at']} "
          f"-> {out}")
    return 0


def _cmd_effects(argv: list) -> int:
    flags = _parse_flags(argv, _EFFECTS_FLAGS)
    before_p, after_p = flags.get("--before"), flags.get("--after")
    floor_p = flags.get("--floor")
    if not before_p or not after_p or not floor_p:
        raise UsageError(
            f"{INSTRUMENT}: effects needs --before <snap.json> --after "
            f"<snap.json> --floor <manifest.json>")
    before, after = load_snapshot(before_p), load_snapshot(after_p)
    try:
        effects = load_effects(floor_p)
    except ValueError as exc:
        raise UsageError(f"{INSTRUMENT}: {exc}") from exc
    result = check_effects(before, after, effects)
    print(result.report())
    return 0 if result.all_ok else 1


def _cmd_check(argv: list) -> int:
    flags = _parse_flags(argv, _CHECK_FLAGS)
    source, floor_path = flags.get("--metrics"), flags.get("--floor")
    if not source or not floor_path:
        raise UsageError(
            f"{INSTRUMENT}: need both --metrics <file-or-url> and --floor "
            f"<manifest.json> (or --selfcheck)")
    timeout = float(flags.get("--timeout", 10.0))
    samples = int(flags.get("--samples", 1))
    interval_ms = float(flags.get("--interval-ms", 0.0))

    if not selfcheck():
        return 1
    try:
        result = gate(source, floor_path, timeout, samples, interval_ms)
    except ValueError as exc:
        print(f"[obsgate] {exc}", file=sys.stderr)
        return 2
    print(result.report())
    return {WITNESSED: 0, UNWITNESSED: 1, INCONCLUSIVE: 3, FROZEN: 4}[result.verdict]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "--selfcheck" in argv:
        return 0 if selfcheck() else 1
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0

    sub = None
    if argv and not argv[0].startswith("-"):
        sub = argv[0]
        if sub not in _SUBCOMMANDS:
            print(f"[obsgate] {INSTRUMENT}: unknown subcommand: {sub} "
                  f"(expected one of {', '.join(_SUBCOMMANDS)}, or the flags "
                  f"of the default check)", file=sys.stderr)
            return 2
        argv = argv[1:]

    try:
        if sub == "snapshot":
            return _cmd_snapshot(argv)
        if sub == "effects":
            return _cmd_effects(argv)
        return _cmd_check(argv)
    except UsageError as exc:
        print(f"[obsgate] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
