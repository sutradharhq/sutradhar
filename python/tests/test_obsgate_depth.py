# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""obsgate's depth layer: snapshots, effect witnessing, and live-surface
honesty (round 12; design note docs/design/obsgate-depth.md).

`test_obsgate.py` pins the single-payload floor gate. This file pins the
three things that make 6.6's sentence - *a change is done when its effect
can be witnessed at a runtime surface* - into something with an exit code:

  1. a snapshot is a DIGEST (deterministic, order-independent, and it moves
     when the surface moves), or it certifies nothing;
  2. every effect verdict names a DIRECTION and a PARTY, because a miss
     without a direction sends the reader the opposite way (doctrine 2.4)
     and a failure without a party lets obsgate file bugs against other
     people's servers (2.4 + 6.4);
  3. nothing here is allowed to pass vacuously - no effects section, an
     empty before-snapshot, and a truncated label set each REFUSE.

Two of these are class ratchets (doctrine 2.1) rather than point tests: one
walks every effect kind, one walks every failure message every detector can
emit. A kind added later is covered the day it lands.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sutradhar_guards.budget import get_budget
from sutradhar_guards.obsgate import (
    COUNTER_RESET,
    EFFECT_KINDS,
    FROZEN,
    INSTRUMENT,
    LABEL_VALUE_CAP,
    NOT_WITNESSED,
    UNANSWERABLE,
    UNWITNESSED,
    WITNESSED,
    UsageError,
    _EFFECT_DISPATCH,
    build_snapshot,
    check_effects,
    check_floor,
    frozen_check,
    gate,
    load_floor_doc,
    load_snapshot,
    safe_parse,
)
from sutradhar_guards.budget import budget

DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design"

BEFORE = """\
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9042
http_requests_total{route="/api/orders",method="POST"} 112
# TYPE jobs_fired_total counter
jobs_fired_total 40
# TYPE queue_depth gauge
queue_depth 10
"""

AFTER = """\
# TYPE http_requests_total counter
http_requests_total{route="/api/users/:id",method="GET"} 9100
http_requests_total{route="/api/orders",method="POST"} 112
http_requests_total{route="/api/exports",method="GET"} 7
# TYPE jobs_fired_total counter
jobs_fired_total 44
# TYPE queue_depth gauge
queue_depth 3
"""

SURFACES = [
    {"name": "requests", "pattern": "^http_requests_total$"},
    {"name": "jobs", "pattern": "^jobs_fired_total$"},
]

EFFECTS = [
    {"kind": "increased", "family": "http_requests_total", "min_delta": 10},
    {"kind": "appeared", "family": "http_requests_total",
     "label": "route", "value": "/api/exports"},
    {"kind": "no_vanished_series"},
    {"kind": "stable_labels", "family": "http_requests_total"},
]


def _snap(text, at="T1"):
    return build_snapshot(text, source="test", captured_at=at)


def _one(effects, before, after):
    return check_effects(before, after, effects).results[0]


# ── 1. the snapshot is a digest ─────────────────────────────────────────────

def test_two_snapshots_of_one_surface_differ_only_in_captured_at():
    """The whole tool leans on this. If a digest wobbled between two reads
    of an unchanged surface, every `effects` run would report drift that
    nobody caused, and the tool would be trained out of within a week."""
    a = build_snapshot(BEFORE, source="s")
    b = build_snapshot(BEFORE, source="s")
    assert a["captured_at"] and b["captured_at"]
    a.pop("captured_at"), b.pop("captured_at")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_series_order_does_not_change_the_digest():
    """Scrapers do not promise line order. A digest that sorted nothing
    would report a reordered scrape as a changed surface."""
    shuffled = "\n".join(reversed(BEFORE.strip().splitlines())) + "\n"
    assert _snap(shuffled)["surface_sha256"] == _snap(BEFORE)["surface_sha256"]


def test_a_changed_surface_changes_the_digest():
    """The other direction, and the one that makes the test above mean
    something: a digest that never moves is a constant, not a digest."""
    assert _snap(AFTER)["surface_sha256"] != _snap(BEFORE)["surface_sha256"]


def test_snapshot_records_type_series_count_and_label_keys():
    fam = _snap(BEFORE)["families"]["http_requests_total"]
    assert fam["type"] == "counter"
    assert fam["series"] == 2
    assert fam["label_keys"] == ["method", "route"]
    assert fam["value_sum"] == 9154


