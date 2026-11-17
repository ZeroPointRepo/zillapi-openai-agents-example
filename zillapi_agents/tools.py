"""ZillAPI tools for the OpenAI Agents SDK.

    from agents import Agent
    from zillapi_agents import ZillapiTools

    agent = Agent(name="Realtor", tools=ZillapiTools().as_function_tools())
"""

from __future__ import annotations

import functools
import json
from typing import Annotated, Any, Awaitable, Callable, Literal
from urllib.parse import urljoin

from agents import FunctionTool, function_tool
from pydantic import BaseModel, Field

from .client import ListingStatus, ZillapiClient, ZillapiError

PROPERTY_FIELDS = ",".join(
    [
        "zpid",
        "address",
        "price",
        "zestimate",
        "rentZestimate",
        "bedrooms",
        "bathrooms",
        "livingArea",
        "lotSize",
        "yearBuilt",
        "homeType",
        "homeStatus",
        "latitude",
        "longitude",
    ]
)

HomeType = Literal["house", "condo", "townhouse", "multi_family", "manufactured", "lot", "apartment"]


class BoundingBox(BaseModel):
    """Bounding box in decimal degrees."""

    west: float
    south: float
    east: float
    north: float


def _num(v: Any) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _first(*values: Any) -> Any:
    return next((v for v in values if v not in (None, "")), None)


def _one_line_address(addr: Any) -> str | None:
    if isinstance(addr, dict):  # detail-style address object
        street, city, state, zipcode = (addr.get(k) for k in ("streetAddress", "city", "state", "zipcode"))
        tail = " ".join(p for p in (state, zipcode) if p)
        return ", ".join(p for p in (street, city, tail) if p) or None
    return addr


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    """Reduce a listing row to the fields an LLM actually needs.

    Handles both the documented search-row shape (addressStreet, unformattedPrice, beds, hdpData.homeInfo)
    and the detail-style shape (address object, bedrooms, livingArea) that some endpoints return.
    """
    info = (row.get("hdpData") or {}).get("homeInfo") or {}
    detail = _first(row.get("detailUrl"), row.get("hdpUrl"), row.get("url"))
    return {
        "zpid": str(row.get("zpid")),
        "address": _one_line_address(row.get("address")),
        "price": _first(_num(row.get("unformattedPrice")), _num(row.get("price")), _num(info.get("price"))),
        "beds": _first(row.get("beds"), row.get("bedrooms"), info.get("bedrooms")),
        "baths": _first(row.get("baths"), row.get("bathrooms"), info.get("bathrooms")),
        "sqft": _first(row.get("area"), row.get("livingArea"), info.get("livingArea")),
        "home_type": _first(row.get("homeType"), info.get("homeType")),
        "status": _first(row.get("statusType"), row.get("homeStatus"), info.get("homeStatus")),
        "zestimate": _first(_num(row.get("zestimate")), _num(info.get("zestimate"))),
        "rent_zestimate": _first(_num(row.get("rentZestimate")), _num(info.get("rentZestimate"))),
        "days_on_zillow": _num(info.get("daysOnZillow")),
        "url": urljoin("https://www.zillow.com", detail) if detail else None,
    }


def _err(e: ZillapiError) -> dict[str, Any]:
    # Returned to the model (not raised) so the agent can explain or recover.
    return {"error": {"code": e.code, "message": str(e)}}


def _range(lo: float | None, hi: float | None) -> dict[str, float] | None:
    if lo is None and hi is None:
        return None
    return {k: v for k, v in (("min", lo), ("max", hi)) if v is not None}


