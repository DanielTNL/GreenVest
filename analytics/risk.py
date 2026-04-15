"""Risk metric implementations for portfolio and asset analysis."""

from __future__ import annotations

import math
import random
import warnings
from dataclasses import dataclass
from statistics import NormalDist, fmean, stdev
from typing import Sequence


class RiskComputationError(ValueError):
    """Raised when a risk metric cannot be computed safely."""


@dataclass(slots=True)
class RiskReport:
    """Convenience container for a bundle of risk statistics."""

    volatility: float
    sharpe: float
    sortino: float
    beta: float | None
    var_parametric: float
    var_historical: float
    var_monte_carlo: float
    cvar: float
    max_drawdown: float
    covariance: float | None = None
    correlation: float | None = None


def compute_returns(prices: Sequence[float], lookback: int | None = None) -> list[float]:
    price_series = _tail(prices, lookback)
    if len(price_series) < 2:
        raise RiskComputationError("At least two price points are required to compute returns.")
    returns: list[float] = []
    for previous, current in zip(price_series, price_series[1:]):
        if previous == 0:
            raise RiskComputationError("Encountered zero price while computing returns.")
        returns.append((current / previous) - 1.0)
    return returns


def volatility(returns: Sequence[float], lookback: int | None = None, periods_per_year: int = 252) -> float:
    series = _require_minimum(_tail(returns, lookback), minimum=2, name="returns")
    return stdev(series) * math.sqrt(periods_per_year)


def covariance(left: Sequence[float], right: Sequence[float], lookback: int | None = None) -> float:
    left_series, right_series = _paired_series(left, right, lookback)
    left_mean = fmean(left_series)
    right_mean = fmean(right_series)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left_series, right_series))
    return numerator / (len(left_series) - 1)


def correlation(left: Sequence[float], right: Sequence[float], lookback: int | None = None) -> float:
    left_series, right_series = _paired_series(left, right, lookback)
    sigma_left = stdev(left_series)
    sigma_right = stdev(right_series)
    if sigma_left == 0 or sigma_right == 0:
        raise RiskComputationError("Correlation is undefined when one series has zero variance.")
    return covariance(left_series, right_series) / (sigma_left * sigma_right)


def sharpe_ratio(
    returns: Sequence[float],
    risk_free_rate: float = 0.0,
    lookback: int | None = None,
    periods_per_year: int = 252,
) -> float:
    series = _require_minimum(_tail(returns, lookback), minimum=2, name="returns")
    sigma = stdev(series)
    if sigma == 0:
        raise RiskComputationError("Sharpe ratio is undefined when returns have zero variance.")
    risk_free_per_period = risk_free_rate / periods_per_year
    return ((fmean(series) - risk_free_per_period) / sigma) * math.sqrt(periods_per_year)


def sortino_ratio(
    returns: Sequence[float],
    risk_free_rate: float = 0.0,
    target_return: float = 0.0,
    lookback: int | None = None,
    periods_per_year: int = 252,
) -> float:
    series = _require_minimum(_tail(returns, lookback), minimum=2, name="returns")
    target_per_period = max(risk_free_rate / periods_per_year, target_return)
    downside = [minimum_return - target_per_period for minimum_return in series if minimum_return < target_per_period]
    if len(downside) < 2:
        raise RiskComputationError("Sortino ratio requires at least two downside observations.")
    downside_deviation = stdev(downside)
    if downside_deviation == 0:
        raise RiskComputationError("Sortino ratio is undefined when downside deviation is zero.")
    return ((fmean(series) - target_per_period) / downside_deviation) * math.sqrt(periods_per_year)


def beta(asset_returns: Sequence[float], benchmark_returns: Sequence[float], lookback: int | None = None) -> float:
    asset_series, benchmark_series = _paired_series(asset_returns, benchmark_returns, lookback)
    benchmark_variance = _sample_variance(benchmark_series)
    if benchmark_variance == 0:
        raise RiskComputationError("Beta is undefined when benchmark variance is zero.")
    return covariance(asset_series, benchmark_series) / benchmark_variance


def value_at_risk_parametric(
    returns: Sequence[float],
    confidence_level: float = 0.95,
    lookback: int | None = None,
    portfolio_value: float = 1.0,
    horizon_days: int = 1,
) -> float:
    _validate_confidence(confidence_level)
    series = _require_minimum(_tail(returns, lookback), minimum=2, name="returns")
    _warn_if_non_normal(series)
    mu = fmean(series) * horizon_days
    sigma = stdev(series) * math.sqrt(horizon_days)
    z_score = NormalDist().inv_cdf(1 - confidence_level)
    var_return = -(mu + (z_score * sigma))
    return max(0.0, var_return * portfolio_value)


def value_at_risk_historical(
    returns: Sequence[float],
    confidence_level: float = 0.95,
    lookback: int | None = None,
    portfolio_value: float = 1.0,
) -> float:
    _validate_confidence(confidence_level)
    series = sorted(_require_minimum(_tail(returns, lookback), minimum=2, name="returns"))
    percentile_return = _quantile(series, 1 - confidence_level)
    return max(0.0, -percentile_return * portfolio_value)