def test_histogram_children_inherit_the_declared_type():
    """`# TYPE foo histogram` types `foo_bucket`/`foo_sum`/`foo_count`,
    which are the names that actually carry series."""
    snap = _snap("# TYPE lat histogram\nlat_bucket{le=\"1\"} 3\nlat_count 3\n")
    assert snap["families"]["lat_bucket"]["type"] == "histogram"
    assert snap["families"]["lat_count"]["type"] == "histogram"


def test_snapshot_of_an_empty_surface_is_refused(tmp_path):
    """A snapshot of nothing would diff cleanly against another snapshot of
    nothing and report a change as witnessed - the empty-200 lie, moved one
    layer down."""
    with pytest.raises(UsageError) as exc:
        build_snapshot("# HELP only comments\n")
    assert "endpoint" in str(exc.value)


def test_label_values_are_capped_and_say_so():
    """Doctrine 2.6 pointed at obsgate's own output: a snapshot that stored
    every distinct label value would rebuild the cardinality bomb inside
    the snapshot file. Past the cap it must record that it STOPPED LOOKING,
    not silently ship a partial set as a complete one."""
    wide = "# TYPE wide_total counter\n" + "".join(
        f'wide_total{{id="v{i}"}} 1\n' for i in range(LABEL_VALUE_CAP + 5)
    )
    fam = _snap(wide)["families"]["wide_total"]
    assert fam["label_values_truncated"] == ["id"]
    assert "id" not in fam["label_values"]

    narrow = "# TYPE n_total counter\n" + "".join(
        f'n_total{{id="v{i}"}} 1\n' for i in range(LABEL_VALUE_CAP)
    )
    assert _snap(narrow)["families"]["n_total"]["label_values_truncated"] == []


def test_a_question_about_a_truncated_label_is_unanswerable_not_guessed():
    wide = "# TYPE wide_total counter\n" + "".join(
        f'wide_total{{id="v{i}"}} 1\n' for i in range(LABEL_VALUE_CAP + 5)
    )
    r = _one([{"kind": "appeared", "family": "wide_total",
               "label": "id", "value": "v3"}], _snap(wide), _snap(wide, "T2"))
    assert r.verdict == UNANSWERABLE
    assert r.party == INSTRUMENT, "obsgate's own cap is obsgate's failure to own"


def test_snapshot_version_and_shape_are_refused_not_duck_typed(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"obsgate_snapshot": 999, "families": {}}))
    with pytest.raises(UsageError):
        load_snapshot(p)
    p.write_text('{"not": "a snapshot"}')
    with pytest.raises(UsageError):
        load_snapshot(p)


# ── 2. effect witnessing ────────────────────────────────────────────────────

def test_a_real_change_is_witnessed_on_every_declared_effect():
    res = check_effects(_snap(BEFORE), _snap(AFTER, "T2"), EFFECTS)
    assert res.all_ok, [r.detail for r in res.results if not r.ok]
    assert res.witnessed == 4


def test_an_unchanged_surface_witnesses_nothing():
    """The load-bearing negative: if this passed, `effects` would certify
    every no-op change ever made."""
    res = check_effects(_snap(BEFORE), _snap(BEFORE, "T2"), EFFECTS)
    assert not res.all_ok
    inc = [r for r in res.results if r.kind == "increased"][0]
    assert inc.verdict == NOT_WITNESSED
    assert "expected-increase-but-flat" in inc.detail


def test_counter_reset_is_named_not_generically_failed():
    """A counter that fell did not decline - the process restarted. Same
    arithmetic, opposite diagnosis, so it gets its own word (doctrine 2.4):
    reporting it as 'the effect did not happen' sends the reader to debug a
    feature when the exporter restarted under them."""
    r = _one([{"kind": "increased", "family": "http_requests_total"}],
             _snap(AFTER), _snap(BEFORE, "T2"))
    assert r.verdict == COUNTER_RESET
    assert "counter-reset" in r.detail
    assert r.party == "endpoint"


