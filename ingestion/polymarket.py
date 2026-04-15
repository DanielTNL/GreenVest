"""Polymarket Gamma API client."""

from __future__ import annotations

from typing import Any

from .base import APIClientError, BaseAPIClient


class PolymarketGammaClient(BaseAPIClient):
    """Fetches public event and market data from the Polymarket Gamma API."""

    provider_name = "polymarket"
    base_url = "https://gamma-api.polymarket.com"

    def validate_payload(self, payload: Any) -> None:
        if isinstance(payload, dict) and payload.get("error"):
            raise APIClientError(str(payload["error"]))

    def fetch_events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
        tag_id: int | None = None,
        slug: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
        }
        if tag_id is not None:
            params["tag_id"] = tag_id
        if slug is not None:
            params["slug"] = slug
        return self.request(path="events", params=params)

    def fetch_markets(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
        slug: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
        }
        if slug is not None:
            params["slug"] = slug
        return self.request(path="markets", params=params)
