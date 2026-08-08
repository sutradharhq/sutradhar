import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.mark.billing_integration
def test_end_to_end_invoice_arithmetic():
    # The test that would actually catch a billing error. It has never run.
    from app.billing import total
    assert total(1000, 0.5) == 450.0