def test_a_gauge_that_falls_is_a_fall_not_a_reset():
    """The direction test for the test above: if everything that fell were
    a reset, COUNTER_RESET would carry no information."""
    r = _one([{"kind": "increased", "family": "queue_depth"}],
             _snap(BEFORE), _snap(AFTER, "T2"))
    assert r.verdict == NOT_WITNESSED
    assert "expected-increase-but-fell" in r.detail


def test_a_vanished_family_is_named_as_the_deleted_instrument_case():
    gone = "\n".join(ln for ln in AFTER.splitlines()
                     if not ln.startswith("jobs_")) + "\n"
    r = _one([{"kind": "no_vanished_series"}], _snap(BEFORE), _snap(gone, "T2"))
    assert r.verdict == NOT_WITNESSED
    assert "jobs_fired_total" in r.detail
    assert r.party == "endpoint"


def test_no_vanished_series_refuses_an_empty_before_snapshot():
    """Otherwise the check passes hardest exactly when the before snapshot
    is broken - a vacuous pass at the worst possible moment."""
    r = _one([{"kind": "no_vanished_series"}], {"families": {}}, _snap(AFTER))
    assert r.verdict == UNANSWERABLE


def test_a_new_label_key_is_cardinality_shape_drift():
    drifted = AFTER.replace(
        'http_requests_total{route="/api/orders",method="POST"} 112',
        'http_requests_total{route="/api/orders",method="POST",tenant="t1"} 112')
    r = _one([{"kind": "stable_labels", "family": "http_requests_total"}],
             _snap(BEFORE), _snap(drifted, "T2"))
    assert r.verdict == NOT_WITNESSED
    assert "tenant" in r.detail and "GAINED" in r.detail


def test_stable_labels_on_an_absent_family_is_unanswerable():
    r = _one([{"kind": "stable_labels", "family": "nope_total"}],
             _snap(BEFORE), _snap(AFTER, "T2"))
    assert r.verdict == UNANSWERABLE


def test_appeared_discriminates_absent_from_already_present():
    absent = _one([{"kind": "appeared", "family": "http_requests_total",
                    "label": "route", "value": "/never"}],
                  _snap(BEFORE), _snap(AFTER, "T2"))
    assert absent.verdict == NOT_WITNESSED
    assert "expected-appear-but-absent" in absent.detail

    already = _one([{"kind": "appeared", "family": "http_requests_total",
                     "label": "route", "value": "/api/orders"}],
                   _snap(BEFORE), _snap(AFTER, "T2"))
    assert already.verdict == NOT_WITNESSED
    assert "already-present" in already.detail, (
        "an effect that cannot discriminate must say so, not pass"
    )


def test_missing_effects_section_refuses_rather_than_passing():
    """The refusal that keeps the command honest. An empty effects list is
    not 'all effects passed'; it is a question nobody asked, and answering
    it 0 would be a tool certifying an unstated change (doctrine 2.4)."""
    with pytest.raises(UsageError) as exc:
        check_effects(_snap(BEFORE), _snap(AFTER, "T2"), [])
    assert "NOTHING to check" in str(exc.value)


@pytest.mark.parametrize("bad", [
    [],
    [{"kind": "teleported", "family": "x"}],
    [{"kind": "increased"}],
    [{"kind": "appeared", "family": "x", "label": "l"}],
    [{"kind": "increased", "family": "x", "min_delta": "lots"}],
    [{"kind": "no_vanished_series", "allow": "everything"}],
])
def test_a_malformed_effects_section_is_refused_at_load(tmp_path, bad):
    """Refused at LOAD, not skipped at check time. A skipped effect is a
    silent pass wearing the clothes of a run one."""
    p = tmp_path / "floor.json"
    p.write_text(json.dumps({"surfaces": SURFACES, "effects": bad}))
    with pytest.raises(UsageError):
        load_floor_doc(p)


# ── 3. live-surface honesty ─────────────────────────────────────────────────

def test_frozen_exporter_is_frozen_not_witnessed(tmp_path):
    """A 200 is not evidence. Byte-identical payloads across every scrape,
    on a surface declaring counters that must move, is stale truth - and it
    must not read as a healthy WITNESSED."""
    m = tmp_path / "m.txt"
    m.write_text(BEFORE)
    floor = tmp_path / "floor.json"
    floor.write_text(json.dumps({"surfaces": SURFACES, "effects": EFFECTS}))

    assert gate(str(m), floor).verdict == WITNESSED, "one sample cannot show staleness"
    res = gate(str(m), floor, samples=3, interval_ms=0)
    assert res.verdict == FROZEN
    assert res.samples_taken == 3
    assert any("FROZEN" in v for v in res.violations)


