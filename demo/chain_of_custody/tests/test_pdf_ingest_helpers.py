from __future__ import annotations

import pytest

from demo.chain_of_custody.stages import pdf_ingest


def test_require_positive_int_accepts_positive_int():
    assert pdf_ingest._require_positive_int(5, "param") == 5


@pytest.mark.parametrize("value", [0, -1, 1.5, "a", True])
def test_require_positive_int_rejects_invalid(value):
    with pytest.raises(ValueError):
        pdf_ingest._require_positive_int(value, "param")