class ZillapiTools:
    """Plain async methods you can call directly, plus ``as_function_tools()`` for an Agent."""

    def __init__(self, client: ZillapiClient | None = None) -> None:
        self.client = client or ZillapiClient()

    async def search_listings(
        self,
        bbox: BoundingBox,
        status: Literal["for_sale", "for_rent", "sold"] = "for_sale",
        location: str | None = None,
        price_min: int | None = None,
        price_max: int | None = None,
        beds_min: int | None = None,
        beds_max: int | None = None,
        baths_min: float | None = None,
        home_types: list[HomeType] | None = None,
        max_items: Annotated[int, Field(ge=1, le=20)] = 5,
    ) -> dict[str, Any]:
        """Search Zillow listings (for sale, for rent or sold) inside a bounding box.

        A bounding box is REQUIRED; a city name alone is not accepted, so estimate the city's bbox
        from your own knowledge (Austin, TX is roughly west=-97.94, south=30.10, east=-97.56, north=30.52).
        Returns compact rows with zpid, address, price, beds, baths, sqft and Zestimate when available.
        Costs 1 credit per row returned.

        Args:
            bbox: Bounding box in decimal degrees.
            status: Listing status.
            location: Optional place label like "Austin, TX" (a hint only).
            price_min: Minimum price in dollars.
            price_max: Maximum price in dollars.
            beds_min: Minimum bedrooms.
            beds_max: Maximum bedrooms.
            baths_min: Minimum bathrooms.
            home_types: Home types to include.
            max_items: Max rows to return (1-20). This is also your credit cap.
        """
        max_items = max(1, min(int(max_items), 20))
        filters: dict[str, Any] = {
            "status": status,
            "bbox": BoundingBox.model_validate(bbox).model_dump(),
            "location": location,
            "price": _range(price_min, price_max),
            "beds": _range(beds_min, beds_max),
            "baths": _range(baths_min, None),
            "homeTypes": home_types,
        }
        filters = {k: v for k, v in filters.items() if v is not None}
        try:
            rows = await self.client.search(filters, max_items)
        except ZillapiError as e:
            return _err(e)
        return {"count": len(rows), "results": [compact_row(r) for r in rows]}

    async def get_property(self, zpid: str | None = None, url: str | None = None) -> dict[str, Any]:
        """Get a property's details (price, Zestimate, Rent Zestimate, beds, baths, sqft, year built, type, status).

        Provide exactly one of zpid or url. Costs 1 credit.

        Args:
            zpid: Zillow property id (numeric string).
            url: Full zillow.com homedetails URL.
        """
        try:
            if zpid:
                if not zpid.isdigit():
                    return {"error": {"code": "invalid_zpid", "message": "zpid must be numeric"}}
                return await self.client.get_property(zpid, PROPERTY_FIELDS)
            if url:
                return await self.client.get_property_by_url(url, PROPERTY_FIELDS)
        except ZillapiError as e:
            return _err(e)
        return {"error": {"code": "missing_input", "message": "Provide zpid or url."}}

    async def get_property_by_address(self, address: str, status: ListingStatus = "FOR_SALE") -> dict[str, Any]:
        """Look up a property by full street address including city, state and ZIP.

        Example: "123 Main St, Austin, TX 78701". Costs 3 credits, so prefer get_property when you have a zpid.

        Args:
            address: Full street address with city, state and ZIP.
            status: Listing status to resolve.
        """
        try:
            return await self.client.get_property_by_address(address, status, PROPERTY_FIELDS)
        except ZillapiError as e:
            return _err(e)

    async def get_zestimate(self, zpid: str) -> dict[str, Any]:
        """Get the Zestimate, Rent Zestimate, tax-assessed value and last sold price for a zpid. Costs 1 credit.

        Args:
            zpid: Zillow property id (numeric string).
        """
        if not zpid.isdigit():
            return {"error": {"code": "invalid_zpid", "message": "zpid must be numeric"}}
        try:
            return {"zpid": zpid, **(await self.client.get_zestimate(zpid))}
        except ZillapiError as e:
            return _err(e)

    async def get_comparables(self, zpid: str) -> dict[str, Any]:
        """Get comparable nearby homes (comps, about 12 rows) for a zpid. Costs 1 credit.

        Args:
            zpid: Zillow property id (numeric string).
        """
        if not zpid.isdigit():
            return {"error": {"code": "invalid_zpid", "message": "zpid must be numeric"}}
        try:
            rows = await self.client.get_comparables(zpid)
        except ZillapiError as e:
            return _err(e)
        return {"zpid": zpid, "count": len(rows), "comparables": [compact_row(r) for r in rows]}

    def as_function_tools(self) -> list[FunctionTool]:
        """The five methods above as Agents SDK function tools (schemas come from type hints + docstrings)."""
        return [
            _json_tool(m)
            for m in (
                self.search_listings,
                self.get_property,
                self.get_property_by_address,
                self.get_zestimate,
                self.get_comparables,
            )
        ]


def _json_tool(method: Callable[..., Awaitable[dict[str, Any]]]) -> FunctionTool:
    """Wrap a method so the model receives compact JSON (the SDK would otherwise str() a dict)."""

    @functools.wraps(method)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        return json.dumps(await method(*args, **kwargs), separators=(",", ":"), default=str)

    return function_tool(wrapper)
