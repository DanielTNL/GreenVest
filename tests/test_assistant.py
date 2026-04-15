"""Tests for the bilingual assistant parser and chat wrapper."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assistant.chat import ChatAssistant
from assistant.nlu_parser import parse_user_message
from api.service import AppService
from config.settings import Settings
from db import KnowledgeBaseManager, MarketRepository, initialize_knowledge_bases, initialize_market_database


class FakeLLMClient:
    def __init__(self, reply: str, *, configured: bool = True) -> None:
        self.reply = reply
        self.configured = configured

    def is_configured(self) -> bool:
        return self.configured

    def generate_reply(self, **_: object) -> str:
        return self.reply


class AssistantParsingTests(unittest.TestCase):
    def test_parses_english_risk_query(self) -> None:
        intent = parse_user_message("Show me today's volatility for Apple.")
        self.assertEqual(intent.name, "calculate_risk_metrics")
        self.assertEqual(intent.entities["metric_key"], "volatility")
        self.assertEqual(intent.entities["symbol"], "AAPL")
        self.assertEqual(intent.language, "en")

    def test_parses_dutch_basket_query(self) -> None:
        intent = parse_user_message(
            "Maak een tech mandje met Apple, Microsoft en Google met gelijke weging."
        )
        self.assertEqual(intent.name, "create_basket")
        self.assertEqual(intent.entities["symbols"], ["AAPL", "MSFT", "GOOGL"])
        self.assertTrue(intent.entities["equal_weight"])
        self.assertEqual(intent.language, "nl")


class AssistantChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.settings = Settings(project_root=temp_path, storage_root=temp_path)
        initialize_market_database(self.settings)
        initialize_knowledge_bases(self.settings)
        repository = MarketRepository(self.settings)
        repository.upsert_stocks(
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "asset_type": "equity", "source": "test"},
            ]
        )
        repository.upsert_stock_prices(
            [
                {
                    "symbol": "AAPL",
                    "source": "test",
                    "interval": "1day",
                    "timestamp_utc": "2026-04-10T00:00:00+00:00",
                    "trading_date": "2026-04-10",
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                    "volume": 10,
                },
                {
                    "symbol": "AAPL",
                    "source": "test",
                    "interval": "1day",
                    "timestamp_utc": "2026-04-11T00:00:00+00:00",
                    "trading_date": "2026-04-11",
                    "open": 101,
                    "high": 103,
                    "low": 100,
                    "close": 102,
                    "volume": 11,
                },
                {
                    "symbol": "AAPL",
                    "source": "test",
                    "interval": "1day",
                    "timestamp_utc": "2026-04-12T00:00:00+00:00",
                    "trading_date": "2026-04-12",
                    "open": 102,
                    "high": 105,
                    "low": 101,
                    "close": 104,
                    "volume": 12,
                },
                {
                    "symbol": "AAPL",
                    "source": "test",
                    "interval": "1day",
                    "timestamp_utc": "2026-04-13T00:00:00+00:00",
                    "trading_date": "2026-04-13",
                    "open": 104,
                    "high": 106,
                    "low": 103,
                    "close": 105,
                    "volume": 13,
                },
            ]
        )
        self.service = AppService(repository, KnowledgeBaseManager(self.settings))
        self.chat = ChatAssistant(self.service, llm_client=FakeLLMClient("", configured=False))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_guardrail_response_blocks_personalized_advice(self) -> None:
        response = self.chat.handle_message("Should I buy Apple right now?")
        self.assertEqual(response["intent"], "guardrail")
        self.assertIn("investment advice", response["reply"])

    def test_chat_can_answer_metric_query(self) -> None:
        response = self.chat.handle_message("Show me today's volatility for Apple.")
        self.assertEqual(response["intent"], "calculate_risk_metrics")
        self.assertIn("AAPL", response["reply"])

    def test_chat_can_use_openai_refinement(self) -> None:
        chat = ChatAssistant(self.service, llm_client=FakeLLMClient("Apple volatility is available from the latest backend snapshot."))
        response = chat.handle_message("Show me today's volatility for Apple.")
        self.assertEqual(response["ai_mode"], "openai")
        self.assertEqual(response["reply"], "Apple volatility is available from the latest backend snapshot.")

    def test_unknown_intent_can_be_softened_by_openai(self) -> None:
        chat = ChatAssistant(
            self.service,
            llm_client=FakeLLMClient("I can explain concepts like Sharpe ratio or run a simulation if you give me a symbol."),
        )
        response = chat.handle_message("Can you explain what Sharpe ratio means?")
        self.assertEqual(response["intent"], "calculate_risk_metrics")
        self.assertEqual(response["ai_mode"], "openai")
        self.assertIn("Sharpe ratio", response["reply"])


if __name__ == "__main__":
    unittest.main()
