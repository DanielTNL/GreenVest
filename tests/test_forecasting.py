"""Unit tests for forecasting helpers that do not require optional heavy dependencies."""

from __future__ import annotations

import unittest

from forecasting.utils import directional_accuracy, mape, rmse, split_series


class ForecastingUtilityTests(unittest.TestCase):
    def test_split_series(self) -> None:
        train, test = split_series([1, 2, 3, 4, 5], test_size=2)
        self.assertEqual(train, [1, 2, 3])
        self.assertEqual(test, [4, 5])

    def test_rmse_and_mape(self) -> None:
        actual = [1.0, 2.0, 3.0]
        predicted = [1.0, 2.5, 2.5]
        self.assertAlmostEqual(rmse(actual, predicted), 0.408248290463863, places=12)
        self.assertAlmostEqual(mape(actual, predicted), 0.13888888888888887, places=12)
        self.assertAlmostEqual(directional_accuracy(actual, predicted), 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
