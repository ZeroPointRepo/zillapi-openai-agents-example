# Zillow data in the OpenAI Agents SDK (ZillAPI example)

Give an OpenAI Agents SDK agent live Zillow property data: listing search, property details, Zestimates, Rent Zestimates and comps, as five function tools powered by [ZillAPI](https://zillapi.com).

```python
from agents import Agent, Runner
from zillapi_agents import ZillapiTools

agent = Agent(
    name="Real estate assistant",
    instructions="Use the ZillAPI tools. Never invent numbers.",
    tools=ZillapiTools().as_function_tools(),  # reads ZILLAPI_API_KEY
)
result = Runner.run_sync(agent, "Find 3-bed homes for sale in Austin under $500k and give me their Zestimates")
print(result.final_output)
```

Built and tested with `openai-agents==0.24.0` on Python 3.12 (3.10+ supported).

## Tools

| Tool | ZillAPI endpoint | Credits |
|---|---|---|
| `search_listings` | `POST /v1/search` (bounding box + price, beds, baths, home type) | 1 per row returned (capped by `max_items`, default 5) |
| `get_property` | `GET /v1/properties/{zpid}` or `GET /v1/properties/by-url` | 1 |
| `get_property_by_address` | `GET /v1/properties/by-address` | 3 |
| `get_zestimate` | `GET /v1/properties/{zpid}/zestimate` | 1 |
| `get_comparables` | `GET /v1/properties/{zpid}/nearby` | 1 |

The tools are plain async methods on `ZillapiTools`, so you can also call them directly from your own code. `as_function_tools()` turns them into strict-schema `FunctionTool`s; the JSON schemas and descriptions come from the type hints and docstrings.

Notes that matter for agents:

- **Search needs a bounding box.** ZillAPI does not accept a bare city name for search. The tool docstring tells the model to estimate the bbox itself, for example Austin, TX is roughly `west=-97.94, south=30.10, east=-97.56, north=30.52`.
- **Property lookups are projected** with `?fields=` so the model gets about 15 useful fields instead of the full 300+ field record. Edit `PROPERTY_FIELDS` in `zillapi_agents/tools.py` to add price history, schools, agent contact and more.
- **Tool output is compact JSON**, and API errors come back as `{"error": {"code", "message"}}` so the agent can explain or retry. 429 and 5xx responses are retried with backoff.
- Search rows do not always include a Zestimate. The agent instructions tell the model to call `get_zestimate` for those rows.

## Setup

```bash
git clone https://github.com/ZeroPointRepo/zillapi-openai-agents-example
cd zillapi-openai-agents-example
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ZILLAPI_API_KEY=zk_...   # free, 100 credits, no card: https://zillapi.com/signup
export OPENAI_API_KEY=sk-...
```

Plans and top-ups: [zillapi.com/pricing](https://zillapi.com/pricing/). The Agents SDK can also run non-OpenAI models; pass any `Model` to `build_agent(model=...)`.

## Run

```bash
# Full agent, streaming (uses your model key + a few ZillAPI credits)
python -m zillapi_agents.agent "Find 3-bed homes for sale in Austin under $500k and give me their Zestimates"

# Just the tools, no LLM
python scripts/tools_demo.py --zpid <zpid>                              # 2 credits
python scripts/tools_demo.py --address "<street>, <city>, <ST> <zip>"   # 3 credits

# Whole agent loop offline: stub model + mocked ZillAPI (no keys, no cost)
python scripts/mock_agent.py

# Tests (mocked HTTP, no network)
pytest -q
```

## Sample output

`scripts/tools_demo.py` against the live API on 2026-11-17 (street addresses, ZIP codes and zpids masked):

```text
get_property -> {
  "zpid": "294xxxxx",
  "address": { "streetAddress": "[masked]", "city": "Austin", "state": "TX", "zipcode": "[masked]", "subdivision": "Windsor Park" },
  "price": 375000, "bedrooms": 3, "bathrooms": 1, "livingArea": 1296, "lotSize": 7065,
  "yearBuilt": 1955, "homeType": "SINGLE_FAMILY", "homeStatus": "FOR_SALE", ...
}
get_comparables (first 3) -> {
  "zpid": "294xxxxx",
  "count": 8,
  "comparables": [
    { "zpid": "294xxxxx", "address": "[masked], Austin, TX", "sqft": 1350, "home_type": "SINGLE_FAMILY", ... },
    { "zpid": "294xxxxx", "address": "[masked], Austin, TX", "sqft": 1144, "home_type": "SINGLE_FAMILY", ... },
    { "zpid": "294xxxxx", "address": "[masked], Austin, TX", "sqft": 888, "home_type": "SINGLE_FAMILY", ... }
  ]
}
get_property_by_address -> {
  "zpid": "644xxxxx",
  "address": { "streetAddress": "[masked]", "city": "Austin", "state": "TX", "zipcode": "[masked]", ... },
  "price": 325000, "bedrooms": 3, "bathrooms": 3, "livingArea": 2170, "lotSize": 6477,
  "yearBuilt": 2003, "homeType": "SINGLE_FAMILY", "homeStatus": "FOR_SALE", ...
}
```

`python scripts/mock_agent.py` (stub model, synthetic data) shows how the agent streams tool calls and the answer:

```text
[tool] search_listings({"bbox": {"west": -97.94, "south": 30.1, "east": -97.56, "north": 30.52}, "status": "for_sale", "location": "Austin, TX", "price_min": null, "price_max": 500000, "beds_min": 3, "beds_max": 3, "baths_min": null, "home_types": null, "max_items": 3})
[tool] -> {"count":3,"results":[{"zpid":"1000001","address":"101 Example Ln, Austin, TX 78745","price":449000,...

[tool] get_zestimate({"zpid": "1000002"})
[tool] -> {"zpid":"1000002","zestimate":395000,"rent_zestimate":2200,"tax_assessed_value":351000,"last_sold_price":310000,"currency":"USD"}

Here are 3 3-bed homes for sale in Austin under $500k:

| Address | List price | Beds/Baths | Sqft | Zestimate | Link |
|---|---|---|---|---|---|
| 101 Example Ln, Austin, TX 78745 | $449,000 | 3/2 | 1520 | $452,300 | https://www.zillow.com/homedetails/1000001_zpid/ |
| 202 Sample Dr, Austin, TX 78744 | $389,900 | 3/2 | 1340 | $395,000 | https://www.zillow.com/homedetails/1000002_zpid/ |
| 303 Placeholder Ct, Austin, TX 78748 | $495,000 | 3/2.5 | 1810 | $488,100 | https://www.zillow.com/homedetails/1000003_zpid/ |
```

## Prefer MCP? Use the hosted ZillAPI MCP server

If you would rather not maintain tool code, point the Agents SDK at ZillAPI's hosted MCP server (`https://api.zillapi.com/mcp`, streamable HTTP, same API key):

```python
import asyncio
import os

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp


async def main() -> None:
    async with MCPServerStreamableHttp(
        name="zillapi",
        params={
            "url": "https://api.zillapi.com/mcp",
            "headers": {"Authorization": f"Bearer {os.environ['ZILLAPI_API_KEY']}"},
        },
    ) as zillapi:
        agent = Agent(name="Real estate assistant", mcp_servers=[zillapi])
        result = await Runner.run(agent, "What is the Zestimate for zpid <zpid>?")
        print(result.final_output)


asyncio.run(main())
```

The function tools in this repo give you tighter control over cost (`max_items`, field projection) and output shape; MCP gives you zero code and the same tools in Claude, ChatGPT, Cursor and Claude Code. Setup guides: [zillapi.com/blog](https://zillapi.com/blog/).

## Project layout

```text
zillapi_agents/client.py      async ZillAPI REST client (httpx, retries, error codes)
zillapi_agents/tools.py       ZillapiTools: five async methods + as_function_tools()
zillapi_agents/agent.py       Agent + Runner.run_streamed CLI
zillapi_agents/stub_model.py  deterministic stub Model for offline runs and tests
zillapi_agents/fixtures.py    synthetic API responses + offline httpx transport
scripts/                      tools_demo (live, no LLM) and mock_agent (offline)
tests/                        pytest suite, mocked HTTP only
```

## Links

- ZillAPI: [zillapi.com](https://zillapi.com) · [Sign up free (100 credits)](https://zillapi.com/signup) · [Pricing](https://zillapi.com/pricing/)
- Docs: [zillapi.com/docs](https://zillapi.com/docs) · [OpenAPI spec](https://zillapi.com/openapi.json) · [llms.txt](https://zillapi.com/llms.txt)
- Other integrations: [MCP server](https://github.com/ZeroPointRepo/zillow-mcp) · [Agent skills](https://github.com/ZeroPointRepo/zillow-skills) · [CrewAI tool](https://pypi.org/project/crewai-zillapi/) · [Vercel AI SDK example](https://github.com/ZeroPointRepo/zillapi-vercel-ai-sdk-example) · [YouTube](https://www.youtube.com/@zillapi)

## License

MIT. See [LICENSE](LICENSE).

ZillAPI is an independent service and is not affiliated with or endorsed by Zillow Group.
