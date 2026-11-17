"""A deterministic stand-in for an LLM, so you can run the whole agent loop with no model key or cost.

It behaves like a good tool-calling model for the demo prompt:
turn 1 searches Austin, turn 2 fetches missing Zestimates, turn 3 streams a table.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

from agents import Model, ModelResponse, Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)

AUSTIN_SEARCH = {
    "bbox": {"west": -97.94, "south": 30.10, "east": -97.56, "north": 30.52},
    "status": "for_sale",
    "location": "Austin, TX",
    "price_min": None,
    "price_max": 500000,
    "beds_min": 3,
    "beds_max": 3,
    "baths_min": None,
    "home_types": None,
    "max_items": 3,
}


def _tool_results(items: Any) -> dict[str, list[Any]]:
    """Map tool name -> list of parsed outputs from the conversation history."""
    if isinstance(items, str):
        return {}
    names: dict[str, str] = {}
    out: dict[str, list[Any]] = {}
    for item in items:
        item = item if isinstance(item, dict) else item.model_dump()
        if item.get("type") == "function_call":
            names[item["call_id"]] = item["name"]
        elif item.get("type") == "function_call_output":
            raw = item.get("output")
            try:
                value = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                value = raw
            out.setdefault(names.get(item["call_id"], "?"), []).append(value)
    return out


def _usd(n: Any) -> str:
    return f"${n:,.0f}" if isinstance(n, (int, float)) else "n/a"


class StubModel(Model):
    def _next_output(self, input: Any) -> list[Any] | str:
        results = _tool_results(input)
        search = (results.get("search_listings") or [None])[0]
        if not search:
            return [_call("search_listings", AUSTIN_SEARCH, 0)]

        rows = search.get("results", [])
        missing = [r for r in rows if r.get("zestimate") is None]
        if missing and "get_zestimate" not in results:
            return [_call("get_zestimate", {"zpid": r["zpid"]}, i) for i, r in enumerate(missing)]

        z_by_zpid = {z.get("zpid"): z.get("zestimate") for z in results.get("get_zestimate", [])}
        lines = [
            f"Here are {len(rows)} 3-bed homes for sale in Austin under $500k:",
            "",
            "| Address | List price | Beds/Baths | Sqft | Zestimate | Link |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            z = r.get("zestimate") if r.get("zestimate") is not None else z_by_zpid.get(r["zpid"])
            lines.append(
                f"| {r['address']} | {_usd(r['price'])} | {r['beds']}/{r['baths']} | {r['sqft']} | {_usd(z)} | {r['url']} |"
            )
        return "\n".join(lines)

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **_):
        out = self._next_output(input)
        output = [_message(out)] if isinstance(out, str) else out
        return ModelResponse(output=output, usage=Usage(requests=1), response_id=None)

    async def stream_response(
        self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **_
    ) -> AsyncIterator[Any]:
        out = self._next_output(input)
        seq = 0
        if isinstance(out, str):
            for word in out.split(" "):
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    item_id="msg_stub",
                    output_index=0,
                    content_index=0,
                    delta=word + " ",
                    logprobs=[],
                    sequence_number=seq,
                )
                seq += 1
            output = [_message(out)]
        else:
            output = out
        yield ResponseCompletedEvent(
            type="response.completed",
            sequence_number=seq,
            response=Response(
                id="resp_stub",
                created_at=time.time(),
                model="stub",
                object="response",
                output=output,
                parallel_tool_calls=True,
                tool_choice="auto",
                tools=[],
            ),
        )


def _call(name: str, args: dict[str, Any], i: int) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        type="function_call", id=f"fc_{name}_{i}", call_id=f"call_{name}_{i}", name=name, arguments=json.dumps(args)
    )


def _message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        type="message",
        id="msg_stub",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )
