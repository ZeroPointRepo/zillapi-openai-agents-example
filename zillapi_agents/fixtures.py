"""Synthetic ZillAPI responses (shapes follow https://zillapi.com/openapi.json) and an offline HTTP transport.

Used by the tests and by ``scripts/mock_agent.py``. No network access.
"""

from __future__ import annotations

import json
import re

import httpx

SEARCH_ROWS = [
    {
        "zpid": "1000001",
        "address": "101 Example Ln, Austin, TX 78745",
        "unformattedPrice": 449000,
        "price": "$449,000",
        "beds": 3,
        "baths": 2,
        "area": 1520,
        "statusType": "FOR_SALE",
        "detailUrl": "/homedetails/1000001_zpid/",
        "hdpData": {"homeInfo": {"homeType": "SINGLE_FAMILY", "zestimate": 452300, "daysOnZillow": 12}},
    },
    {
        "zpid": "1000002",
        "address": "202 Sample Dr, Austin, TX 78744",
        "unformattedPrice": 389900,
        "beds": 3,
        "baths": 2,
        "area": 1340,
        "statusType": "FOR_SALE",
        "detailUrl": "https://www.zillow.com/homedetails/1000002_zpid/",
        "hdpData": {"homeInfo": {"homeType": "SINGLE_FAMILY", "daysOnZillow": 30}},
    },
    {
        "zpid": "1000003",
        "address": "303 Placeholder Ct, Austin, TX 78748",
        "unformattedPrice": 495000,
        "beds": 3,
        "baths": 2.5,
        "area": 1810,
        "statusType": "FOR_SALE",
        "detailUrl": "/homedetails/1000003_zpid/",
        "hdpData": {"homeInfo": {"homeType": "TOWNHOUSE", "zestimate": 488100, "rentZestimate": 2450}},
    },
]

ZESTIMATE = {
    "zestimate": 395000,
    "rent_zestimate": 2200,
    "tax_assessed_value": 351000,
    "last_sold_price": 310000,
    "currency": "USD",
}

# Live /nearby rows (Nov 2026) came back with an address OBJECT rather than the documented search-row shape.
NEARBY_ROWS = [
    {
        "zpid": "1000004",
        "address": {"streetAddress": "404 Demo Ave", "city": "Austin", "state": "TX", "zipcode": "78745"},
        "livingArea": 1350,
        "homeType": "SINGLE_FAMILY",
    },
    {
        "zpid": "1000005",
        "address": {"streetAddress": "505 Mock Blvd", "city": "Austin", "state": "TX", "zipcode": "78745"},
        "price": 410000,
        "bedrooms": 3,
        "bathrooms": 2,
        "livingArea": 1144,
        "homeType": "SINGLE_FAMILY",
        "homeStatus": "RECENTLY_SOLD",
        "hdpUrl": "/homedetails/1000005_zpid/",
    },
]

PROPERTY = {
    "zpid": "1000001",
    "address": {"streetAddress": "101 Example Ln", "city": "Austin", "state": "TX", "zipcode": "78745"},
    "price": 449000,
    "zestimate": 452300,
    "rentZestimate": 2390,
    "bedrooms": 3,
    "bathrooms": 2,
    "livingArea": 1520,
    "yearBuilt": 1998,
    "homeType": "SINGLE_FAMILY",
    "homeStatus": "FOR_SALE",
}


def fixture_transport(calls: list[httpx.Request] | None = None, overrides: dict | None = None) -> httpx.MockTransport:
    """An httpx transport that answers like ZillAPI from the fixtures above and records every request."""
    overrides = overrides or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        key = f"{request.method} {request.url.path}"
        if key in overrides:
            return overrides[key](request)
        if key == "POST /v1/search":
            return httpx.Response(200, json={"data": SEARCH_ROWS, "meta": {"count": 3}, "request_id": "req_test"})
        if re.fullmatch(r"GET /v1/properties/\d+/zestimate", key):
            return httpx.Response(200, json={"data": ZESTIMATE, "request_id": "req_test"})
        if re.fullmatch(r"GET /v1/properties/\d+/nearby", key):
            return httpx.Response(200, json={"data": NEARBY_ROWS, "request_id": "req_test"})
        if key in ("GET /v1/properties/by-address", "GET /v1/properties/by-url") or re.fullmatch(
            r"GET /v1/properties/\d+", key
        ):
            return httpx.Response(200, json={"data": PROPERTY, "request_id": "req_test"})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": f"No fixture for {key}"}})

    return httpx.MockTransport(handler)


def body(request: httpx.Request) -> dict:
    return json.loads(request.content or b"{}")
