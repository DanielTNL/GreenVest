"""Prophet forecasting wrapper."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Sequence

from .base import BaseForecaster, DependencyUnavailableError, ForecastResult


class ProphetForecaster(BaseForecaster):
    """Thin wrapper around Prophet."""

    model_name = "prophet"

    def __init__(self) -> None:
        self._model = None
        self._last_date: date | None = None
        self._regressor_names: list[str] = []

    def fit(
        self,
        *,
        series: Sequence[float],
        dates: Sequence[str] | None = None,
        exogenous: Any = None,
        yearly_seasonality: bool = True,
        weekly_seasonality: bool = True,
        daily_seasonality: bool = False,
        **kwargs: Any,
    ) -> "ProphetForecaster":
        try:
            import pandas as pd
            from prophet import Prophet
        except ImportError as exc:
            raise DependencyUnavailableError("prophet is required for Prophet forecasting.") from exc
        resolved_dates = list(dates) if dates else _synthetic_dates(len(series))
        frame = pd.DataFrame({"ds": pd.to_datetime(resolved_dates), "y": list(series)})
        self._model = Prophet(
            yearly_seasonality=yearly_seasonality,
            weekly_seasonality=weekly_seasonality,
            daily_seasonality=daily_seasonality,
        )
        if isinstance(exogenous, dict):
            for name, values in exogenous.items():
                self._model.add_regressor(name)
                frame[name] = values
                self._regressor_names.append(name)
        self._model.fit(frame)
        self._last_date = datetime.fromisoformat(resolved_dates[-1]).date()
        return self

    def forecast(
        self,
        *,
        horizon: int,
        future_dates: Sequence[str] | None = None,
        exogenous_future: Any = None,
        **kwargs: Any,
    ) -> ForecastResult:
        if self._model is None or self._last_date is None:
            raise RuntimeError("Prophet forecaster must be fit before forecasting.")
        try:
            import pandas as pd
        except ImportError as exc:
            raise DependencyUnavailableError("pandas is required for Prophet forecasting.") from exc
        resolved_dates = list(future_dates) if future_dates else [
            (self._last_date + timedelta(days=index)).isoformat()
            for index in range(1, horizon + 1)
        ]
        future = pd.DataFrame({"ds": pd.to_datetime(resolved_dates)})
        if isinstance(exogenous_future, dict):
            for name in self._regressor_names:
                future[name] = exogenous_future.get(name, [0.0] * horizon)
        forecast = self._model.predict(future)
        return ForecastResult(
            model=self.model_name,
            predictions=[float(value) for value in forecast["yhat"].tolist()],
            lower_bounds=[float(value) for value in forecast["yhat_lower"].tolist()],
            upper_bounds=[float(value) for value in forecast["yhat_upper"].tolist()],
        )


def _synthetic_dates(length: int) -> list[str]:
    start = date.today() - timedelta(days=length - 1)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(length)]
