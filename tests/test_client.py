import httpx
import pytest

from zillapi_agents.client import USER_AGENT, ZillapiClient, ZillapiError
from zillapi_agents.fixtures import body, fixture_transport


async def _nosleep(_):
    return None


def make(calls=None, overrides=None, **kw):
    http = httpx.AsyncClient(transport=fixture_transport(calls, overrides))
    return ZillapiClient("zk_test", http=http, sleep=_nosleep, **kw)


def test_requires_key():
    with pytest.raises(ValueError, match="ZILLAPI_API_KEY"):
        ZillapiClient()


async def test_search_sends_auth_and_body():
    calls = []
    bbox = {"west": -1, "south": 1, "east": 2, "north": 3}
    rows = await make(calls).search({"bbox": bbox, "beds": {"min": 3}}, 3)
    assert len(rows) == 3
    req = calls[0]
    assert req.method == "POST"
    assert str(req.url) == "https://api.zillapi.com/v1/search"
    assert req.headers["authorization"] == "Bearer zk_test"
    assert req.headers["user-agent"] == USER_AGENT
    assert body(req) == {"filters": {"bbox": bbox, "beds": {"min": 3}}, "maxItems": 3}


async def test_property_endpoints():
    calls = []
    c = make(calls)
    await c.get_property("123", "zpid,price")
    await c.get_property_by_url("https://www.zillow.com/homedetails/123_zpid/")
    await c.get_property_by_address("1 Main St, Austin, TX 78701")
    await c.get_zestimate("123")
    await c.get_comparables("123")
    assert [f"{r.method} {r.url.path}" for r in calls] == [
        "GET /v1/properties/123",
        "GET /v1/properties/by-url",
        "GET /v1/properties/by-address",
        "GET /v1/properties/123/zestimate",
        "GET /v1/properties/123/nearby",
    ]
    assert calls[0].url.params["fields"] == "zpid,price"
    assert "fields" not in calls[1].url.params  # None params are dropped
    assert calls[2].url.params["address"] == "1 Main St, Austin, TX 78701"
    assert calls[2].url.params["status"] == "FOR_SALE"


async def test_error_envelope():
    def bad(_):
        return httpx.Response(400, json={"error": {"code": "invalid_filters", "message": "bbox required", "request_id": "req_1"}})

    with pytest.raises(ZillapiError) as ei:
        await make(overrides={"POST /v1/search": bad}).search({})
    assert (ei.value.status, ei.value.code, ei.value.request_id) == (400, "invalid_filters", "req_1")


async def test_retries_on_429_then_succeeds():
    n = {"i": 0}

    def flaky(_):
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, json={"error": {"code": "rate_limited", "message": "slow down"}})
        return httpx.Response(200, json={"data": {"zestimate": 1}})

    z = await make(overrides={"GET /v1/properties/1/zestimate": flaky}).get_zestimate("1")
    assert z == {"zestimate": 1} and n["i"] == 2


async def test_gives_up_after_max_retries():
    n = {"i": 0}

    def limited(_):
        n["i"] += 1
        return httpx.Response(429, json={"error": {"code": "rate_limited", "message": "slow down"}})

    with pytest.raises(ZillapiError, match="slow down"):
        await make(overrides={"GET /v1/properties/1/zestimate": limited}, max_retries=1).get_zestimate("1")
    assert n["i"] == 2
