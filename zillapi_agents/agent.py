"""An OpenAI Agents SDK agent with ZillAPI tools, streamed to stdout.

    python -m zillapi_agents.agent "Find 3-bed homes for sale in Austin under $500k and give me their Zestimates"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Callable

from agents import Agent, Model, Runner
from openai.types.responses import ResponseTextDeltaEvent

from .tools import ZillapiTools

INSTRUCTIONS = """You are a real estate research assistant with live Zillow property data via ZillAPI tools.
- Listing search needs a bounding box. Estimate the bbox for the city or neighborhood the user names.
- Keep searches small (max_items 3 to 5) because every row costs a credit.
- If a search row has no Zestimate, call get_zestimate with its zpid.
- Answer with a short table: address, list price, beds/baths, sqft, Zestimate, and the Zillow link.
- Never invent numbers. If a tool returns an error, say so."""

DEFAULT_PROMPT = "Find 3-bed homes for sale in Austin, TX under $500k and give me their Zestimates. Show 3."


def build_agent(tools: ZillapiTools | None = None, model: str | Model | None = None) -> Agent:
    return Agent(
        name="ZillAPI real estate assistant",
        instructions=INSTRUCTIONS,
        tools=(tools or ZillapiTools()).as_function_tools(),
        model=model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini"),
    )


def _short(value: object, limit: int = 160) -> str:
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return s if len(s) <= limit else s[: limit - 3] + "..."


async def run_agent(
    agent: Agent,
    prompt: str = DEFAULT_PROMPT,
    write: Callable[[str], object] = lambda s: (sys.stdout.write(s), sys.stdout.flush()),
):
    result = Runner.run_streamed(agent, prompt, max_turns=8)
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            write(event.data.delta)
        elif event.type == "run_item_stream_event":
            if event.item.type == "tool_call_item":
                raw = event.item.raw_item
                write(f"\n[tool] {getattr(raw, 'name', '?')}({getattr(raw, 'arguments', '')})\n")
            elif event.item.type == "tool_call_output_item":
                write(f"[tool] -> {_short(event.item.output)}\n\n")
    write("\n")
    return result


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Set OPENAI_API_KEY (or pass any Agents SDK Model to build_agent).")
    tools = ZillapiTools()
    try:
        await run_agent(build_agent(tools), " ".join(sys.argv[1:]) or DEFAULT_PROMPT)
    finally:
        await tools.client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
