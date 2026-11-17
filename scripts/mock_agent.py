"""Run the full agent loop with the stub model and an offline ZillAPI (no keys, no cost).

    python scripts/mock_agent.py
"""

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import set_tracing_disabled  # noqa: E402

from zillapi_agents import ZillapiClient, ZillapiTools  # noqa: E402
from zillapi_agents.agent import build_agent, run_agent  # noqa: E402
from zillapi_agents.fixtures import fixture_transport  # noqa: E402
from zillapi_agents.stub_model import StubModel  # noqa: E402


async def main() -> None:
    set_tracing_disabled(True)
    client = ZillapiClient("zk_demo", http=httpx.AsyncClient(transport=fixture_transport()))
    await run_agent(build_agent(ZillapiTools(client), model=StubModel()))


asyncio.run(main())
