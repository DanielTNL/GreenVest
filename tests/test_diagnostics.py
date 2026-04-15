"""Tests for backend diagnostics."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audits.diagnostics import run_backend_diagnostics
from config.settings import Settings


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_path = Path(self.temp_dir.name)
        self.settings = Settings(project_root=temp_path, storage_root=temp_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_diagnostics_returns_expected_sections(self) -> None:
        diagnostics = run_backend_diagnostics(self.settings)
        self.assertIn("api_keys", diagnostics)
        self.assertIn("dependencies", diagnostics)
        self.assertIn("econometrics", diagnostics)
        self.assertIn("assistant", diagnostics)
        self.assertIn("geopolitical", diagnostics)
        self.assertIn("recommendations", diagnostics)
        self.assertTrue(diagnostics["econometrics"]["risk_engine"]["operational"])


if __name__ == "__main__":
    unittest.main()
