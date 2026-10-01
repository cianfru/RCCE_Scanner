import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _hl_budget_never_waits(monkeypatch):
    """Code under test that posts to Hyperliquid (through fakes) must not wait on the process's
    shared weight budget in real time; tests of the budget build their own with a fake clock."""
    import hl_calls
    monkeypatch.setattr(hl_calls, "budget", hl_calls.unlimited())