def test_a_surface_that_moves_between_scrapes_is_not_frozen():
    frozen, why = frozen_check([BEFORE, AFTER], SURFACES, EFFECTS)
    assert not frozen
    assert "not frozen" in why


def test_a_gauge_only_surface_is_never_accused_of_being_frozen():
    """A false finding costs more trust than no finding (doctrine 6.4). A
    surface with no counter that must move has no staleness signal, and
    identical bytes there are merely identical bytes."""
    frozen, why = frozen_check(
        ["# TYPE g gauge\ng 1\n"] * 3, [{"name": "g", "pattern": "^g$"}], None)
    assert not frozen
    assert "not evidence of staleness" in why


def test_a_missing_surface_outranks_frozen_in_the_verdict(tmp_path):
    """Both facts are stated, but the verdict names the more fundamental
    one: telling someone their exporter is stale when the metric does not
    exist sends them to the wrong fix."""
    m = tmp_path / "m.txt"
    m.write_text('# TYPE http_requests_total counter\nhttp_requests_total 1\n')
    floor = tmp_path / "floor.json"
    floor.write_text(json.dumps({"surfaces": SURFACES}))
    res = gate(str(m), floor, samples=2, interval_ms=0)
    assert res.verdict == UNWITNESSED
    assert any("'jobs'" in v for v in res.violations)
    assert any("FROZEN" in v for v in res.violations)


def test_a_non_metrics_payload_is_diagnosed_as_such(tmp_path):
    """An HTML error page parses to zero samples exactly like an empty 200,
    and the two need different fixes."""
    m = tmp_path / "m.txt"
    m.write_text("<html><body>502 Bad Gateway</body></html>\n")
    floor = tmp_path / "floor.json"
    floor.write_text(json.dumps({"surfaces": SURFACES}))
    res = gate(str(m), floor)
    assert res.verdict == UNWITNESSED
    assert any("none of which parse" in v for v in res.violations)


def test_a_parser_crash_accuses_the_instrument_never_the_endpoint():
    """*Scar (6.4): a polling loop printed ten "no response" lines about an
    API serving 200s, because the poller's own formatting raised and a
    shell fallback spoke on the server's behalf.*"""
    def _exploding(_text):
        raise ZeroDivisionError("planted")

    samples, why = safe_parse("anything", parser=_exploding)
    assert samples == []
    assert why.startswith(INSTRUMENT + ":")
    assert "ZeroDivisionError" in why
    assert "NOT evidence about the endpoint" in why


# ── class ratchets (doctrine 2.1) ───────────────────────────────────────────

def test_every_declared_effect_kind_has_an_implementation():
    """A kind added to EFFECT_KINDS without a checker would be accepted by
    the manifest validator and then crash - or worse, be skipped."""
    assert set(_EFFECT_DISPATCH) == set(EFFECT_KINDS)


_PARTIES = {"instrument", "endpoint", "floor"}


def _every_failing_effect_result():
    """One planted failure per effect kind, plus the refusals. This walks
    the space rather than listing three examples, so a detector added later
    that forgets its party is caught by this test, not by a reader."""
    b, a = _snap(BEFORE), _snap(AFTER, "T2")
    gone = _snap("\n".join(ln for ln in AFTER.splitlines()
                           if not ln.startswith("jobs_")) + "\n", "T2")
    drifted = _snap(AFTER.replace(
        'http_requests_total{route="/api/orders",method="POST"} 112',
        'http_requests_total{route="/api/orders",method="POST",tenant="t1"} 112'),
        "T2")
    cases = [
        ([{"kind": "increased", "family": "http_requests_total"}], a, b),
        ([{"kind": "increased", "family": "queue_depth"}], b, a),
        ([{"kind": "increased", "family": "absent_total"}], b, a),
        ([{"kind": "increased", "family": "jobs_fired_total"}], b, gone),
        ([{"kind": "appeared", "family": "http_requests_total",
           "label": "route", "value": "/never"}], b, a),
        ([{"kind": "appeared", "family": "absent_total"}], b, a),
        ([{"kind": "no_vanished_series"}], b, gone),
        ([{"kind": "no_vanished_series"}], {"families": {}}, a),
        ([{"kind": "stable_labels", "family": "http_requests_total"}], b, drifted),
        ([{"kind": "stable_labels", "family": "nope"}], b, a),
    ]
    return [_one(*c) for c in cases]


