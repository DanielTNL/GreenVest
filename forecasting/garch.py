"""GARCH forecasting wrapper."""

from __future__ import annotations

import math
from typing import Any, Sequence

from .base import BaseForecaster, DependencyUnavailableError, ForecastResult


class GARCHForecaster(BaseForecaster):
    """Thin wrapper around the arch package for volatility forecasting."""

    model_name = "garch"

    def __init__(self) -> None:
        self._result = None
        self._scale_factor = 1.0

    def fit(
        self,
        *,
        series: Sequence[float],
        dates: Sequence[str] | None = None,
        exogenous: Any = None,
        p: int = 1,
        q: int = 1,
        mean_model: str = "Constant",
        distribution: str = "normal",
        **kwargs: Any,
    ) -> "GARCHForecaster":
        try:
            from arch import arch_model
        except ImportError as exc:
            raise DependencyUnavailableError("arch is required for GARCH forecasting.") from exc
        values = [float(value) for value in series]
        self._scale_factor = _fit_scale_factor(values)
        scaled_values = [value * self._scale_factor for value in values]
        model = arch_model(
            scaled_values,
            p=p,
            q=q,
            mean=mean_model,
            vol="GARCH",
            dist=distribution,
            rescale=False,
        )
        self._result = model.fit(disp="off")
        return self

    def forecast(
        self,
        *,
        horizon: int,
        future_dates: Sequence[str] | None = None,
        exogenous_future: Any = None,
        **kwargs: Any,
    ) -> ForecastResult:
        if self._result is None:
            raise RuntimeError("GARCH forecaster must be fit before forecasting.")
        forecast = self._result.forecast(horizon=horizon)
        variance_row = forecast.variance.iloc[-1].tolist()
        mean_row = forecast.mean.iloc[-1].tolist() if hasattr(forecast, "mean") else [0.0] * horizon
        volatilities = [math.sqrt(max(value, 0.0)) / self._scale_factor for value in variance_row]
        return ForecastResult(
            model=self.model_name,
            predictions=[float(value) / self._scale_factor for value in mean_row],
            metadata={"volatility_forecast": volatilities, "scale_factor": self._scale_factor},
        )


def _fit_scale_factor(series: Sequence[float]) -> float:
    max_abs = max((abs(value) for value in series), default=0.0)
    if max_abs == 0:
        return 1.0
    scale_factor = 1.0
    scaled_max = max_abs
    while scaled_max < 1.0:
        scale_factor *= 10.0
        scaled_max *= 10.0
    while scaled_max > 1000.0:
        scale_factor /= 10.0
        scaled_max /= 10.0
    return scale_factor
