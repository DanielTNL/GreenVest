"""Provider response normalizers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .base import (
    coerce_float,
    coerce_int,
    ensure_utc_timestamp,
    safe_json_loads,
    trading_date_from_timestamp,
)


def normalize_alpha_vantage_daily(
    symbol: str,
    payload: dict[str, Any],
    raw_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prices: list[dict[str, Any]] = []
    stocks = [{"symbol": symbol, "name": symbol, "asset_type": "equity", "source": "alpha_vantage"}]
    series = payload.get("Time Series (Daily)", {})
    for date_key, values in series.items():
        timestamp_utc = ensure_utc_timestamp(date_key, source_timezone="US/Eastern")
        prices.append(
            {
                "symbol": symbol,
                "source": "alpha_vantage",
                "interval": "1day",
                "timestamp_utc": timestamp_utc,
                "trading_date": trading_date_from_timestamp(timestamp_utc),
                "price": coerce_float(values.get("4. close")),
                "open": coerce_float(values.get("1. open")),
                "high": coerce_float(values.get("2. high")),
                "low": coerce_float(values.get("3. low")),
                "close": coerce_float(values.get("4. close")),
                "volume": coerce_int(values.get("5. volume")),
                "raw_path": raw_path,
            }
        )
    return stocks, prices


def normalize_alpha_vantage_intraday(
    symbol: str,
    payload: dict[str, Any],
    interval: str,
    raw_path: str,
) -> list[dict[str, Any]]:
    series_key = next((key for key in payload if key.startswith("Time Series")), None)
    if not series_key:
        return []
    rows: list[dict[str, Any]] = []
    for timestamp, values in payload.get(series_key, {}).items():
        timestamp_utc = ensure_utc_timestamp(timestamp, source_timezone="US/Eastern")
        rows.append(
            {
                "symbol": symbol,
                "source": "alpha_vantage",
                "interval": interval,
                "timestamp_utc": timestamp_utc,
                "trading_date": trading_date_from_timestamp(timestamp_utc),
                "price": coerce_float(values.get("4. close")),
                "open": coerce_float(values.get("1. open")),
                "high": coerce_float(values.get("2. high")),
                "low": coerce_float(values.get("3. low")),
                "close": coerce_float(values.get("4. close")),
                "volume": coerce_int(values.get("5. volume")),
                "raw_path": raw_path,
            }
        )
    return rows


def normalize_fmp_history(
    symbol: str,
    payload: Any,
    raw_path: str,
    *,
    interval: str,
    source: str = "fmp",
    asset_type: str = "equity",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = payload.get("historical", payload) if isinstance(payload, dict) else payload
    rows: list[dict[str, Any]] = []
    stocks_or_commodities = [{"symbol": symbol, "name": symbol, "asset_type": asset_type, "source": source}]
    for item in records or []:
        timestamp_value = item.get("date") or item.get("datetime")
        if not timestamp_value:
            continue
        timestamp_utc = ensure_utc_timestamp(timestamp_value, source_timezone="America/New_York")
        rows.append(
            {
                "symbol": symbol,
                "source": source,
                "interval": interval,
                "timestamp_utc": timestamp_utc,
                "trading_date": trading_date_from_timestamp(timestamp_utc),
                "price": coerce_float(item.get("close") or item.get("price")),
                "open": coerce_float(item.get("open")),
                "high": coerce_float(item.get("high")),
                "low": coerce_float(item.get("low")),
                "close": coerce_float(item.get("close") or item.get("price")),
                "volume": coerce_int(item.get("volume")),
                "raw_path": raw_path,
            }
        )
    return stocks_or_commodities, rows


def normalize_fred_series(
    series_name: str,
    series_id: str,
    metadata_payload: dict[str, Any],
    observations_payload: dict[str, Any],
    raw_path: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = (metadata_payload.get("seriess") or [{}])[0]
    indicator = {
        "name": series_name,
        "fred_series_id": series_id,
        "frequency": metadata.get("frequency_short") or metadata.get("frequency"),
        "units": metadata.get("units_short") or metadata.get("units"),
    }
    observations: list[dict[str, Any]] = []
    for item in observations_payload.get("observations", []):
        if item.get("value") in (None, "."):
            continue
        timestamp_utc = ensure_utc_timestamp(item["date"], source_timezone="UTC")
        observations.append(
            {
                "observation_date": item["date"],
                "timestamp_utc": timestamp_utc,
                "value": coerce_float(item["value"]),
                "realtime_start": item.get("realtime_start"),
                "realtime_end": item.get("realtime_end"),
                "source": "fred",
                "raw_path": raw_path,
            }
        )
    return indicator, observations


def normalize_eodhd_history(
    symbol: str,
    payload: Iterable[dict[str, Any]],
    raw_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    commodities = [{"symbol": symbol, "name": symbol, "source": "eodhd"}]
    prices: list[dict[str, Any]] = []
    for item in payload:
        timestamp_utc = ensure_utc_timestamp(item["date"], source_timezone="UTC")
        prices.append(
            {
                "symbol": symbol,
                "source": "eodhd",
                "interval": "1day",
                "timestamp_utc": timestamp_utc,
                "trading_date": trading_date_from_timestamp(timestamp_utc),
                "price": coerce_float(item.get("close")),
                "open": coerce_float(item.get("open")),
                "high": coerce_float(item.get("high")),
                "low": coerce_float(item.get("low")),
                "close": coerce_float(item.get("close")),
                "volume": coerce_int(item.get("volume")),
                "raw_path": raw_path,
            }
        )
    return commodities, prices


def normalize_polymarket_events(payload: list[dict[str, Any]], raw_path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    markets: list[dict[str, Any]] = []
    odds: list[dict[str, Any]] = []
    for event in payload:
        event_id = str(event.get("id"))
        for market in event.get("markets", []):
            outcome_prices = safe_json_loads(market.get("outcomePrices")) or []
            yes_prob = coerce_float(outcome_prices[0]) if len(outcome_prices) >= 1 else None
            no_prob = coerce_float(outcome_prices[1]) if len(outcome_prices) >= 2 else None
            updated_at = market.get("updatedAt") or event.get("updatedAt") or event.get("createdAt")
            timestamp_utc = ensure_utc_timestamp(updated_at, source_timezone="UTC")
            markets.append(
                {
                    "market_id": str(market["id"]),
                    "event_id": event_id,
                    "slug": market.get("slug"),
                    "question": market.get("question") or event.get("title") or market.get("slug"),
                    "description": market.get("description") or event.get("description"),
                    "active": bool(market.get("active")),
                    "closed": bool(market.get("closed")),
                    "end_date_utc": ensure_utc_timestamp(
                        market.get("endDate") or event.get("endDate") or timestamp_utc,
                        source_timezone="UTC",
                    ),
                    "tags": event.get("tags", []),
                    "source": "polymarket",
                    "raw_path": raw_path,
                }
            )
            odds.append(
                {
                    "market_id": str(market["id"]),
                    "timestamp_utc": timestamp_utc,
                    "yes_prob": yes_prob,
                    "no_prob": no_prob,
                    "last_trade_price": coerce_float(market.get("lastTradePrice")),
                    "volume": coerce_float(market.get("volume")),
                    "liquidity": coerce_float(market.get("liquidity") or market.get("liquidityClob")),
                    "raw_path": raw_path,
                }
            )
    return markets, odds