def test_no_effect_failure_is_ever_unattributed():
    """Doctrine 2.4 + 6.4 as a ratchet: an instrument whose error branch cannot
    say WHOSE failure it is reports the wrong outage with total confidence,
    and it always reports it about the system."""
    results = _every_failing_effect_result()
    assert len(results) == 10
    for r in results:
        assert r.verdict != WITNESSED, f"planted failure passed: {r}"
        assert r.party in _PARTIES, f"unattributed failure: {r}"
        assert r.detail.strip(), f"verdict with no diagnosis: {r}"


def test_every_effect_miss_states_a_direction():
    """Doctrine 2.4: a miss without a direction is a verdict whose word is
    wrong, and nobody re-derives a figure that arrived with a confident
    label. Each NOT_WITNESSED must say which way it missed."""
    for r in _every_failing_effect_result():
        if r.verdict != NOT_WITNESSED:
            continue
        assert ("expected-" in r.detail or "GONE" in r.detail
                or "drift" in r.detail), f"directionless miss: {r.detail}"


def test_no_floor_violation_is_ever_unattributed():
    """The same ratchet over the single-payload gate. Every violation
    string this tool can emit starts with one of the three parties."""
    from sutradhar_guards.obsgate import Sample, parse_metrics

    cases = [
        check_floor([], SURFACES),
        check_floor(parse_metrics("http_requests_total 1\n"), SURFACES),
        check_floor(
            parse_metrics("jobs_fired_total 1\n")
            + [Sample("http_requests_total", {"route": f"/u/{i}"}, 1.0)
               for i in range(12)],
            [{"name": "requests", "pattern": "^http_requests_total$",
              "max_label_cardinality": {"route": 5}}]),
    ]
    seen = 0
    for res in cases:
        assert res.violations, "a planted floor breach produced no violation"
        for v in res.violations:
            seen += 1
            assert v.split(":")[0] in _PARTIES, f"unattributed violation: {v}"
    assert seen >= 3


# ── the declared envelope (doctrine 1.1) ────────────────────────────────────

def _synthetic(n_series: int, bump: int = 0, families: int = 100) -> str:
    per = n_series // families
    out = []
    for f in range(families):
        out.append(f"# TYPE fam_{f}_total counter")
        for i in range(per):
            out.append(
                f'fam_{f}_total{{route="/api/r{i}",method="GET",zone="z{i % 7}"}} '
                f"{i + bump}"
            )
    return "\n".join(out) + "\n"


def test_snapshot_holds_its_declared_envelope():
    """`b.n` IS the 10,000 declared in docs/design/obsgate-depth.md. Nobody
    hand-picks a comfortable size here: raising the design N makes this test
    harder, and lowering it is a diff someone reviews.

    The memory ceiling is a tripwire, not a fit. The shape that breaks it is
    a change that retains per-series state across families - which is
    exactly the patch anyone reaches for the first time a snapshot cannot
    answer something.
    """
    n = get_budget("obsgate-snapshot", root=DESIGN).n
    before_text, after_text = _synthetic(n, 0), _synthetic(n, 1)
    effects = [
        {"kind": "increased", "family": "fam_0_total"},
        {"kind": "no_vanished_series"},
        {"kind": "stable_labels"},
    ]
    with budget("obsgate-snapshot", root=DESIGN) as b:
        before = build_snapshot(before_text, "synthetic", captured_at="T1")
        after = build_snapshot(after_text, "synthetic", captured_at="T2")
        res = check_effects(before, after, effects)

    assert before["series_total"] == b.n
    assert res.all_ok, [r.detail for r in res.results if not r.ok]


# ── the CLI seam ────────────────────────────────────────────────────────────

