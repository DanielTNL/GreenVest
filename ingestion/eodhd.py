"""EOD Historical Data client."""

from __future__ import annotations

from typing import Any

from .base import APIClientError, BaseAPIClient, RateLimitPolicy


class EODHDClient(BaseAPIClient):
    """Fetches commodity and market history from EOD Historical Data."""

    provider_name = "eodhd"
    base_url = "https://eodhd.com/api"
    rate_limit_policy = RateLimitPolicy(max_calls_per_day=1000)

    def validate_payload(self, payload: Any) -> None:
        if isinstance(payload, dict) and payload.get("error"):
            raise APIClientError(str(payload["error"]))

    def fetch_end_of_day(
        self,
        symbol: str,
        from_date: str | None = None,
        to_date: str | None = None,
        period: str = "d",
    ) -> Any:
        params = {
            "api_token": self.settings.eodhd_api_key,
            "fmt": "json",
            "period": period,
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self.request(path=f"eod/{symbol}", params=params)
