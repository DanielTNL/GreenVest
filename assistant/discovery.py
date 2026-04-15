"""Stock discovery helpers for search and daily watch suggestions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from analytics.risk import compute_returns, volatility
from config import Settings
from db import MarketRepository
from ingestion import DataIngestionPipeline
from assistant.openai_client import OpenAIChatClient, OpenAIChatError

THEMATIC_UNIVERSE: tuple[dict[str, Any], ...] = (
    {"symbol": "NVDA", "name": "NVIDIA", "theme": "AI"},
    {"symbol": "AMD", "name": "AMD", "theme": "AI"},
    {"symbol": "MSFT", "name": "Microsoft", "theme": "Technology"},
    {"symbol": "GOOGL", "name": "Alphabet", "theme": "Technology"},
    {"symbol": "META", "name": "Meta", "theme": "AI"},
    {"symbol": "AMZN", "name": "Amazon", "theme": "Cloud"},
    {"symbol": "PLTR", "name": "Palantir", "theme": "AI"},
    {"symbol": "TSM", "name": "TSMC", "theme": "Semiconductors"},
    {"symbol": "AVGO", "name": "Broadcom", "theme": "Semiconductors"},
    {"symbol": "ARM", "name": "Arm", "theme": "AI"},
    {"symbol": "SMR", "name": "NuScale", "theme": "Energy"},
    {"symbol": "XOM", "name": "Exxon Mobil", "theme": "Energy"},
    {"symbol": "CVX", "name": "Chevron", "theme": "Energy"},
    {"symbol": "SLB", "name": "Schlumberger", "theme": "Commodity Trading"},
    {"symbol": "CCJ", "name": "Cameco", "theme": "Energy"},
    {"symbol": "NEM", "name": "Newmont", "theme": "Commodities"},
)


class StockDiscoveryService:
    """Provider-backed symbol search and AI-assisted daily stock suggestions."""

    def __init__(self, settings: Settings, repository: MarketRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.pipeline = DataIngestionPipeline(settings)
        self.fmp = self.pipeline.fmp
        self.openai = OpenAIChatClient(settings)

    def search_candidates(self, query: str, limit: int = 12) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if len(normalized_query) < 2:
            return []

        tracked_symbols = set(self.repository.list_tracked_stock_symbols())
        merged: dict[str, dict[str, Any]] = {}

        for stock in self.repository.search_stocks(query=normalized_query, limit=limit):
            merged[stock["symbol"]] = {
                **stock,
                "is_tracked": stock["symbol"] in tracked_symbols,
            }

        provider_results = self._provider_search(query=normalized_query, limit=limit)
        for item in provider_results:
            symbol = str(item.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            existing = merged.get(symbol, {})
            merged[symbol] = {
                "symbol": symbol,
                "name": item.get("name") or existing.get("name") or symbol,
                "exchange": item.get("exchange") or existing.get("exchange"),
                "asset_type": item.get("asset_type") or existing.get("asset_type") or "equity",
                "source": item.get("source") or existing.get("source") or "fmp_search",
                "latest_close": existing.get("latest_close"),
                "latest_price_timestamp_utc": existing.get("latest_price_timestamp_utc"),
                "is_tracked": symbol in tracked_symbols,
            }

        ranked = sorted(
            merged.values(),
            key=lambda item: (
                0 if item.get("is_tracked") else 1,
                0 if str(item.get("symbol", "")).upper() == normalized_query.upper() else 1,
                0 if normalized_query.upper() in str(item.get("name", "")).upper() else 1,
                0 if str(item.get("exchange", "")).upper() in {"NASDAQ", "NYSE", "AMEX", "OTC"} else 1,
                1 if "." in str(item.get("symbol", "")) else 0,
                str(item.get("symbol", "")),
            ),
        )
        return ranked[:limit]

    def track_symbol(
        self,
        *,
        symbol: str,
        name: str | None = None,
        exchange: str | None = None,
    ) -> dict[str, Any]:
        cleaned_symbol = symbol.upper().strip()
        if not cleaned_symbol:
            raise ValueError("A stock symbol is required.")

        try:
            self.pipeline.ingest_fmp_stock(cleaned_symbol, include_intraday=False)
        except Exception as exc:
            self.repository.log_audit(
                "stock_tracking",
                "warning",
                f"FMP ingestion failed for {cleaned_symbol}; falling back to metadata-only tracking: {exc}",
            )

        self.repository.upsert_stocks(
            [
                {
                    "symbol": cleaned_symbol,
                    "name": name or cleaned_symbol,
                    "exchange": exchange,
                    "asset_type": "equity",
                    "source": "tracked",
                }
            ]
        )
        self.repository.track_stock_symbol(cleaned_symbol)
        tracked = self.repository.search_stocks(query=cleaned_symbol, limit=1)
        if tracked:
            return tracked[0]
        return {
            "symbol": cleaned_symbol,
            "name": name or cleaned_symbol,
            "exchange": exchange,
            "asset_type": "equity",
            "source": "tracked",
            "latest_close": None,
            "latest_price_timestamp_utc": None,
        }

    def list_daily_suggestions(self, limit: int = 5) -> list[dict[str, Any]]:
        today = datetime.now(timezone.utc).date().isoformat()
        existing = self.repository.list_watch_suggestions(suggestion_date=today, limit=limit)
        if len(existing) >= limit:
            return existing
        generated = self.generate_daily_suggestions(suggestion_date=today, limit=limit)
        if generated:
            return generated
        return self.repository.list_watch_suggestions(limit=limit)

    def generate_daily_suggestions(
        self,
        *,
        suggestion_date: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        active_date = suggestion_date or datetime.now(timezone.utc).date().isoformat()
        tracked_symbols = set(self.repository.list_tracked_stock_symbols())
        candidates: list[dict[str, Any]] = []
        for item in THEMATIC_UNIVERSE:
            symbol = item["symbol"]
            self._ensure_history(symbol)
            series = self.repository.get_price_series(symbol)
            closes = [float(row["close"]) for row in series if row.get("close") is not None]
            if len(closes) < 25:
                continue
            momentum_20 = (closes[-1] / closes[-21]) - 1 if len(closes) >= 21 else 0.0
            try:
                realized_vol = volatility(compute_returns(closes, lookback=min(63, len(closes))))
            except Exception:
                realized_vol = 0.0
            score = (momentum_20 * 100.0) - (realized_vol * 10.0) + self._theme_bonus(item["theme"])
            stock = self.repository.get_stock(symbol) or {}
            candidates.append(
                {
                    "symbol": symbol,
                    "name": stock.get("name") or item["name"],
                    "theme": item["theme"],
                    "momentum_20": momentum_20,
                    "volatility": realized_vol,
                    "latest_close": closes[-1],
                    "score": score,
                    "is_tracked": symbol in tracked_symbols,
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        selected = self._rank_with_ai(candidates[:10], limit=limit) or self._rank_deterministically(candidates, limit=limit)
        rows = [
            {
                "symbol": item["symbol"],
                "rank": index + 1,
                "name": item["name"],
                "theme": item["theme"],
                "rationale": item["rationale"],
                "score": item["score"],
                "latest_close": item["latest_close"],
            }
            for index, item in enumerate(selected)
        ]
        self.repository.replace_watch_suggestions(active_date, rows)
        return self.repository.list_watch_suggestions(suggestion_date=active_date, limit=limit)

    def _provider_search(self, *, query: str, limit: int) -> list[dict[str, Any]]:
        if not self.settings.fmp_api_key:
            return []
        results: list[dict[str, Any]] = []
        for payload in (
            self._safe_fmp_search(lambda: self.fmp.search_symbol(query, limit=limit)),
            self._safe_fmp_search(lambda: self.fmp.search_name(query, limit=limit)),
        ):
            for item in payload:
                results.append(
                    {
                        "symbol": str(item.get("symbol") or "").upper(),
                        "name": item.get("name") or item.get("companyName") or str(item.get("symbol") or "").upper(),
                        "exchange": item.get("exchange") or item.get("exchangeShortName"),
                        "asset_type": "equity",
                        "source": "fmp_search",
                    }
                )
        return results

    def _safe_fmp_search(self, operation: Any) -> list[dict[str, Any]]:
        try:
            payload = operation()
        except Exception as exc:
            self.repository.log_audit("stock_search", "warning", f"Provider-backed stock search failed: {exc}")
            return []
        if isinstance(payload, list):
            return payload
        return []

    def _ensure_history(self, symbol: str) -> None:
        series = self.repository.get_price_series(symbol)
        if len(series) >= 25:
            return
        try:
            self.pipeline.ingest_fmp_stock(symbol, include_intraday=False)
        except Exception as exc:
            self.repository.log_audit(
                "watch_suggestions",
                "warning",
                f"Unable to refresh {symbol} for daily suggestions: {exc}",
            )

    def _rank_deterministically(self, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        used_themes: set[str] = set()
        for item in candidates:
            if item["theme"] in used_themes and len(selected) < min(limit, 3):
                continue
            selected.append(
                {
                    **item,
                    "rationale": (
                        f"{item['theme']} name with 20-day momentum of {item['momentum_20'] * 100:.1f}% "
                        f"and annualized volatility near {item['volatility']:.2f}."
                    ),
                }
            )
            used_themes.add(item["theme"])
            if len(selected) == limit:
                break
        return selected

    def _rank_with_ai(self, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]] | None:
        if not candidates:
            return None
        try:
            payload = self.openai.generate_json_object(
                system_instruction=(
                    "You are generating a daily stock watchlist for an educational investment app. "
                    "Select a diverse shortlist for a user interested in technology, AI, commodity trading, and energy. "
                    "Do not give buy or sell advice. Return compact JSON only in the form "
                    "{\"items\": [{\"symbol\": \"NVDA\", \"theme\": \"AI\", \"rationale\": \"...\"}]}."
                ),
                input_payload={
                    "limit": limit,
                    "candidates": [
                        {
                            "symbol": item["symbol"],
                            "name": item["name"],
                            "theme": item["theme"],
                            "momentum_20": round(item["momentum_20"], 4),
                            "volatility": round(item["volatility"], 4),
                            "latest_close": round(item["latest_close"], 2),
                            "score": round(item["score"], 2),
                        }
                        for item in candidates
                    ],
                },
            )
        except OpenAIChatError as exc:
            self.repository.log_audit("watch_suggestions", "warning", f"AI suggestion ranking failed: {exc}")
            return None
        if not payload:
            return None
        by_symbol = {item["symbol"]: item for item in candidates}
        selected: list[dict[str, Any]] = []
        for item in payload.get("items", []):
            symbol = str(item.get("symbol") or "").upper()
            if symbol not in by_symbol or len(selected) >= limit:
                continue
            selected.append(
                {
                    **by_symbol[symbol],
                    "theme": item.get("theme") or by_symbol[symbol]["theme"],
                    "rationale": item.get("rationale") or f"{by_symbol[symbol]['theme']} watchlist candidate.",
                }
            )
        return selected or None

    def _theme_bonus(self, theme: str) -> float:
        bonuses = {
            "AI": 6.0,
            "Technology": 5.0,
            "Semiconductors": 5.0,
            "Cloud": 4.0,
            "Commodity Trading": 4.0,
            "Commodities": 4.0,
            "Energy": 5.0,
        }
        return bonuses.get(theme, 0.0)
