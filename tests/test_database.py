"""Database initialization tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from db import KnowledgeBaseManager, initialize_knowledge_bases, initialize_market_database
from db.connection import connect_sqlite


class DatabaseInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.settings = Settings(project_root=temp_path, storage_root=temp_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_market_database_initializes_expected_tables(self) -> None:
        initialize_market_database(self.settings)
        with connect_sqlite(self.settings.database_path) as connection:
            table_names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertIn("stocks", table_names)
        self.assertIn("stock_prices", table_names)
        self.assertIn("prediction_markets", table_names)
        self.assertIn("risk_metrics_history", table_names)

    def test_knowledge_bases_seed_versions(self) -> None:
        initialize_knowledge_bases(self.settings)
        manager = KnowledgeBaseManager(self.settings)
        self.assertTrue(manager.get_active_version("daily"))
        with connect_sqlite(self.settings.truth_db_path) as connection:
            count = connection.execute("SELECT COUNT(*) AS count FROM metric_definitions").fetchone()["count"]
        self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
