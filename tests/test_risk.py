"""Unit tests for risk metrics."""

from __future__ import annotations

import math
import unittest

from analytics.risk import (
    RiskComputationError,
    beta,
    build_risk_report,
    compute_returns,
    conditional_value_at_risk,
    correlation,
    covariance,
    maximum_drawdown,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk_historical,
    value_at_risk_monte_carlo,
    value_at_risk_parametric,
    volatility,
)


class RiskMetricTests(unittest.TestCase):
    def test_compute_returns(self) -> None:
        returns = compute_returns([100, 110, 99])
        self.assertAlmostEqual(returns[0], 0.10, places=8)
        self.assertAlmostEqual(returns[1], -0.10, places=8)

    def test_core_statistics(self) -> None:
        asset = [0.01, 0.02, -0.01, 0.03, 0.015]
        bench = [0.008, 0.018, -0.012, 0.025, 0.01]
        self.assertAlmostEqual(covariance(asset, bench), 0.00020575, places=8)
        self.assertAlmostEqual(correlation(asset, bench), 0.99541433, places=7)
        self.assertAlmostEqual(beta(asset, bench), 1.05947476, places=7)

    def test_risk_ratios_and_volatility(self) -> None:
        returns = [0.01, 0.015, -0.005, 0.02, -0.01, 0.005]
        self.assertGreater(volatility(returns), 0)
        self.assertGreater(sharpe_ratio(returns, risk_free_rate=0.02), -10)
        self.assertGreater(sortino_ratio(returns, risk_free_rate=0.02), -10)

    def test_var_and_cvar_are_non_negative(self) -> None:
        returns = [-0.04, -0.02, 0.01, 0.015, -0.03, 0.02, -0.01, 0.005]
        self.assertGreaterEqual(value_at_risk_parametric(returns, portfolio_value=1000), 0)
        self.assertGreaterEqual(value_at_risk_historical(returns, portfolio_value=1000), 0)
        self.assertGreaterEqual(value_at_risk_monte_carlo(returns, portfolio_value=1000, simulations=500), 0)
        self.assertGreaterEqual(conditional_value_at_risk(returns, portfolio_value=1000), 0)

    def test_maximum_drawdown(self) -> None:
        prices = [100, 120, 115, 90, 95, 130]
        self.assertAlmostEqual(maximum_drawdown(prices), -0.25, places=8)

    def test_insufficient_data_raises(self) -> None:
        with self.assertRaises(RiskComputationError):
            build_risk_report([100.0])


if __name__ == "__main__":
    unittest.main()