def _cli(*args: str) -> subprocess.CompletedProcess:
    import os

    import sutradhar_guards

    env = dict(os.environ)
    pkg_parent = str(Path(sutradhar_guards.__path__[0]).parent)
    env["PYTHONPATH"] = os.pathsep.join(
        [pkg_parent, env["PYTHONPATH"]] if env.get("PYTHONPATH") else [pkg_parent]
    )
    return subprocess.run(
        [sys.executable, "-m", "sutradhar_guards.obsgate", *args],
        capture_output=True, text=True, env=env, timeout=180,
    )


def _fixtures(tmp_path: Path, effects=EFFECTS):
    (tmp_path / "before.txt").write_text(BEFORE)
    (tmp_path / "after.txt").write_text(AFTER)
    doc = {"surfaces": SURFACES}
    if effects is not None:
        doc["effects"] = effects
    (tmp_path / "floor.json").write_text(json.dumps(doc))
    return tmp_path


def test_cli_snapshot_then_effects_round_trip(tmp_path):
    d = _fixtures(tmp_path)
    assert _cli("snapshot", "--metrics", str(d / "before.txt"),
                "--out", str(d / "b.json")).returncode == 0
    assert _cli("snapshot", "--metrics", str(d / "after.txt"),
                "--out", str(d / "a.json")).returncode == 0
    ok = _cli("effects", "--before", str(d / "b.json"), "--after",
              str(d / "a.json"), "--floor", str(d / "floor.json"))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "4 of 4 witnessed" in ok.stdout

    # the same pair, backwards: the change is not witnessed and says why
    bad = _cli("effects", "--before", str(d / "a.json"), "--after",
               str(d / "b.json"), "--floor", str(d / "floor.json"))
    assert bad.returncode == 1
    assert COUNTER_RESET in bad.stdout


def test_cli_effects_without_an_effects_section_exits_2_not_0(tmp_path):
    d = _fixtures(tmp_path, effects=None)
    _cli("snapshot", "--metrics", str(d / "before.txt"), "--out", str(d / "b.json"))
    _cli("snapshot", "--metrics", str(d / "after.txt"), "--out", str(d / "a.json"))
    proc = _cli("effects", "--before", str(d / "b.json"), "--after",
                str(d / "a.json"), "--floor", str(d / "floor.json"))
    assert proc.returncode == 2, "a manifest with nothing to check must refuse"
    assert "NOTHING to check" in proc.stderr


def test_cli_snapshot_refuses_a_dead_endpoint_and_writes_nothing(tmp_path):
    out = tmp_path / "snap.json"
    proc = _cli("snapshot", "--metrics", "http://127.0.0.1:1/metrics",
                "--out", str(out))
    assert proc.returncode == 3
    assert not out.exists(), "a snapshot of nothing must not reach the disk"


def test_cli_frozen_exit_code_is_reachable_only_with_samples(tmp_path):
    d = _fixtures(tmp_path)
    plain = _cli("check", "--metrics", str(d / "before.txt"),
                 "--floor", str(d / "floor.json"))
    assert plain.returncode == 0
    sampled = _cli("check", "--metrics", str(d / "before.txt"), "--floor",
                   str(d / "floor.json"), "--samples", "3", "--interval-ms", "0")
    assert sampled.returncode == 4
    assert FROZEN in sampled.stdout


def test_the_legacy_invocation_is_untouched(tmp_path):
    """Backward compatibility is a promise, so it is a test. Subcommands
    EXTEND the CLI; an adopter's pipeline does not move."""
    d = _fixtures(tmp_path)
    proc = _cli("--metrics", str(d / "before.txt"), "--floor", str(d / "floor.json"))
    assert proc.returncode == 0
    assert WITNESSED in proc.stdout


@pytest.mark.parametrize("args", [
    ("--zzz-bogus",),
    ("check", "--zzz-bogus"),
    ("snapshot", "--zzz-bogus"),
    ("effects", "--zzz-bogus"),
    ("teleport",),
    ("snapshot", "--before", "x"),          # another subcommand's flag
    ("effects", "--metrics", "x"),          # ditto
    ("snapshot", "--metrics"),              # flag with no value
])
def test_every_path_refuses_what_it_does_not_understand(args):
    """Doctrine, round 4: if an unrecognised flag exits 0, then so does
    `--selfcheck`, for the same reason - nothing parsed it."""
    proc = _cli(*args)
    assert proc.returncode == 2, f"{args} exited {proc.returncode}"
    assert INSTRUMENT in proc.stderr, "a usage error is the instrument's, and says so"
