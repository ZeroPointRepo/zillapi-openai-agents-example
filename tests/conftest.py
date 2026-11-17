import sys
from pathlib import Path

import pytest
from agents import set_tracing_disabled

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
set_tracing_disabled(True)


@pytest.fixture(autouse=True)
def _no_real_key(monkeypatch):
    # Guard against accidentally using a real key or the network in tests.
    monkeypatch.delenv("ZILLAPI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
