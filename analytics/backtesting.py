"""Portfolio return aggregation and backtesting helpers."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime


def price_records_to_series(records: Sequence[dict]) -> list[tuple[str, float]]:
    return [
        (record["trading_date"], float(record["close"]))
        for record in records
        if record.get("close") is not None
    ]


def compute_simple_returns(series: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    if len(series) < 2:
        return []
    returns: list[tuple[str, float]] = []
    for (previous_date, previous_price), (current_date, current_price) in zip(series, series[1:]):
        if previous_price == 0:
            continue
        returns.append((current_date, (current_price / previous_price) - 1.0))
    return returns


def aggregate_portfolio_returns(
    symbol_returns: dict[str, Sequence[tuple[str, float]]],
    weights: dict[str, float],
) -> list[tuple[str, float]]:
    aligned: dict[str, dict[str, float]] = defaultdict(dict)
    for symbol, series in symbol_returns.items():
        for trading_date, value in series:
            aligned[trading_date][symbol] = value
    portfolio_returns: list[tuple[str, float]] = []
    for trading_date in sorted(aligned):
        daily = aligned[trading_date]
        if set(weights).issubset(daily):
            portfolio_returns.append(
                (trading_date, sum(weights[symbol] * daily[symbol] for symbol in weights))
            )
    return portfolio_returns


def cumulative_return_path(returns: Sequence[tuple[str, float]], initial_capital: float = 1.0) -> list[tuple[str, float]]:
    capital = initial_capital
    path: list[tuple[str, float]] = []
    for trading_date, daily_return in returns:
        capital *= 1 + daily_return
        path.append((trading_date, capital))
    return path


def apply_costs(
    returns: Sequence[tuple[str, float]],
    *,
    transaction_cost_rate: float = 0.0,
    slippage_rate: float = 0.0,
) -> list[tuple[str, float]]:
    total_cost = transaction_cost_rate + slippage_rate
    return [(trading_date, daily_return - total_cost) for trading_date, daily_return in returns]


def resample_prices(series: Sequence[tuple[str, float]], horizon_unit: str) -> list[tuple[str, float]]:
    if horizon_unit == "daily":
        return list(series)
    grouped: dict[str, tuple[str, float]] = {}
    for trading_date, value in series:
        dt = datetime.fromisoformat(trading_date).date()
        if horizon_unit == "weekly":
            bucket = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        elif horizon_unit == "monthly":
            bucket = f"{dt.year:04d}-{dt.month:02d}"
        else:
            raise ValueError(f"Unsupported horizon_unit '{horizon_unit}'.")
        grouped[bucket] = (trading_date, value)
    return [grouped[key] for key in sorted(grouped)]


def realised_horizon_return(series: Sequence[tuple[str, float]], horizon_steps: int) -> float:
    if len(series) < horizon_steps + 1:
        raise ValueError("Not enough price history to compute realised horizon return.")
    start_price = series[-(horizon_steps + 1)][1]
    end_price = series[-1][1]
    if start_price == 0:
        raise ValueError("Encountered zero starting price while computing realised return.")
    return (end_price / start_price) - 1.0


def directional_accuracy(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted series must have the same length.")
    if not actual:
        return 0.0
    hits = [math.copysign(1, a) == math.copysign(1, p) for a, p in zip(actual, predicted)]
    return sum(hits) / len(hits)
