"""Suite-level pytest guards for hydrospectral-lab.

An empty test run must fail loudly rather than exit cleanly over zero collected
tests.
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(session, config, items) -> None:  # noqa: ANN001, ARG001
    if not items:
        raise pytest.UsageError(
            "pytest collected zero tests; an empty test suite is treated as a failure."
        )
