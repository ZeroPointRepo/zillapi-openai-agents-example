import json

import httpx
from agents import FunctionTool

from zillapi_agents import ZillapiClient, ZillapiTools, compact_row
from zillapi_agents.agent import build_agent, run_agent
from zillapi_agents.fixtures import SEARCH_ROWS, ZESTIMATE, body, fixture_transport
from zillapi_agents.stub_model import StubModel


def make(calls=None, overrides=None):
    http = httpx.AsyncClient(transport=fixture_transport(calls, overrides))
    return ZillapiTools(ZillapiClient("zk_test", http=http))


def test_compact_row():
    assert compact_row(SEARCH_ROWS[0]) == {
        "zpid": "1000001",
        "address": "101 Example Ln, Austin, TX 78745",
        "price": 449000,
        "beds": 3,
        "baths": 2,
        "sqft": 1520,
        "home_type": "SINGLE_FAMILY",
        "status": "FOR_SALE",
        "zestimate": 452300,
        "rent_zestimate": None,
        "days_on_zillow": 12,
        "url": "https://www.zillow.com/homedetails/1000001_zpid/",
    }


def test_compact_row_detail_style_address():
    from zillapi_agents.fixtures import NEARBY_ROWS

    assert compact_row(NEARBY_ROWS[0])["address"] == "404 Demo Ave, Austin, TX 78745"
    row = compact_row(NEARBY_ROWS[1])
    assert (row["price"], row["beds"], row["baths"], row["sqft"], row["status"]) == (410000, 3, 2, 1144, "RECENTLY_SOLD")
    assert row["url"] == "https://www.zillow.com/homedetails/1000005_zpid/"


async def test_get_comparables():
    out = await make().get_comparables("1000001")
    assert out["count"] == 2 and out["comparables"][1]["beds"] == 3


def test_function_tools_have_strict_schemas_and_docs():
    tools = make().as_function_tools()
    assert all(isinstance(t, FunctionTool) for t in tools)
    assert [t.name for t in tools] == [
        "search_listings",
        "get_property",
        "get_property_by_address",
        "get_zestimate",
        "get_comparables",
    ]
    search = tools[0]
    assert search.strict_json_schema
    assert "bounding box" in search.description.lower()
    props = search.params_json_schema["properties"]
    assert props["max_items"]["maximum"] == 20
    assert props["bbox"]["$ref"].endswith("BoundingBox")
    assert props["price_max"]["description"] == "Maximum price in dollars."


async def test_search_maps_filters():
    calls = []
    out = await make(calls).search_listings(
        bbox={"west": -97.94, "south": 30.1, "east": -97.56, "north": 30.52},
        beds_min=3,
        beds_max=3,
        price_max=500000,
        max_items=3,
    )
    assert body(calls[0]) == {
        "filters": {
            "status": "for_sale",
            "bbox": {"west": -97.94, "south": 30.1, "east": -97.56, "north": 30.52},
            "price": {"max": 500000},
            "beds": {"min": 3, "max": 3},
        },
        "maxItems": 3,
    }
    assert out["count"] == 3 and out["results"][1]["zestimate"] is None


async def test_get_property_by_zpid_or_url():
    calls = []
    t = make(calls)
    await t.get_property(zpid="1000001")
    await t.get_property(url="https://www.zillow.com/homedetails/1000001_zpid/")
    assert calls[0].url.path == "/v1/properties/1000001"
    assert "zestimate" in calls[0].url.params["fields"]
    assert calls[1].url.path == "/v1/properties/by-url"
    assert (await t.get_property())["error"]["code"] == "missing_input"
    assert (await t.get_zestimate("abc"))["error"]["code"] == "invalid_zpid"
    assert len(calls) == 2  # invalid input never hits the API


async def test_api_errors_are_returned_to_the_model():
    def nf(_):
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "no such zpid"}})

    out = await make(overrides={"GET /v1/properties/999/zestimate": nf}).get_zestimate("999")
    assert out == {"error": {"code": "not_found", "message": "no such zpid"}}


async def test_tool_invocation_through_the_sdk():
    """Call the FunctionTool the way the Runner does: JSON args in, string out."""
    from agents.tool_context import ToolContext

    calls = []
    tool = make(calls).as_function_tools()[3]  # get_zestimate
    ctx = ToolContext(context=None, tool_name=tool.name, tool_call_id="c1", tool_arguments='{"zpid": "1000002"}')
    out = await tool.on_invoke_tool(ctx, '{"zpid": "1000002"}')
    assert calls[0].url.path == "/v1/properties/1000002/zestimate"
    assert json.loads(out) == {"zpid": "1000002", **ZESTIMATE}  # compact JSON, not a Python repr


async def test_full_agent_run_with_stub_model_streams_table():
    calls = []
    agent = build_agent(make(calls), model=StubModel())
    chunks = []
    result = await run_agent(agent, write=chunks.append)
    out = "".join(chunks)

    assert [f"{r.method} {r.url.path}" for r in calls] == [
        "POST /v1/search",
        "GET /v1/properties/1000002/zestimate",
    ]
    assert "[tool] search_listings(" in out
    assert "[tool] get_zestimate(" in out
    assert "| 202 Sample Dr, Austin, TX 78744 | $389,900 | 3/2 | 1340 | $395,000 |" in result.final_output
    assert "$452,300" in out  # streamed text deltas reached the writer
