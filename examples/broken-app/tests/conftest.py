"""PLANTED DEFECT 6 (the ~86-tests incident): a skip gate nothing sets.

`BILLING_TESTS` is not set by any workflow, Makefile, or compose file in
this example. So test_billing_integration below never runs anywhere, while
the suite counts it and reports green. A skip marker nothing sets is
indistinguishable from a deleted test.
"""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "billing_integration" in item.keywords and not os.environ.get("BILLING_TESTS"):
            item.add_marker(pytest.mark.skip(reason="needs BILLING_TESTS"))


def pytest_configure(config):
    config.addinivalue_line("markers", "billing_integration: needs the billing stack")
