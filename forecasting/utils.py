"""Forecasting utility helpers shared across model wrappers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def split_series(series: Sequence[Any] | None, *, test_size: int) -> tuple[list[Any], list[Any]]:
    if series is None:
        return [], []
    values = list(series)
    if not 0 < test_size < len(values):
        raise ValueError("test_size must be between 1 and len(series) - 1.")
    return values[:-test_size], values[-test_size:]


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _validate_matching_lengths(actual, predicted)
    if not actual:
        return 0.0
    squared_errors = [(a - p) ** 2 for a, p in zip(actual, predicted)]
    return math.sqrt(sum(squared_errors) / len(squared_errors))


def mape(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _validate_matching_lengths(actual, predicted)
    if not actual:
        return 0.0
    percentage_errors = [
        abs((a - p) / a)
        for a, p in zip(actual, predicted)
        if a not in (0, 0.0)
    ]
    return sum(percentage_errors) / len(percentage_errors) if percentage_errors else 0.0


def directional_accuracy(actual: Sequence[float], predicted: Sequence[float]) -> float:
    _validate_matching_lengths(actual, predicted)
    if not actual:
        return 0.0
    hits = [math.copysign(1, a) == math.copysign(1, p) for a, p in zip(actual, predicted)]
    return sum(hits) / len(hits)


def exogenous_to_matrix(exogenous: Any) -> Any:
    if exogenous is None:
        return None
    if isinstance(exogenous, dict):
        keys = list(exogenous)
        return [[exogenous[key][idx] for key in keys] for idx in range(len(exogenous[keys[0]]))]
    if exogenous and isinstance(exogenous[0], dict):
        keys = sorted(exogenous[0])
        return [[row[key] for key in keys] for row in exogenous]
    return exogenous


def _validate_matching_lengths(actual: Sequence[float], predicted: Sequence[float]) -> None:
    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted sequences must have matching lengths.")
