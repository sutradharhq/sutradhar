"""The kind of test suite that ships with a codebase like this.

Every test here passes. Not one of them can see any of the three defects in
app/readings.py, because each asserts that the happy path works - and the
happy path does work.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.readings import Store, latest_readings, readings_for


def test_latest_readings_returns_the_rows():
    store = Store({7: {"kwh": 12.5}})
    assert latest_readings(store, 7) == {"kwh": 12.5}


def test_unknown_meter_is_empty():
    assert latest_readings(Store({}), 99) == {}


def test_query_mentions_the_meter():
    # Asserts the string contains what we expect. Says nothing about the
    # interpolation hole, and never will.
    assert "42" in readings_for(42)
