"""Minimal async ZillAPI REST client.

Docs: https://zillapi.com/docs  |  OpenAPI: https://zillapi.com/openapi.json
Auth: ``Authorization: Bearer zk_...``  |  Base URL: https://api.zillapi.com
"""

from __future__ import annotations

import asyncio
import os
import random
from typing import Any, Awaitable, Callable, Literal

import httpx

DEFAULT_BASE_URL = "https://api.zillapi.com"
USER_AGENT = "zillapi-openai-agents-example/1.0 (+https://zillapi.com)"

ListingStatus = Literal["FOR_SALE", "RECENTLY_SOLD", "FOR_RENT"]


class ZillapiError(Exception):
    """Raised for non-2xx responses. ``code`` is the stable ZillAPI error code."""

    def __init__(self, message: str, status: int, code: str, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id


class ZillapiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        http: httpx.AsyncClient | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        api_key = api_key or os.environ.get("ZILLAPI_API_KEY")
        if not api_key:
            raise ValueError(
                "Missing ZillAPI key. Set ZILLAPI_API_KEY "
                "(free key with 100 credits: https://zillapi.com/signup)."
            )
        self._api_key = api_key
        self._base_url = (base_url or os.environ.get("ZILLAPI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=60)
        self._max_retries = max_retries
        self._sleep = sleep

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "ZillapiClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> dict[str, Any]:
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        attempt = 0
        while True:
            res = await self._http.request(method, self._base_url + path, params=params, json=json, headers=headers)
            if res.is_success:
                return res.json()

            if res.status_code in (429, 502, 504) and attempt < self._max_retries:
                retry_after = res.headers.get("retry-after", "")
                delay = float(retry_after) if retry_after.isdigit() else 2.0 * 2**attempt
                await self._sleep(delay + random.random() / 4)
                attempt += 1
                continue

            try:
                err = res.json().get("error", {})
            except ValueError:
                err = {}
            raise ZillapiError(
                err.get("message") or f"ZillAPI request failed with HTTP {res.status_code}",
                res.status_code,
                err.get("code") or "http_error",
                err.get("request_id"),
            )

    async def search(self, filters: dict[str, Any], max_items: int = 5) -> list[dict[str, Any]]:
        """POST /v1/search. ``filters.bbox`` is required. 1 credit per row returned."""
        return (await self._request("POST", "/v1/search", json={"filters": filters, "maxItems": max_items}))["data"]

    async def get_property(self, zpid: str, fields: str | None = None) -> dict[str, Any]:
        """GET /v1/properties/{zpid}. 1 credit."""
        return (await self._request("GET", f"/v1/properties/{zpid}", params={"fields": fields}))["data"]

    async def get_property_by_url(self, url: str, fields: str | None = None) -> dict[str, Any]:
        """GET /v1/properties/by-url. 1 credit per record."""
        return (await self._request("GET", "/v1/properties/by-url", params={"url": url, "fields": fields}))["data"]

    async def get_property_by_address(
        self, address: str, status: ListingStatus = "FOR_SALE", fields: str | None = None
    ) -> dict[str, Any]:
        """GET /v1/properties/by-address. Full street address with city, state, ZIP. 3 credits."""
        params = {"address": address, "status": status, "fields": fields}
        return (await self._request("GET", "/v1/properties/by-address", params=params))["data"]

    async def get_zestimate(self, zpid: str) -> dict[str, Any]:
        """GET /v1/properties/{zpid}/zestimate. 1 credit."""
        return (await self._request("GET", f"/v1/properties/{zpid}/zestimate"))["data"]

    async def get_comparables(self, zpid: str) -> list[dict[str, Any]]:
        """GET /v1/properties/{zpid}/nearby. About 12 comparable homes. 1 credit."""
        return (await self._request("GET", f"/v1/properties/{zpid}/nearby"))["data"]
