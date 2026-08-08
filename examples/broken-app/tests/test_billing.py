"""PLANTED DEFECT 5 (doctrine 2.2): a guard that cannot fail.

This is the scar, reproduced: the test sets up the arithmetic by hand and
asserts on its own copy of it. It never calls `total()`. Delete the bulk
discount from app/billing.py and this test stays green - so it guards
nothing, while reading in review exactly like a test that does.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.billing import total


def test_bulk_discount_applies():
    subtotal = 1000 * 0.5
    subtotal *= 0.9              # the test re-implements the fix locally
    assert subtotal == 450.0


def test_small_orders_are_undiscounted():
    assert total(10, 0.5) == 5.0
