# Copyright 2026 Varun Mundra. Licensed under the Apache License, Version 2.0.
# Part of Sutradhar: https://github.com/sutradharhq/sutradhar
"""obsgate through its real seams: the library calls a conftest would make
and the CLI a pipeline would run (doctrine 2.3). The selfcheck covers the
detection logic; these pin the seam behaviour - exit codes, verdict mapping,
and the refusals a caller will actually depend on."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sutradhar_guards.obsgate import (
    INCONCLUSIVE,
    UNWITNESSED,
    WITNESSED,
    check_floor,
    gate,
    load_floor,
    parse_metrics,
)

GOOD = """\
http_requests_total{route="/api/users/:id"} 100
jobs_fired_total 5
dependency_up{dep="db"} 1
"""

FLOOR = [
    {"name": "requests", "pattern": "^http_requests_total$",
     "max_label_cardinality": {"route": 10}},
    {"name": "jobs", "pattern": "^jobs_fired_total$"},
    {"name": "deps", "pattern": "^dependency_up$"},
]


def _floor_file(tmp_path: Path, surfaces=None) -> Path:
    p = tmp_path / "floor.json"
    p.write_text(json.dumps({"surfaces": surfaces or FLOOR}))
    return p


def test_complete_floor_is_witnessed(tmp_path):
    m = tmp_path / "m.txt"
    m.write_text(GOOD)
    res = gate(str(m), _floor_file(tmp_path))
    assert res.verdict == WITNESSED
    assert res.series_seen == 3


def test_empty_payload_is_refused_with_the_empty_200_diagnosis(tmp_path):
    m = tmp_path / "m.txt"
    m.write_text("# HELP nothing here\n")
    res = gate(str(m), _floor_file(tmp_path))
    assert res.verdict == UNWITNESSED
    assert any("no series at all" in v for v in res.violations)


def test_missing_surface_is_named(tmp_path):
    m = tmp_path / "m.txt"
    m.write_text("http_requests_total 1\njobs_fired_total 1\n")
    res = gate(str(m), _floor_file(tmp_path))
    assert res.verdict == UNWITNESSED
    assert any("'deps'" in v for v in res.violations)


def test_unreadable_source_is_inconclusive_not_a_pass(tmp_path):
    res = gate(str(tmp_path / "absent.txt"), _floor_file(tmp_path))
    assert res.verdict == INCONCLUSIVE
    assert res.verdict != WITNESSED


def test_cardinality_bomb_is_caught():
    samples = parse_metrics(
        "\n".join(f'http_requests_total{{route="/u/{i}"}} 1' for i in range(20))
        + "\njobs_fired_total 1\ndependency_up 1"
    )
    res = check_floor(samples, FLOOR)
    assert res.verdict == UNWITNESSED
    assert any("distinct" in v for v in res.violations)


def test_empty_floor_manifest_is_refused(tmp_path):
    p = tmp_path / "floor.json"
    p.write_text('{"surfaces": []}')
    with pytest.raises(ValueError):
        load_floor(p)


def test_bad_pattern_is_refused_at_load_not_at_check(tmp_path):
    p = tmp_path / "floor.json"
    p.write_text(json.dumps({"surfaces": [{"name": "x", "pattern": "("}]}))
    with pytest.raises(ValueError):
        load_floor(p)


def test_parser_reads_labels_values_and_timestamps():
    s = parse_metrics('m_total{a="x",b="y"} 4.5 1700000000\nplain 2\n')
    assert [x.name for x in s] == ["m_total", "plain"]
    assert s[0].labels == {"a": "x", "b": "y"}
    assert s[0].value == 4.5


# ── the CLI seam ────────────────────────────────────────────────────────────

def _cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    import os

    import sutradhar_guards

    env = dict(os.environ)
    pkg_parent = str(Path(sutradhar_guards.__path__[0]).parent)
    env["PYTHONPATH"] = os.pathsep.join(
        [pkg_parent, env["PYTHONPATH"]] if env.get("PYTHONPATH") else [pkg_parent]
    )
    return subprocess.run(
        [sys.executable, "-m", "sutradhar_guards.obsgate", *args],
        capture_output=True, text=True, env=env, timeout=120,
    )


def test_cli_exit_codes_encode_the_tri_state(tmp_path):
    floor = _floor_file(tmp_path)
    good = tmp_path / "good.txt"
    good.write_text(GOOD)
    empty = tmp_path / "empty.txt"
    empty.write_text("")

    assert _cli(tmp_path, "--metrics", str(good), "--floor", str(floor)).returncode == 0
    assert _cli(tmp_path, "--metrics", str(empty), "--floor", str(floor)).returncode == 1
    assert _cli(tmp_path, "--metrics", str(tmp_path / "nope.txt"),
                "--floor", str(floor)).returncode == 3


def test_cli_usage_errors_exit_2(tmp_path):
    assert _cli(tmp_path, "--metrics", "x.txt").returncode == 2   # no --floor
    assert _cli(tmp_path, "--zzz-bogus").returncode == 2           # unknown flag
