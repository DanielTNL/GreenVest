"""FRED macroeconomic series client."""

from __future__ import annotations

from typing import Any

from .base import APIClientError, BaseAPIClient


class FREDClient(BaseAPIClient):
    """Fetches macroeconomic observations from the FRED API."""

    provider_name = "fred"
    base_url = "https://api.stlouisfed.org/fred"

    def validate_payload(self, payload: Any) -> None:
        if isinstance(payload, dict) and payload.get("error_message"):
            raise APIClientError(str(payload["error_message"]))

    def fetch_series_metadata(self, series_id: str) -> Any:
        return self.request(
            path="series",
            params={
                "series_id": series_id,
                "api_key": self.settings.fred_api_key,
                "file_type": "json",
            },
        )

    def fetch_series_observations(
        self,
        series_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        params = {
            "series_id": series_id,
            "api_key": self.settings.fred_api_key,
            "file_type": "json",
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date
        return self.request(path="series/observations", params=params)
