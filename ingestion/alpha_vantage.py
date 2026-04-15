"""Alpha Vantage data client."""

from __future__ import annotations

from typing import Any

from .base import APIClientError, BaseAPIClient, RateLimitPolicy


class AlphaVantageClient(BaseAPIClient):
    """Fetches equity daily and intraday price data from Alpha Vantage."""

    provider_name = "alpha_vantage"
    base_url = "https://www.alphavantage.co/query"
    rate_limit_policy = RateLimitPolicy(min_interval_seconds=12.5)

    def validate_payload(self, payload: Any) -> None:
        if isinstance(payload, dict):
            if "Error Message" in payload:
                raise APIClientError(payload["Error Message"])
            if "Note" in payload:
                raise APIClientError(payload["Note"])
            if "Information" in payload and len(payload) <= 2:
                raise APIClientError(str(payload["Information"]))

    def fetch_daily(self, symbol: str, outputsize: str = "compact") -> dict[str, Any]:
        return self.request(
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": outputsize,
                "apikey": self.settings.alpha_vantage_api_key,
            }
        )

    def fetch_intraday(
        self,
        symbol: str,
        interval: str = "5min",
        outputsize: str = "compact",
    ) -> dict[str, Any]:
        return self.request(
            params={
                "function": "TIME_SERIES_INTRADAY",
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "apikey": self.settings.alpha_vantage_api_key,
            }
        )
