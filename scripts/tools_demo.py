"""Call the ZillAPI tools directly, with no LLM, to check your key and see the data shapes.

    export ZILLAPI_API_KEY=zk_...
    python scripts/tools_demo.py --zpid 29401977                 # get_property + get_comparables: 2 credits
    python scripts/tools_demo.py --address "1 Main St, Austin, TX 78701"   # get_property_by_address: 3 credits
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zillapi_agents import ZillapiTools  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zpid")
    ap.add_argument("--address")
    args = ap.parse_args()
    if not (args.zpid or args.address):
        ap.error("pass --zpid and/or --address")

    tools = ZillapiTools()
    try:
        if args.zpid:
            print("get_property ->", json.dumps(await tools.get_property(zpid=args.zpid), indent=2))
            comps = await tools.get_comparables(args.zpid)
            if "comparables" in comps:
                comps["comparables"] = comps["comparables"][:3]  # keep the printout short
            print("get_comparables (first 3) ->", json.dumps(comps, indent=2))
        if args.address:
            print("get_property_by_address ->", json.dumps(await tools.get_property_by_address(args.address), indent=2))
    finally:
        await tools.client.aclose()


asyncio.run(main())
