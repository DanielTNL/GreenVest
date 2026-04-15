"""End-to-end ETL pipeline for market, macro, and prediction data."""

from __future__ import annotations

from typing import Any

from config import Settings, get_settings
from db import MarketRepository

from .alpha_vantage import AlphaVantageClient
from .base import APIClientError, RawDataStore, utc_now
from .eodhd import EODHDClient
from .fmp import FMPClient
from .fred import FREDClient
from .normalizers import (
    normalize_alpha_vantage_daily,
    normalize_alpha_vantage_intraday,
    normalize_eodhd_history,
    normalize_fmp_history,
    normalize_fred_series,
    normalize_polymarket_events,
)
from .polymarket import PolymarketGammaClient


class DataIngestionPipeline:
    """Coordinates provider fetches, raw archival, and normalized writes."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.repository = MarketRepository(self.settings)
        self.raw_store = RawDataStore(self.settings)
        self.alpha_vantage = AlphaVantageClient(self.settings)
        self.fmp = FMPClient(self.settings)
        self.fred = FREDClient(self.settings)
        self.eodhd = EODHDClient(self.settings)
        self.polymarket = PolymarketGammaClient(self.settings)

    def ingest_alpha_vantage_stock(self, symbol: str, *, include_intraday: bool = False, interval: str = "5min") -> None:
        if not self.settings.alpha_vantage_api_key:
            self.repository.log_audit("ingestion", "warning", "ALPHAVANTAGE_API_KEY missing; skipping Alpha Vantage ingestion.")
            return
        daily_payload = self.alpha_vantage.fetch_daily(symbol)
        raw_path, checksum = self.raw_store.persist("alpha_vantage", "daily", daily_payload, entity_key=symbol)
        stocks, prices = normalize_alpha_vantage_daily(symbol, daily_payload, str(raw_path))
        self.repository.upsert_stocks(stocks)
        self.repository.upsert_stock_prices(prices)
        self.repository.log_raw_ingestion(
            {
                "provider": "alpha_vantage",
                "endpoint": "daily",
                "entity_key": symbol,
                "requested_at_utc": utc_now(),
                "raw_path": str(raw_path),
                "status": "success",
                "http_status": 200,
                "checksum": checksum,
            }
        )
        if include_intraday:
            intraday_payload = self.alpha_vantage.fetch_intraday(symbol, interval=interval)
            raw_path, checksum = self.raw_store.persist(
                "alpha_vantage",
                f"intraday_{interval}",
                intraday_payload,
                entity_key=symbol,
            )
            intraday_rows = normalize_alpha_vantage_intraday(symbol, intraday_payload, interval, str(raw_path))
            if intraday_rows:
                self.repository.upsert_stock_prices(intraday_rows)
            self.repository.log_raw_ingestion(
                {
                    "provider": "alpha_vantage",
                    "endpoint": f"intraday_{interval}",
                    "entity_key": symbol,
                    "requested_at_utc": utc_now(),
                    "raw_path": str(raw_path),
                    "status": "success",
                    "http_status": 200,
                    "checksum": checksum,
                }
            )

    def ingest_fmp_stock(self, symbol: str, *, include_intraday: bool = False, interval: str = "1min") -> None:
        if not self.settings.fmp_api_key:
            self.repository.log_audit("ingestion", "warning", "FMP_API_KEY missing; skipping FMP stock ingestion.")
            return
        daily_payload = self.fmp.fetch_stock_daily(symbol)
        raw_path, checksum = self.raw_store.persist("fmp", "stock_daily", daily_payload, entity_key=symbol)
        stocks, prices = normalize_fmp_history(symbol, daily_payload, str(raw_path), interval="1day")
        self.repository.upsert_stocks(stocks)
        self.repository.upsert_stock_prices(prices)
        self.repository.log_raw_ingestion(
            {
                "provider": "fmp",
                "endpoint": "stock_daily",
                "entity_key": symbol,
                "requested_at_utc": utc_now(),
                "raw_path": str(raw_path),
                "status": "success",
                "http_status": 200,
                "checksum": checksum,
            }
        )
        if include_intraday:
            intraday_payload = self.fmp.fetch_stock_intraday(symbol, interval=interval)
            raw_path, checksum = self.raw_store.persist("fmp", f"stock_intraday_{interval}", intraday_payload, entity_key=symbol)
            _, rows = normalize_fmp_history(symbol, intraday_payload, str(raw_path), interval=interval)
            if rows:
                self.repository.upsert_stock_prices(rows)
            self.repository.log_raw_ingestion(
                {
                    "provider": "fmp",
                    "endpoint": f"stock_intraday_{interval}",
                    "entity_key": symbol,
                    "requested_at_utc": utc_now(),
                    "raw_path": str(raw_path),
                    "status": "success",
                    "http_status": 200,
                    "checksum": checksum,
                }
            )

    def ingest_macro_series(self, series_name: str, series_id: str) -> None:
        if not self.settings.fred_api_key:
            self.repository.log_audit("ingestion", "warning", "FRED_API_KEY missing; skipping macro ingestion.")
            return
        metadata_payload = self.fred.fetch_series_metadata(series_id)
        observations_payload = self.fred.fetch_series_observations(series_id)
        raw_payload = {"metadata": metadata_payload, "observations": observations_payload}
        raw_path, checksum = self.raw_store.persist("fred", "series_observations", raw_payload, entity_key=series_id)
        indicator, observations = normalize_fred_series(
            series_name,
            series_id,
            metadata_payload,
            observations_payload,
            str(raw_path),
        )
        macro_id = self.repository.upsert_macro_indicator(indicator)
        for observation in observations:
            observation["macro_id"] = macro_id
        self.repository.upsert_macro_observations(observations)
        self.repository.log_raw_ingestion(
            {
                "provider": "fred",
                "endpoint": "series_observations",
                "entity_key": series_id,
                "requested_at_utc": utc_now(),
                "raw_path": str(raw_path),
                "status": "success",
                "http_status": 200,
                "checksum": checksum,
            }
        )

    def ingest_commodity_from_fmp(self, symbol: str) -> None:
        if not self.settings.fmp_api_key:
            self.repository.log_audit("ingestion", "warning", "FMP_API_KEY missing; skipping FMP commodity ingestion.")
            return
        payload = self.fmp.fetch_commodity_daily(symbol)
        raw_path, checksum = self.raw_store.persist("fmp", "commodity_daily", payload, entity_key=symbol)
        commodities, prices = normalize_fmp_history(
            symbol,
            payload,
            str(raw_path),
            interval="1day",
            source="fmp",
            asset_type="commodity",
        )
        self.repository.upsert_commodities(commodities)
        self.repository.upsert_commodity_prices(prices)
        self.repository.log_raw_ingestion(
            {
                "provider": "fmp",
                "endpoint": "commodity_daily",
                "entity_key": symbol,
                "requested_at_utc": utc_now(),
                "raw_path": str(raw_path),
                "status": "success",
                "http_status": 200,
                "checksum": checksum,
            }
        )

    def ingest_commodity_from_eodhd(self, symbol: str) -> None:
        if not self.settings.eodhd_api_key:
            self.repository.log_audit("ingestion", "warning", "EODHD_API_KEY missing; skipping EODHD commodity ingestion.")
            return
        payload = self.eodhd.fetch_end_of_day(symbol)
        raw_path, checksum = self.raw_store.persist("eodhd", "commodity_daily", payload, entity_key=symbol)
        commodities, prices = normalize_eodhd_history(symbol, payload, str(raw_path))
        self.repository.upsert_commodities(commodities)
        self.repository.upsert_commodity_prices(prices)
        self.repository.log_raw_ingestion(
            {
                "provider": "eodhd",
                "endpoint": "commodity_daily",
                "entity_key": symbol,
                "requested_at_utc": utc_now(),
                "raw_path": str(raw_path),
                "status": "success",
                "http_status": 200,
                "checksum": checksum,
            }
        )

    def ingest_polymarket(self, *, limit: int | None = None) -> None:
        all_events: list[dict[str, Any]] = []
        max_records = limit or self.settings.default_polymarket_limit
        offset = 0
        while len(all_events) < max_records:
            remaining = max_records - len(all_events)
            page_limit = min(self.settings.default_polymarket_limit, remaining)
            payload = self.polymarket.fetch_events(limit=page_limit, offset=offset, active=True, closed=False)
            if not payload:
                break
            all_events.extend(payload)
            if len(payload) < page_limit:
                break
            offset += page_limit
        raw_path, checksum = self.raw_store.persist("polymarket", "events", all_events, entity_key="active_events")
        markets, odds = normalize_polymarket_events(all_events, str(raw_path))
        self.repository.upsert_prediction_markets(markets)
        self.repository.upsert_prediction_market_odds(odds)
        self.repository.log_raw_ingestion(
            {
                "provider": "polymarket",
                "endpoint": "events",
                "entity_key": "active_events",
                "requested_at_utc": utc_now(),
                "raw_path": str(raw_path),
                "status": "success",
                "http_status": 200,
                "checksum": checksum,
            }
        )

    def run_full_etl(
        self,
        *,
        stock_symbols: list[str] | None = None,
        include_intraday: bool = False,
        macro_series: dict[str, str] | None = None,
        commodity_symbols: list[str] | None = None,
        eodhd_symbols: list[str] | None = None,
        include_geopolitical: bool = True,
        include_polymarket: bool = True,
    ) -> None:
        for symbol in stock_symbols or list(self.settings.default_stock_symbols):
            self._safe_ingest(
                lambda current_symbol=symbol: self.ingest_alpha_vantage_stock(
                    current_symbol,
                    include_intraday=include_intraday,
                ),
                component=f"alpha_vantage:{symbol}",
            )
            self._safe_ingest(
                lambda current_symbol=symbol: self.ingest_fmp_stock(
                    current_symbol,
                    include_intraday=include_intraday,
                ),
                component=f"fmp_stock:{symbol}",
            )
        configured_macro_series = macro_series or self.settings.configured_macro_series(
            include_geopolitical=include_geopolitical
        )
        for series_name, series_id in configured_macro_series.items():
            self._safe_ingest(
                lambda current_name=series_name, current_id=series_id: self.ingest_macro_series(current_name, current_id),
                component=f"fred:{series_id}",
            )
        for symbol in commodity_symbols or list(self.settings.default_commodity_symbols):
            self._safe_ingest(
                lambda current_symbol=symbol: self.ingest_commodity_from_fmp(current_symbol),
                component=f"fmp_commodity:{symbol}",
            )
        for symbol in eodhd_symbols or []:
            self._safe_ingest(
                lambda current_symbol=symbol: self.ingest_commodity_from_eodhd(current_symbol),
                component=f"eodhd:{symbol}",
            )
        if include_polymarket:
            self._safe_ingest(self.ingest_polymarket, component="polymarket")

    def _safe_ingest(self, action, *, component: str) -> None:
        try:
            action()
        except APIClientError as exc:
            self.repository.log_audit("ingestion", "warning", f"{component} failed: {exc}")
        except Exception as exc:  # pragma: no cover - defensive fallback
            self.repository.log_audit("ingestion", "error", f"{component} raised unexpected error: {exc}")