def value_at_risk_monte_carlo(
    returns: Sequence[float],
    confidence_level: float = 0.95,
    lookback: int | None = None,
    portfolio_value: float = 1.0,
    horizon_days: int = 1,
    simulations: int = 5000,
    seed: int | None = 7,
) -> float:
    _validate_confidence(confidence_level)
    series = _require_minimum(_tail(returns, lookback), minimum=2, name="returns")
    rng = random.Random(seed)
    simulated_returns: list[float] = []
    for _ in range(simulations):
        path_return = sum(rng.choice(series) for _ in range(horizon_days))
        simulated_returns.append(path_return)
    percentile_return = _quantile(sorted(simulated_returns), 1 - confidence_level)
    return max(0.0, -percentile_return * portfolio_value)


def conditional_value_at_risk(
    returns: Sequence[float],
    confidence_level: float = 0.95,
    lookback: int | None = None,
    portfolio_value: float = 1.0,
) -> float:
    _validate_confidence(confidence_level)
    series = sorted(_require_minimum(_tail(returns, lookback), minimum=2, name="returns"))
    cutoff = _quantile(series, 1 - confidence_level)
    tail = [value for value in series if value <= cutoff]
    if not tail:
        raise RiskComputationError("CVaR could not be computed because the tail set is empty.")
    return max(0.0, -fmean(tail) * portfolio_value)


def maximum_drawdown(prices: Sequence[float], lookback: int | None = None) -> float:
    price_series = _require_minimum(_tail(prices, lookback), minimum=2, name="prices")
    peak = price_series[0]
    drawdown = 0.0
    for price in price_series:
        peak = max(peak, price)
        if peak == 0:
            continue
        drawdown = min(drawdown, (price - peak) / peak)
    return drawdown


def build_risk_report(
    prices: Sequence[float],
    benchmark_prices: Sequence[float] | None = None,
    *,
    risk_free_rate: float = 0.0,
    lookback: int | None = None,
    confidence_level: float = 0.95,
    periods_per_year: int = 252,
    portfolio_value: float = 1.0,
) -> RiskReport:
    returns = compute_returns(prices, lookback=lookback)
    benchmark_returns = compute_returns(benchmark_prices, lookback=lookback) if benchmark_prices else None
    covariance_value = covariance(returns, benchmark_returns) if benchmark_returns else None
    correlation_value = correlation(returns, benchmark_returns) if benchmark_returns else None
    beta_value = beta(returns, benchmark_returns) if benchmark_returns else None
    return RiskReport(
        volatility=volatility(returns, periods_per_year=periods_per_year),
        sharpe=sharpe_ratio(returns, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year),
        sortino=sortino_ratio(returns, risk_free_rate=risk_free_rate, periods_per_year=periods_per_year),
        beta=beta_value,
        var_parametric=value_at_risk_parametric(
            returns,
            confidence_level=confidence_level,
            portfolio_value=portfolio_value,
        ),
        var_historical=value_at_risk_historical(
            returns,
            confidence_level=confidence_level,
            portfolio_value=portfolio_value,
        ),
        var_monte_carlo=value_at_risk_monte_carlo(
            returns,
            confidence_level=confidence_level,
            portfolio_value=portfolio_value,
        ),
        cvar=conditional_value_at_risk(
            returns,
            confidence_level=confidence_level,
            portfolio_value=portfolio_value,
        ),
        max_drawdown=maximum_drawdown(prices),
        covariance=covariance_value,
        correlation=correlation_value,
    )


def _tail(values: Sequence[float], lookback: int | None) -> list[float]:
    series = list(values)
    return series[-lookback:] if lookback else series


def _paired_series(
    left: Sequence[float],
    right: Sequence[float] | None,
    lookback: int | None = None,
) -> tuple[list[float], list[float]]:
    if right is None:
        raise RiskComputationError("Benchmark series is required for paired statistics.")
    left_series = _tail(left, lookback)
    right_series = _tail(right, lookback)
    if len(left_series) != len(right_series):
        raise RiskComputationError("Return series must have the same length.")
    _require_minimum(left_series, minimum=2, name="left returns")
    _require_minimum(right_series, minimum=2, name="right returns")
    return left_series, right_series


def _require_minimum(series: Sequence[float], minimum: int, name: str) -> list[float]:
    if len(series) < minimum:
        raise RiskComputationError(f"Insufficient {name}; expected at least {minimum} observations.")
    return list(series)


def _sample_variance(series: Sequence[float]) -> float:
    mean_value = fmean(series)
    numerator = sum((value - mean_value) ** 2 for value in series)
    return numerator / (len(series) - 1)


def _quantile(series: Sequence[float], percentile: float) -> float:
    if not 0 <= percentile <= 1:
        raise RiskComputationError("Percentile must lie in [0, 1].")
    if len(series) == 1:
        return float(series[0])
    position = (len(series) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(series[lower])
    weight = position - lower
    return float(series[lower] + (series[upper] - series[lower]) * weight)


def _validate_confidence(confidence_level: float) -> None:
    if not 0 < confidence_level < 1:
        raise RiskComputationError("Confidence level must be between 0 and 1.")


def _warn_if_non_normal(series: Sequence[float]) -> None:
    if len(series) < 8:
        return
    mean_value = fmean(series)
    sigma = stdev(series)
    if sigma == 0:
        return
    skew = sum(((value - mean_value) / sigma) ** 3 for value in series) / len(series)
    kurtosis = sum(((value - mean_value) / sigma) ** 4 for value in series) / len(series)
    if abs(skew) > 1.0 or kurtosis > 5.0:
        warnings.warn(
            "Return distribution appears non-normal; prefer historical or Monte Carlo VaR for robustness.",
            RuntimeWarning,
            stacklevel=2,
        )
