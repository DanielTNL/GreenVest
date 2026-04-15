"""Dependency-light baseline forecaster used for previews and local development."""

from __future__ import annotations

from statistics import fmean, stdev
from typing import Any, Sequence

from .base import BaseForecaster, ForecastResult


class NaiveForecaster(BaseForecaster):
    """Simple forecaster that projects the trailing mean return forward."""

    model_name = "baseline"

    def __init__(self) -> None:
        self._series: list[float] = []
        self._window: int = 5

    def fit(
        self,
        *,
        series: Sequence[float],
        dates: Sequence[str] | None = None,
        exogenous: Any = None,
        window: int = 5,
        **kwargs: Any,
    ) -> "NaiveForecaster":
        self._series = [float(value) for value in series]
        self._window = max(1, min(window, len(self._series) or 1))
        return self

    def forecast(
        self,
        *,
        horizon: int,
        future_dates: Sequence[str] | None = None,
        exogenous_future: Any = None,
        **kwargs: Any,
    ) -> ForecastResult:
        if not self._series:
            raise RuntimeError("Baseline forecaster must be fit before forecasting.")
        window_values = self._series[-self._window :]
        center = fmean(window_values)
        spread = stdev(window_values) if len(window_values) > 1 else abs(center) * 0.5
        predictions = [center for _ in range(horizon)]
        lower_bounds = [center - spread for _ in range(horizon)]
        upper_bounds = [center + spread for _ in range(horizon)]
        return ForecastResult(
            model=self.model_name,
            predictions=predictions,
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            metadata={"window": self._window},
        )
