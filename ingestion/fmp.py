"""Financial Modeling Prep client."""

from __future__ import annotations

from typing import Any

from .base import APIClientError, BaseAPIClient, RateLimitPolicy


class FMPClient(BaseAPIClient):
    """Fetches stock and commodity data from Financial Modeling Prep."""

    provider_name = "fmp"
    base_url = "https://financialmodelingprep.com/stable"
    rate_limit_policy = RateLimitPolicy(max_calls_per_day=250)

    def validate_payload(self, payload: Any) -> None:
        if isinstance(payload, dict) and payload.get("Error Message"):
            raise APIClientError(str(payload["Error Message"]))
        if isinstance(payload, dict) and payload.get("error"):
            raise APIClientError(str(payload["error"]))

    def fetch_stock_daily(
        self,
        symbol: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Any:
        params = {"symbol": symbol, "apikey": self.settings.fmp_api_key}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self.request(path="historical-price-eod/full", params=params)

    def search_symbol(self, query: str, limit: int = 10) -> Any:
        params = {"query": query, "limit": limit, "apikey": self.settings.fmp_api_key}
        return self.request(path="search-symbol", params=params)

    def search_name(self, query: str, limit: int = 10) -> Any:
        params = {"query": query, "limit": limit, "apikey": self.settings.fmp_api_key}
        return self.request(path="search-name", params=params)

    def fetch_stock_intraday(
        self,
        symbol: str,
        interval: str = "1min",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Any:
        params = {"symbol": symbol, "apikey": self.settings.fmp_api_key}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self.request(path=f"historical-chart/{interval}", params=params)

    def fetch_commodity_daily(
        self,
        symbol: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Any:
        return self.fetch_stock_daily(symbol=symbol, from_date=from_date, to_date=to_date)
