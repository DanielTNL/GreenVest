"""Portfolio simulation and forecast evaluation engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import prod
from typing import Any, Sequence

from analytics.backtesting import (
    price_records_to_series,
    resample_prices,
)
from analytics.forecasting import backtest_forecast, generate_forecast
from db import KnowledgeBaseManager, MarketRepository
from ingestion.base import utc_now


@dataclass(slots=True)
class PortfolioPosition:
    """A portfolio constituent and its target weight."""

    symbol: str
    weight: float


@dataclass(slots=True)
class SimulationConfig:
    """Configuration for a historical or predictive portfolio simulation."""

    portfolio_name: str
    positions: list[PortfolioPosition]
    start_date: str
    end_date: str
    initial_capital: float
    horizon: int = 1
    horizon_unit: str = "daily"
    model_name: str = "arima"
    basket_id: int | None = None
    transaction_cost_rate: float = 0.001
    slippage_rate: float = 0.0001


@dataclass(slots=True)
class SimulationModelSpec:
    """Logical simulation model presented to the end user."""

    semantic_key: str
    display_name: str
    forecast_model: str
    version_id: str
    explanation: str


class PortfolioSimulator:
    """Runs backtests and forecast-versus-actual evaluations for portfolios."""

    def __init__(
        self,
        repository: MarketRepository,
        knowledge_manager: KnowledgeBaseManager | None = None,
    ) -> None:
        self.repository = repository
        self.knowledge_manager = knowledge_manager

    def run_comparative_simulation(
        self,
        *,
        config: SimulationConfig,
        simulation_type: str,
        asset_kind: str,
        asset_identifier: str,
        model_specs: Sequence[SimulationModelSpec],
    ) -> dict[str, Any]:
        steps = _date_steps(config.start_date, config.end_date, config.horizon_unit)
        if steps <= 0:
            raise ValueError("End date must be after start date.")

        weights = {position.symbol: position.weight for position in config.positions}
        timestamp = utc_now()
        simulation_mode = simulation_type.lower()
        results: list[dict[str, Any]] = []
        prediction_outcomes: list[dict[str, Any]] = []
        actual_portfolio_return: float | None = None
        latest_updated_version = None
        if self.knowledge_manager is not None and any(
            spec.semantic_key == "updated_working_model" for spec in model_specs
        ):
            latest_updated_version = self.knowledge_manager.get_active_version(config.horizon_unit)

        for spec in model_specs:
            if simulation_mode == "future" and spec.semantic_key == "updated_working_model":
                # Reserve Updated Working Model for end-of-run comparison in future simulations.
                continue
            model_result = self._evaluate_model(
                config=config,
                weights=weights,
                steps=steps,
                spec=spec,
                simulation_type=simulation_mode,
            )
            model_result["latest_updated_working_version"] = latest_updated_version
            results.append(model_result)
            if model_result.get("actual_return") is not None:
                actual_portfolio_return = model_result["actual_return"]
                for symbol, predicted_total in model_result["component_predictions"].items():
                    actual_total = model_result["component_actuals"].get(symbol)
                    if actual_total is None:
                        continue
                    prediction_outcomes.append(
                        {
                            "symbol": symbol,
                            "model_key": spec.forecast_model,
                            "prediction_timestamp_utc": timestamp,
                            "target_timestamp_utc": config.end_date,
                            "predicted_value": predicted_total,
                            "actual_value": actual_total,
                            "absolute_error": abs(actual_total - predicted_total),
                            "squared_error": (actual_total - predicted_total) ** 2,
                            "mape": _safe_mape(actual_total, predicted_total),
                            "direction_correct": (predicted_total >= 0) == (actual_total >= 0),
                            "metadata": {
                                "semantic_model": spec.semantic_key,
                                "version_id": spec.version_id,
                            },
                        }
                    )

        completed_results = [result for result in results if result.get("actual_return") is not None]
        if completed_results:
            ranked = sorted(
                completed_results,
                key=lambda item: (
                    item.get("absolute_error", float("inf")),
                    -float(item.get("directional_accuracy") or 0.0),
                ),
            )
            for index, item in enumerate(ranked, start=1):
                item["rank"] = index
            best_model = ranked[0]["model_key"]
            status = "completed"
            resolved_at_utc = timestamp
        else:
            best_model = None
            status = "awaiting_actual_data"
            resolved_at_utc = None

        primary_result = next(
            (item for item in results if item["model_key"] == "updated_working_model"),
            results[0],
        )
        details = {
            "simulation_type": simulation_mode,
            "asset_kind": asset_kind,
            "asset_identifier": asset_identifier,
            "status": status,
            "models_used": [spec.display_name for spec in model_specs],
            "model_results": results,
            "best_model": best_model,
            "ai_analysis": None,
            "key_outcome_summary": _key_outcome_summary(results, status=status),
            "resolved_at_utc": resolved_at_utc,
        }
        sim_id = self.repository.save_simulation(
            {
                "basket_id": config.basket_id,
                "portfolio_name": config.portfolio_name,
                "start_date": config.start_date,
                "end_date": config.end_date,
                "horizon": steps,
                "horizon_unit": config.horizon_unit,
                "initial_capital": config.initial_capital,
                "predicted_return": primary_result.get("predicted_return"),
                "actual_return": actual_portfolio_return,
                "rmse": primary_result.get("absolute_error"),
                "mape": primary_result.get("percentage_error"),
                "directional_accuracy": primary_result.get("directional_accuracy"),
                "details": details,
            }
        )
        self.repository.save_simulation_results(
            [
                {
                    "simulation_id": sim_id,
                    "evaluation_timestamp_utc": timestamp,
                    "model": result["display_name"],
                    "predicted_value": result.get("predicted_return"),
                    "actual_value": result.get("actual_return"),
                    "absolute_error": result.get("absolute_error"),
                    "squared_error": (
                        (result["actual_return"] - result["predicted_return"]) ** 2
                        if result.get("actual_return") is not None and result.get("predicted_return") is not None
                        else None
                    ),
                    "percentage_error": result.get("percentage_error"),
                }
                for result in results
            ]
        )
        if self.knowledge_manager is not None and prediction_outcomes:
            updated_version = self.knowledge_manager.update_from_prediction_outcomes(
                config.horizon_unit,
                prediction_outcomes,
            )
            details["learning_update_version"] = updated_version
            self.repository.update_simulation(
                sim_id,
                predicted_return=primary_result.get("predicted_return"),
                actual_return=actual_portfolio_return,
                rmse=primary_result.get("absolute_error"),
                mape=primary_result.get("percentage_error"),
                directional_accuracy=primary_result.get("directional_accuracy"),
                details=details,
            )
        return {
            "simulation_id": sim_id,
            "simulation_type": simulation_mode,
            "status": status,
            "portfolio_name": config.portfolio_name,
            "asset_kind": asset_kind,
            "asset_identifier": asset_identifier,
            "start_date": config.start_date,
            "end_date": config.end_date,
            "initial_investment": config.initial_capital,
            "models": results,
            "best_model": best_model,
            "ai_analysis": None,
            "key_outcome_summary": details["key_outcome_summary"],
        }

    def resolve_future_simulation(
        self,
        simulation_record: dict[str, Any],
        *,
        asset_kind: str,
        asset_identifier: str,
        positions: Sequence[PortfolioPosition],
    ) -> dict[str, Any] | None:
        details = simulation_record.get("details") or {}
        if details.get("status") != "awaiting_actual_data":
            return simulation_record

        today = date.today().isoformat()
        if simulation_record["end_date"] > today:
            return simulation_record

        actual_return, component_actuals = self._portfolio_actual_return(
            positions=positions,
            start_date=simulation_record["start_date"],
            end_date=simulation_record["end_date"],
            horizon_unit=simulation_record["horizon_unit"],
        )
        if actual_return is None:
            return simulation_record

        model_results = list(details.get("model_results") or [])
        if not model_results:
            return simulation_record

        if self.knowledge_manager is not None and not any(
            item.get("model_key") == "updated_working_model" for item in model_results
        ):
            config = SimulationConfig(
                portfolio_name=simulation_record.get("portfolio_name") or "Portfolio",
                positions=list(positions),
                start_date=simulation_record["start_date"],
                end_date=simulation_record["end_date"],
                initial_capital=float(simulation_record["initial_capital"]),
                horizon=1,
                horizon_unit=simulation_record["horizon_unit"],
                model_name=self.knowledge_manager.get_active_version(simulation_record["horizon_unit"]),
                basket_id=simulation_record.get("basket_id"),
            )
            updated_spec = SimulationModelSpec(
                semantic_key="updated_working_model",
                display_name="Updated Working Model",
                forecast_model="prophet",
                version_id=self.knowledge_manager.get_active_version(simulation_record["horizon_unit"]),
                explanation=(
                    "Latest iteratively improved working model, evaluated after the future simulation period completed."
                ),
            )
            model_results.append(
                self._evaluate_model(
                    config=config,
                    weights={position.symbol: position.weight for position in positions},
                    steps=_date_steps(simulation_record["start_date"], simulation_record["end_date"], simulation_record["horizon_unit"]),
                    spec=updated_spec,
                    simulation_type="past",
                )
            )

        timestamp = utc_now()
        prediction_outcomes: list[dict[str, Any]] = []
        for item in model_results:
            item["component_actuals"] = component_actuals
            item["actual_return"] = actual_return
            item["actual_ending_value"] = simulation_record["initial_capital"] * (1 + actual_return)
            item["actual_gain_loss"] = item["actual_ending_value"] - simulation_record["initial_capital"]
            item["absolute_error"] = abs((item.get("predicted_return") or 0.0) - actual_return)
            item["percentage_error"] = _safe_mape(actual_return, item.get("predicted_return") or 0.0)
            item["directional_accuracy"] = float(((item.get("predicted_return") or 0.0) >= 0) == (actual_return >= 0))
            for symbol, predicted_total in (item.get("component_predictions") or {}).items():
                actual_total = component_actuals.get(symbol)
                if actual_total is None:
                    continue
                prediction_outcomes.append(
                    {
                        "symbol": symbol,
                        "model_key": item.get("forecast_model", item["model_key"]),
                        "prediction_timestamp_utc": timestamp,
                        "target_timestamp_utc": simulation_record["end_date"],
                        "predicted_value": predicted_total,
                        "actual_value": actual_total,
                        "absolute_error": abs(actual_total - predicted_total),
                        "squared_error": (actual_total - predicted_total) ** 2,
                        "mape": _safe_mape(actual_total, predicted_total),
                        "direction_correct": (predicted_total >= 0) == (actual_total >= 0),
                        "metadata": {
                            "semantic_model": item["model_key"],
                            "version_id": item.get("version_id"),
                        },
                    }
                )

        ranked = sorted(model_results, key=lambda item: item.get("absolute_error", float("inf")))
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        details["model_results"] = model_results
        details["best_model"] = ranked[0]["model_key"]
        details["status"] = "completed"
        details["resolved_at_utc"] = timestamp
        details["key_outcome_summary"] = _key_outcome_summary(model_results, status="completed")

        if self.knowledge_manager is not None and prediction_outcomes:
            details["learning_update_version"] = self.knowledge_manager.update_from_prediction_outcomes(
                simulation_record["horizon_unit"],
                prediction_outcomes,
            )

        primary_result = next(
            (item for item in model_results if item["model_key"] == "updated_working_model"),
            model_results[0],
        )
        self.repository.update_simulation(
            simulation_record["sim_id"],
            predicted_return=primary_result.get("predicted_return"),
            actual_return=actual_return,
            rmse=primary_result.get("absolute_error"),
            mape=primary_result.get("percentage_error"),
            directional_accuracy=primary_result.get("directional_accuracy"),
            details=details,
        )
        self.repository.save_simulation_results(
            [
                {
                    "simulation_id": simulation_record["sim_id"],
                    "evaluation_timestamp_utc": timestamp,
                    "model": item["display_name"],
                    "predicted_value": item.get("predicted_return"),
                    "actual_value": item.get("actual_return"),
                    "absolute_error": item.get("absolute_error"),
                    "squared_error": (
                        (item["actual_return"] - item["predicted_return"]) ** 2
                        if item.get("actual_return") is not None and item.get("predicted_return") is not None
                        else None
                    ),
                    "percentage_error": item.get("percentage_error"),
                }
                for item in model_results
            ]
        )
        refreshed = self.repository.get_simulation(simulation_record["sim_id"])
        return refreshed

    def _evaluate_model(
        self,
        *,
        config: SimulationConfig,
        weights: dict[str, float],
        steps: int,
        spec: SimulationModelSpec,
        simulation_type: str,
    ) -> dict[str, Any]:
        component_predictions: dict[str, float] = {}
        component_actuals: dict[str, float] = {}
        absolute_errors: list[float] = []
        direction_hits: list[float] = []
        actual_available = simulation_type == "past"

        for position in config.positions:
            train_end = config.end_date if simulation_type == "past" else config.start_date
            records = self.repository.get_price_series(position.symbol, end_date=train_end)
            series = price_records_to_series(records)
            if config.horizon_unit != "daily":
                series = resample_prices(series, config.horizon_unit)
            returns = [value for _, value in _compute_simple_returns(series)]
            min_required = 8 if simulation_type == "future" else 3
            if len(returns) < min_required:
                raise ValueError(f"Insufficient price history for {position.symbol}.")

            if simulation_type == "past":
                backtest_steps = min(max(1, steps), max(1, len(returns) - 1))
                evaluation = backtest_forecast(spec.forecast_model, returns, test_size=backtest_steps)
                forecast = evaluation["forecast"]
                predicted_total = _compound_return(forecast.predictions)
                actual_total = _compound_return(returns[-backtest_steps:])
                error_value = evaluation["rmse"]
                percentage_error = evaluation["mape"]
                directional_accuracy = evaluation["directional_accuracy"]
                absolute_errors.append(abs(actual_total - predicted_total))
                direction_hits.append(float((predicted_total >= 0) == (actual_total >= 0)))
            else:
                forecast_horizon = min(max(1, steps), 12)
                forecast = generate_forecast(spec.forecast_model, returns, horizon=forecast_horizon)
                predicted_total = _compound_return(forecast.predictions)
                actual_total = None
                error_value = None
                percentage_error = None
                directional_accuracy = None

            component_predictions[position.symbol] = predicted_total
            if actual_total is not None:
                component_actuals[position.symbol] = actual_total
            self.repository.save_forecast(
                {
                    "symbol": position.symbol,
                    "model": spec.display_name,
                    "run_timestamp_utc": utc_now(),
                    "horizon": steps,
                    "horizon_unit": config.horizon_unit,
                    "forecast_value": predicted_total,
                    "lower_bound": forecast.lower_bounds[0] if forecast.lower_bounds else None,
                    "upper_bound": forecast.upper_bounds[0] if forecast.upper_bounds else None,
                    "exogenous_features": None,
                    "version_id": spec.version_id,
                    "actual_value": actual_total,
                    "error_metric": "rmse",
                    "error_value": error_value,
                    "status": "evaluated" if actual_total is not None else "pending_actuals",
                }
            )

        predicted_portfolio_return = sum(weights[symbol] * component_predictions[symbol] for symbol in weights)
        actual_portfolio_return = (
            sum(weights[symbol] * component_actuals.get(symbol, 0.0) for symbol in weights)
            if actual_available and component_actuals
            else None
        )
        return {
            "model_key": spec.semantic_key,
            "display_name": spec.display_name,
            "forecast_model": spec.forecast_model,
            "version_id": spec.version_id,
            "explanation": spec.explanation,
            "predicted_return": predicted_portfolio_return,
            "actual_return": actual_portfolio_return,
            "predicted_ending_value": config.initial_capital * (1 + predicted_portfolio_return),
            "actual_ending_value": (
                config.initial_capital * (1 + actual_portfolio_return)
                if actual_portfolio_return is not None
                else None
            ),
            "predicted_gain_loss": config.initial_capital * predicted_portfolio_return,
            "actual_gain_loss": (
                config.initial_capital * actual_portfolio_return if actual_portfolio_return is not None else None
            ),
            "absolute_error": (
                abs(actual_portfolio_return - predicted_portfolio_return)
                if actual_portfolio_return is not None
                else None
            ),
            "percentage_error": (
                _safe_mape(actual_portfolio_return, predicted_portfolio_return)
                if actual_portfolio_return is not None
                else None
            ),
            "directional_accuracy": (
                float((predicted_portfolio_return >= 0) == (actual_portfolio_return >= 0))
                if actual_portfolio_return is not None
                else None
            ),
            "status": "completed" if actual_portfolio_return is not None else "awaiting_actual_data",
            "component_predictions": component_predictions,
            "component_actuals": component_actuals,
            "mean_component_error": (sum(absolute_errors) / len(absolute_errors)) if absolute_errors else None,
            "mean_component_direction": (sum(direction_hits) / len(direction_hits)) if direction_hits else None,
        }

    def _portfolio_actual_return(
        self,
        *,
        positions: Sequence[PortfolioPosition],
        start_date: str,
        end_date: str,
        horizon_unit: str,
    ) -> tuple[float | None, dict[str, float]]:
        component_actuals: dict[str, float] = {}
        weighted_total = 0.0
        included = 0
        for position in positions:
            records = self.repository.get_price_series(
                position.symbol,
                start_date=start_date,
                end_date=end_date,
            )
            series = price_records_to_series(records)
            if horizon_unit != "daily":
                series = resample_prices(series, horizon_unit)
            if len(series) < 2:
                continue
            start_price = series[0][1]
            end_price = series[-1][1]
            if start_price == 0:
                continue
            asset_return = (end_price / start_price) - 1.0
            component_actuals[position.symbol] = asset_return
            weighted_total += position.weight * asset_return
            included += 1
        if included == 0:
            return None, {}
        return weighted_total, component_actuals


def _compound_return(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0
    return prod(1 + value for value in returns) - 1.0


def _date_steps(start_date: str, end_date: str, horizon_unit: str) -> int:
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    if end <= start:
        return 0
    days = (end - start).days
    if horizon_unit == "daily":
        return max(1, days)
    if horizon_unit == "weekly":
        return max(1, days // 7)
    if horizon_unit == "monthly":
        return max(1, days // 30)
    raise ValueError(f"Unsupported horizon_unit '{horizon_unit}'.")


def _safe_mape(actual: float, predicted: float) -> float:
    if actual == 0:
        return 0.0
    return abs((actual - predicted) / actual)


def _compute_simple_returns(series: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    results: list[tuple[str, float]] = []
    previous: float | None = None
    for timestamp, value in series:
        if previous is not None and previous != 0:
            results.append((timestamp, (value / previous) - 1.0))
        previous = value
    return results


def _key_outcome_summary(results: Sequence[dict[str, Any]], *, status: str) -> str:
    if not results:
        return "No models were evaluated."
    if status != "completed":
        return "Predictions are stored and waiting for end-of-period market data."
    ranked = sorted(results, key=lambda item: item.get("absolute_error", float("inf")))
    best = ranked[0]
    return (
        f"{best['display_name']} performed best so far with predicted "
        f"{best['predicted_return']:.2%} versus actual {best['actual_return']:.2%}."
    )
