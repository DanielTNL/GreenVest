"""Base classes for forecasting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


class DependencyUnavailableError(ImportError):
    """Raised when an optional forecasting dependency is not installed."""


@dataclass(slots=True)
class ForecastResult:
    """Standard forecasting result object shared by model wrappers."""

    model: str
    predictions: list[float]
    lower_bounds: list[float] | None = None
    upper_bounds: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseForecaster:
    """Base forecaster contract."""

    model_name: str = "base"

    def fit(
        self,
        *,
        series: Sequence[float],
        dates: Sequence[str] | None = None,
        exogenous: Any = None,
        **kwargs: Any,
    ) -> "BaseForecaster":
        raise NotImplementedError

    def forecast(
        self,
        *,
        horizon: int,
        future_dates: Sequence[str] | None = None,
        exogenous_future: Any = None,
        **kwargs: Any,
    ) -> ForecastResult:
        raise NotImplementedError
