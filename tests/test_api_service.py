"""Tests for the local app service facade."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from api.service import AppService
from config.settings import Settings
from db import KnowledgeBaseManager, MarketRepository, initialize_knowledge_bases, initialize_market_database


class AppServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.settings = Settings(project_root=temp_path, storage_root=temp_path)
        initialize_market_database(self.settings)
        initialize_knowledge_bases(self.settings)
        self.repository = MarketRepository(self.settings)
        self.repository.upsert_stocks(
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "asset_type": "equity", "source": "test"},
                {"symbol": "MSFT", "name": "Microsoft Corp.", "exchange": "NASDAQ", "asset_type": "equity", "source": "test"},
            ]
        )
        self.repository.upsert_stock_prices(self._seed_prices("AAPL", [100, 101, 103, 104, 105]))
        self.repository.upsert_stock_prices(self._seed_prices("MSFT", [200, 202, 204, 206, 208]))
        self.service = AppService(self.repository, KnowledgeBaseManager(self.settings))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_stock_detail_computes_risk_metrics_when_history_exists(self) -> None:
        detail = self.service.get_stock_detail("AAPL")
        self.assertEqual(detail["stock"]["symbol"], "AAPL")
        self.assertIsNotNone(detail["risk_metrics"])
        self.assertEqual(len(detail["price_history"]), 5)

    def test_create_basket_persists_constituents(self) -> None:
        basket = self.service.create_basket(
            name="Tech Leaders",
            description="Test basket",
            symbols=["AAPL", "MSFT"],
            equal_weight=True,
        )
        self.assertEqual(basket["name"], "Tech Leaders")
        self.assertEqual(len(basket["constituents"]), 2)

    def test_run_simulation_returns_comparative_result(self) -> None:
        result = self.service.run_simulation(
            asset_kind="stock",
            asset_identifier="AAPL",
            horizon_unit="daily",
            model_name="baseline",
        )
        self.assertEqual(result["simulation_type"], "past")
        self.assertEqual(result["models_count"], 2)
        self.assertIn("model_results", result)
        self.assertEqual([item["display_name"] for item in result["model_results"]], ["Truth Model", "Working Model"])
        self.assertIn("ai_analysis", result)

    def test_get_diagnostics_returns_backend_readiness_summary(self) -> None:
        diagnostics = self.service.get_diagnostics()
        self.assertIn("api_keys", diagnostics)
        self.assertIn("econometrics", diagnostics)
        self.assertIn("geopolitical", diagnostics)
        self.assertTrue(diagnostics["econometrics"]["risk_engine"]["operational"])

    def _seed_prices(self, symbol: str, closes: list[float]) -> list[dict[str, object]]:
        records = []
        for index, close in enumerate(closes, start=1):
            records.append(
                {
                    "symbol": symbol,
                    "source": "test",
                    "interval": "1day",
                    "timestamp_utc": f"2026-04-0{index}T00:00:00+00:00",
                    "trading_date": f"2026-04-0{index}",
                    "open": close - 1,
                    "high": close + 1,
                    "low": close - 2,
                    "close": close,
                    "volume": 1000 + index,
                }
            )
        return records


if __name__ == "__main__":
    unittest.main()
