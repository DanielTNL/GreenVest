"""ARIMA/SARIMAX forecasting wrapper."""

from __future__ import annotations

from typing import Any, Sequence

from .base import BaseForecaster, DependencyUnavailableError, ForecastResult
from .utils import exogenous_to_matrix


class ARIMAForecaster(BaseForecaster):
    """Thin wrapper around statsmodels SARIMAX."""

    model_name = "arima"

    def __init__(self) -> None:
        self._result = None

    def fit(
        self,
        *,
        series: Sequence[float],
        dates: Sequence[str] | None = None,
        exogenous: Any = None,
        order: tuple[int, int, int] = (1, 1, 1),
        seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0),
        **kwargs: Any,
    ) -> "ARIMAForecaster":
        try:
            from statsmodels.tsa.statespace.sarimax import SARIMAX
        except ImportError as exc:
            raise DependencyUnavailableError(
                "statsmodels is required for ARIMA/SARIMAX forecasting."
            ) from exc
        exog_matrix = exogenous_to_matrix(exogenous)
        model = SARIMAX(
            list(series),
            exog=exog_matrix,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        self._result = model.fit(disp=False)
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
            raise RuntimeError("ARIMA forecaster must be fit before forecasting.")
        exog_matrix = exogenous_to_matrix(exogenous_future)
        forecast = self._result.get_forecast(steps=horizon, exog=exog_matrix)
        interval = forecast.conf_int()
        lower_bounds = interval.iloc[:, 0].astype(float).tolist() if hasattr(interval, "iloc") else None
        upper_bounds = interval.iloc[:, 1].astype(float).tolist() if hasattr(interval, "iloc") else None
        return ForecastResult(
            model=self.model_name,
            predictions=[float(value) for value in forecast.predicted_mean],
            lower_bounds=lower_bounds,
            upper_bounds=upper_bounds,
            metadata={"summary": str(self._result.summary())},
        )
