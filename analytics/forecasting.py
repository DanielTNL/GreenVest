"""Forecasting orchestration and evaluation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from forecasting.arima import ARIMAForecaster
from forecasting.base import DependencyUnavailableError, ForecastResult
from forecasting.garch import GARCHForecaster
from forecasting.naive import NaiveForecaster
from forecasting.prophet_model import ProphetForecaster
from forecasting.utils import directional_accuracy, mape, rmse, split_series


MODEL_REGISTRY = {
    "arima": ARIMAForecaster,
    "baseline": NaiveForecaster,
    "sarima": ARIMAForecaster,
    "garch": GARCHForecaster,
    "naive": NaiveForecaster,
    "prophet": ProphetForecaster,
    "truth_model": NaiveForecaster,
    "working_model": ARIMAForecaster,
    "updated_working_model": ProphetForecaster,
}


def get_forecaster(model_name: str):
    key = model_name.lower()
    if key not in MODEL_REGISTRY:
        raise ValueError(f"Unsupported forecasting model '{model_name}'.")
    return MODEL_REGISTRY[key]()


def generate_forecast(
    model_name: str,
    series: Sequence[float],
    horizon: int,
    *,
    dates: Sequence[str] | None = None,
    exogenous: Any = None,
    exogenous_future: Any = None,
    **model_kwargs: Any,
) -> ForecastResult:
    forecaster = get_forecaster(model_name)
    forecaster.fit(series=series, dates=dates, exogenous=exogenous, **model_kwargs)
    return forecaster.forecast(horizon=horizon, future_dates=None, exogenous_future=exogenous_future)


def backtest_forecast(
    model_name: str,
    series: Sequence[float],
    *,
    test_size: int,
    dates: Sequence[str] | None = None,
    exogenous: Any = None,
    **model_kwargs: Any,
) -> dict[str, Any]:
    train, test = split_series(series, test_size=test_size)
    train_dates, test_dates = split_series(dates, test_size=test_size) if dates else (None, None)
    train_exog, test_exog = split_series(exogenous, test_size=test_size) if exogenous else (None, None)
    forecast = generate_forecast(
        model_name=model_name,
        series=train,
        horizon=len(test),
        dates=train_dates,
        exogenous=train_exog,
        exogenous_future=test_exog,
        **model_kwargs,
    )
    return {
        "forecast": forecast,
        "rmse": rmse(test, forecast.predictions),
        "mape": mape(test, forecast.predictions),
        "directional_accuracy": directional_accuracy(test, forecast.predictions),
    }


__all__ = [
    "DependencyUnavailableError",
    "ForecastResult",
    "backtest_forecast",
    "generate_forecast",
    "get_forecaster",
]
