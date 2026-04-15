"""Backend-facing service objects used by the local HTTP API and chat assistant."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from analytics.forecasting import DependencyUnavailableError
from analytics.risk import (
    RiskComputationError,
    RiskReport,
    build_risk_report,
    compute_returns,
    conditional_value_at_risk,
    maximum_drawdown,
    sharpe_ratio,
    sortino_ratio,
    value_at_risk_historical,
    value_at_risk_monte_carlo,
    value_at_risk_parametric,
    volatility,
)
from assistant.openai_client import OpenAIChatClient, OpenAIChatError
from db import KnowledgeBaseManager, MarketRepository
from assistant.discovery import StockDiscoveryService
from simulations.simulator import PortfolioPosition, PortfolioSimulator, SimulationConfig, SimulationModelSpec


class AppService:
    """Aggregates backend modules into app-friendly read and write operations."""

    def __init__(self, repository: MarketRepository, knowledge_manager: KnowledgeBaseManager) -> None:
        self.repository = repository
        self.knowledge_manager = knowledge_manager
        self.simulator = PortfolioSimulator(repository, knowledge_manager)
        self.discovery = StockDiscoveryService(repository.settings, repository)
        self.llm_client = OpenAIChatClient(repository.settings)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "system_status": self.repository.get_system_status(),
            "truth_version": "truth-v1",
            "working_versions": {
                period: self.knowledge_manager.get_active_version(period)
                for period in ("daily", "weekly", "monthly")
            },
        }

    def list_stocks(self, query: str | None = None) -> dict[str, Any]:
        return {"items": self.repository.list_tracked_stocks(query=query)}

    def search_stock_catalog(self, query: str, limit: int = 12) -> dict[str, Any]:
        return {"items": self.discovery.search_candidates(query=query, limit=limit)}

    def track_stock(
        self,
        *,
        symbol: str,
        name: str | None = None,
        exchange: str | None = None,
    ) -> dict[str, Any]:
        result = self.discovery.track_symbol(symbol=symbol, name=name, exchange=exchange)
        self.repository.create_alert(
            f"Added {result['symbol']} to the watchlist.",
            level="info",
            symbol=result["symbol"],
        )
        return result

    def daily_watch_suggestions(self, limit: int = 5) -> dict[str, Any]:
        return {"items": self.discovery.list_daily_suggestions(limit=limit)}

    def get_stock_detail(self, symbol: str) -> dict[str, Any]:
        stock = self.repository.get_stock(symbol) or {"symbol": symbol.upper(), "name": symbol.upper()}
        price_history = self.repository.get_price_series(symbol.upper())[-90:]
        latest_close = price_history[-1]["close"] if price_history else None
        previous_close = price_history[-2]["close"] if len(price_history) > 1 else None
        risk_metrics = self.repository.latest_risk_metric(symbol=symbol.upper())
        if risk_metrics is None:
            closes = [float(row["close"]) for row in price_history if row.get("close") is not None]
            risk_metrics = self._risk_metrics_from_closes(closes)
        latest_forecast = self.repository.latest_forecast(symbol.upper())
        return {
            "stock": stock,
            "latest_close": latest_close,
            "daily_change_percent": _safe_change(previous_close, latest_close),
            "price_history": price_history,
            "risk_metrics": risk_metrics,
            "latest_forecast": latest_forecast,
        }

    def list_baskets(self) -> dict[str, Any]:
        baskets = []
        for basket in self.repository.list_baskets_with_constituents():
            baskets.append(
                {
                    **basket,
                    "risk_metrics": self.repository.latest_risk_metric(basket_id=int(basket["basket_id"])),
                }
            )
        return {"items": baskets}

    def get_basket_detail(self, basket_id: int) -> dict[str, Any]:
        basket = self.repository.get_basket(basket_id)
        if basket is None:
            raise KeyError(f"Unknown basket_id {basket_id}.")
        basket_history = self._build_basket_history(basket["constituents"])
        risk_metrics = self.repository.latest_risk_metric(basket_id=basket_id)
        if risk_metrics is None:
            closes = [float(point["close"]) for point in basket_history]
            risk_metrics = self._risk_metrics_from_closes(closes)
        simulations = [
            item
            for item in self.repository.list_recent_simulations(limit=50)
            if item.get("basket_id") == basket_id
        ]
        return {
            "basket": basket,
            "price_history": basket_history,
            "risk_metrics": risk_metrics,
            "recent_simulations": simulations[:10],
        }

    def create_basket(
        self,
        *,
        name: str,
        description: str,
        symbols: list[str],
        equal_weight: bool = True,
    ) -> dict[str, Any]:
        cleaned_symbols = [symbol.upper() for symbol in symbols if symbol]
        if not cleaned_symbols:
            raise ValueError("At least one symbol is required.")
        weight = 1.0 / len(cleaned_symbols) if equal_weight else 1.0
        constituents = [(symbol, weight) for symbol in cleaned_symbols]
        self.repository.upsert_stocks(
            {
                "symbol": symbol,
                "name": symbol,
                "exchange": None,
                "asset_type": "equity",
                "source": "assistant",
            }
            for symbol in cleaned_symbols
        )
        basket_id = self.repository.create_basket(name=name, description=description, constituents=constituents)
        self.repository.create_alert(
            f"Basket {name} created with {len(cleaned_symbols)} constituents.",
            level="info",
            symbol="SYSTEM",
        )
        basket = self.repository.get_basket(basket_id)
        if basket is None:
            raise RuntimeError("Basket creation succeeded but the basket could not be loaded.")
        return basket

    def find_basket_by_name(self, name: str) -> dict[str, Any] | None:
        for basket in self.repository.list_baskets_with_constituents():
            if str(basket["name"]).lower() == name.lower():
                return basket
        return None

    def get_metrics_snapshot(self, knowledge_base: str = "working") -> dict[str, Any]:
        version, summary = self._knowledge_context(knowledge_base)
        items: list[dict[str, Any]] = []
        for stock in self.repository.search_stocks(limit=20):
            detail = self.get_stock_detail(stock["symbol"])
            items.append(
                {
                    "id": stock["symbol"],
                    "kind": "stock",
                    "display_name": stock.get("name") or stock["symbol"],
                    "symbol": stock["symbol"],
                    "risk_metrics": detail["risk_metrics"],
                    "latest_forecast": detail["latest_forecast"],
                    "latest_close": detail["latest_close"],
                }
            )
        for basket in self.repository.list_baskets_with_constituents():
            detail = self.get_basket_detail(int(basket["basket_id"]))
            items.append(
                {
                    "id": f"basket-{basket['basket_id']}",
                    "kind": "basket",
                    "display_name": basket["name"],
                    "symbol": None,
                    "risk_metrics": detail["risk_metrics"],
                    "latest_forecast": None,
                    "latest_close": detail["price_history"][-1]["close"] if detail["price_history"] else None,
                }
            )
        recent_simulations = self.repository.list_recent_simulations(limit=10)
        return {
            "knowledge_base": knowledge_base,
            "knowledge_version": version,
            "summary": summary,
            "items": items,
            "recent_simulations": recent_simulations,
        }

    def get_macro_geopolitics(self) -> dict[str, Any]:
        return {
            "indicators": self.repository.list_macro_indicators(),
            "commodities": self.repository.list_commodities(),
            "prediction_markets": self.repository.list_prediction_markets(),
        }

    def get_alerts(self) -> dict[str, Any]:
        items = [
            item
            for item in self.repository.list_alert_feed(limit=100)
            if self._should_surface_alert(item)
        ]
        return {
            "items": items[:50],
            "system_status": self.repository.get_system_status(),
        }

    def get_diagnostics(self) -> dict[str, Any]:
        from audits.diagnostics import run_backend_diagnostics

        return run_backend_diagnostics(self.repository.settings)

    def run_manual_audit(self, lookback: int = 252) -> dict[str, Any]:
        from audits.daily_audit import run_daily_audit

        results = run_daily_audit(settings=self.repository.settings, lookback=lookback)
        warning_count = sum(1 for item in results if item.get("status") != "ok")
        self.repository.create_alert(
            f"Manual audit completed with {warning_count} warnings.",
            level="warning" if warning_count else "info",
            symbol="SYSTEM",
        )
        return {"items": results}

    def recent_simulations(self) -> dict[str, Any]:
        self._resolve_due_simulations(limit=40)
        items = [self._enrich_simulation_record(item) for item in self.repository.list_recent_simulations(limit=20)]
        return {"items": items}

    def delete_simulation(self, simulation_id: int) -> dict[str, Any]:
        simulation = self.repository.get_simulation(simulation_id)
        if simulation is None:
            raise KeyError(f"Unknown simulation_id {simulation_id}.")
        self.repository.delete_simulation(simulation_id)
        return {"deleted": True, "simulation_id": simulation_id}

    def simulation_options(self) -> dict[str, Any]:
        return {
            "stocks": self.repository.list_tracked_stocks(limit=50),
            "baskets": self.repository.list_baskets_with_constituents(),
        }

    def run_simulation(
        self,
        *,
        asset_kind: str,
        asset_identifier: str,
        simulation_type: str = "past",
        horizon_unit: str = "weekly",
        model_name: str = "updated_working_model",
        initial_capital: float = 10000.0,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        start_value = start_date or datetime.now(timezone.utc).date().isoformat()
        end_value = end_date or (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
        simulation_type = "future" if simulation_type == "future" else "past"
        config = self._simulation_config(
            asset_kind=asset_kind,
            asset_identifier=asset_identifier,
            horizon_unit=horizon_unit,
            model_name=model_name,
            initial_capital=initial_capital,
            start_date=start_value,
            end_date=end_value,
        )
        model_specs = self._simulation_model_specs(horizon_unit=horizon_unit, simulation_type=simulation_type)
        try:
            result = self.simulator.run_comparative_simulation(
                config=config,
                simulation_type=simulation_type,
                asset_kind=asset_kind,
                asset_identifier=asset_identifier,
                model_specs=model_specs,
            )
        except DependencyUnavailableError:
            fallback_specs = self._simulation_model_specs(
                horizon_unit=horizon_unit,
                simulation_type=simulation_type,
                force_fallback=True,
            )
            result = self.simulator.run_comparative_simulation(
                config=config,
                simulation_type=simulation_type,
                asset_kind=asset_kind,
                asset_identifier=asset_identifier,
                model_specs=fallback_specs,
            )
            model_specs = fallback_specs
        analysis = self._build_simulation_analysis(
            result=result,
            model_specs=model_specs,
        )
        stored = self.repository.get_simulation(int(result["simulation_id"]))
        if stored is not None:
            details = stored.get("details") or {}
            details["ai_analysis"] = analysis
            details["model_descriptions"] = [self._model_description(spec) for spec in model_specs]
            self.repository.update_simulation(
                stored["sim_id"],
                predicted_return=stored.get("predicted_return"),
                actual_return=stored.get("actual_return"),
                rmse=stored.get("rmse"),
                mape=stored.get("mape"),
                directional_accuracy=stored.get("directional_accuracy"),
                details=details,
            )
            stored = self.repository.get_simulation(stored["sim_id"])
        self.repository.create_alert(
            f"{simulation_type.capitalize()} simulation prepared for {config.portfolio_name} across Truth Model, Working Model, and Updated Working Model.",
            level="info",
            symbol="SYSTEM",
        )
        if stored is None:
            return {**result, "ai_analysis": analysis}
        enriched = self._enrich_simulation_record(stored)
        enriched["ai_analysis"] = analysis
        return enriched

    def format_metric(self, metric_key: str | None, value: Any) -> str:
        if value is None:
            return "n/a"
        if metric_key in {"volatility", "correlation", "covariance", "beta", "sharpe", "sortino"}:
            return f"{float(value):.3f}"
        if metric_key in {"value_at_risk", "conditional_value_at_risk", "max_drawdown"}:
            return self.format_percent(value)
        return str(value)

    def _should_surface_alert(self, item: dict[str, Any]) -> bool:
        message = str(item.get("message") or "")
        if "Premium Query Parameter" in message:
            return False
        if "Insufficient price history for TEST." in message:
            return False
        if message == "No symbols available for audit.":
            return False
        return True

    def format_percent(self, value: Any) -> str:
        if value is None:
            return "n/a"
        return f"{float(value) * 100:.2f}%"

    def format_currency(self, value: Any) -> str:
        if value is None:
            return "n/a"
        return f"${float(value):,.2f}"

    def _knowledge_context(self, knowledge_base: str) -> tuple[str, str]:
        if knowledge_base == "truth":
            return ("truth-v1", "Authoritative formulas and definitions from truth_db.")
        active_version = self.knowledge_manager.get_active_version("daily")
        recent_outcomes = self.knowledge_manager.list_recent_outcomes("daily", limit=25)
        if not recent_outcomes:
            return (active_version, "Adaptive working model with no recent learning outcomes yet.")
        mean_mape = [
            float(item["mape"])
            for item in recent_outcomes
            if item.get("mape") is not None
        ]
        summary = (
            f"Adaptive working model {active_version} with "
            f"{len(recent_outcomes)} recent outcomes; "
            f"mean MAPE={sum(mean_mape) / len(mean_mape):.4f}."
            if mean_mape
            else f"Adaptive working model {active_version} with {len(recent_outcomes)} recent outcomes."
        )
        return (active_version, summary)

    def _simulation_model_specs(
        self,
        *,
        horizon_unit: str,
        simulation_type: str,
        force_fallback: bool = False,
    ) -> list[SimulationModelSpec]:
        working_version = self.knowledge_manager.get_active_version(horizon_unit)
        truth_model = "naive" if force_fallback else "naive"
        working_model = "naive" if force_fallback else "arima"
        specs = [
            SimulationModelSpec(
                semantic_key="truth_model",
                display_name="Truth Model",
                forecast_model=truth_model,
                version_id="truth-v1",
                explanation=(
                    "Static reference model anchored to the fixed knowledge base. "
                    "It keeps the logic stable and does not learn from simulation outcomes."
                ),
            ),
            SimulationModelSpec(
                semantic_key="working_model",
                display_name="Working Model",
                forecast_model=working_model,
                version_id=working_version,
                explanation=(
                    "Active adaptive model that follows the working knowledge base. "
                    "It is dynamic, but less aggressive than the newest updated working state."
                ),
            ),
        ]
        if simulation_type == "future":
            updated_version = self.knowledge_manager.get_active_version(horizon_unit)
            updated_model = "naive" if force_fallback else self._choose_updated_working_model(horizon_unit)
            specs.append(
                SimulationModelSpec(
                    semantic_key="updated_working_model",
                    display_name="Updated Working Model",
                    forecast_model=updated_model,
                    version_id=updated_version,
                    explanation=(
                        "Latest iteratively improved working model. It is refreshed through recent simulation outcomes, "
                        "new market data, and model-performance comparisons."
                    ),
                )
            )
        return specs

    def _choose_updated_working_model(self, horizon_unit: str) -> str:
        recent_outcomes = self.knowledge_manager.list_recent_outcomes(horizon_unit, limit=200)
        if not recent_outcomes:
            return "prophet"
        rollups: dict[str, list[float]] = {}
        for item in recent_outcomes:
            model_key = str(item.get("model_key") or "").lower()
            mape_value = item.get("mape")
            if not model_key or mape_value is None:
                continue
            rollups.setdefault(model_key, []).append(float(mape_value))
        if not rollups:
            return "prophet"
        best_model = min(rollups.items(), key=lambda entry: sum(entry[1]) / len(entry[1]))[0]
        if best_model == "baseline":
            return "naive"
        return best_model

    def _build_simulation_analysis(
        self,
        *,
        result: dict[str, Any],
        model_specs: list[SimulationModelSpec],
    ) -> str:
        model_descriptions = [self._model_description(spec) for spec in model_specs]
        best_model = result.get("best_model")
        fallback = self._fallback_simulation_analysis(result=result, model_descriptions=model_descriptions)
        try:
            reply = self.llm_client.generate_reply(
                user_message="Explain this investment simulation in plain language.",
                language="english",
                intent_name="simulation_analysis",
                structured_response={
                    "simulation": result,
                    "models": model_descriptions,
                    "guardrails": "Educational analysis only. No personalized financial advice.",
                },
            )
            if reply:
                return reply
        except OpenAIChatError:
            pass
        if best_model:
            return fallback
        return fallback

    def _fallback_simulation_analysis(
        self,
        *,
        result: dict[str, Any],
        model_descriptions: list[dict[str, Any]],
    ) -> str:
        status = result.get("status")
        models = result.get("models") or []
        if status != "completed":
            updated = next((item for item in models if item.get("model_key") == "updated_working_model"), None)
            if updated is None:
                return "This future simulation has been stored and is waiting for actual market data before the models can be judged."
            return (
                f"This future simulation is waiting for actual market data. The Updated Working Model currently projects "
                f"{updated.get('predicted_return', 0.0):.2%} from an initial investment of {self.format_currency(result.get('initial_investment'))}. "
                "When the end date arrives, the backend will compare all three models, explain what happened, and feed the lesson into the updated working state."
            )
        ranked = sorted(
            [item for item in models if item.get("absolute_error") is not None],
            key=lambda item: item.get("absolute_error", float("inf")),
        )
        if not ranked:
            return "The run completed, but there was not enough comparable outcome data to rank the models."
        best = ranked[0]
        worst = ranked[-1]
        return (
            f"This run compared the Truth Model, Working Model, and Updated Working Model over the same window. "
            f"{best['display_name']} performed best with predicted ending value {self.format_currency(best.get('predicted_ending_value'))} "
            f"versus actual ending value {self.format_currency(best.get('actual_ending_value'))}. "
            f"{worst['display_name']} diverged the most. The system records this ranking, reviews the error, and uses the completed run to improve the Updated Working Model while keeping the Truth Model fixed."
        )

    def _model_description(self, spec: SimulationModelSpec) -> dict[str, Any]:
        comparison = {
            "truth_model": "It differs from the other two because it stays fixed and acts as the reference anchor.",
            "working_model": "It differs from the Truth Model because it adapts, and from the Updated Working Model because it is not the newest iteratively refined state.",
            "updated_working_model": "It differs from the other two because it uses the most current learned version and is the main vehicle for iterative improvement.",
        }
        strengths = {
            "truth_model": "Best for consistency, auditability, and understanding the fixed logic.",
            "working_model": "Best for active simulations that should reflect the current adaptive framework.",
            "updated_working_model": "Best for the freshest predictive logic and learning from recent results.",
        }
        limitations = {
            "truth_model": "It can lag behind new market regimes because it does not learn from simulations.",
            "working_model": "It may still under-react if the newest evidence has not yet been folded into its active version.",
            "updated_working_model": "It can change over time, so it needs version tracking and careful interpretation.",
        }
        return {
            "model_key": spec.semantic_key,
            "display_name": spec.display_name,
            "version_id": spec.version_id,
            "forecast_model": spec.forecast_model,
            "plain_language_explanation": spec.explanation,
            "relies_on": "Historical prices, basket composition, configured horizon, and the backend forecasting engine.",
            "good_at": strengths[spec.semantic_key],
            "limitations": limitations[spec.semantic_key],
            "comparison_note": comparison[spec.semantic_key],
        }

    def _resolve_due_simulations(self, limit: int = 40) -> None:
        simulations = self.repository.list_recent_simulations(limit=limit)
        for simulation in simulations:
            details = simulation.get("details") or {}
            if details.get("simulation_type") != "future":
                continue
            if details.get("status") != "awaiting_actual_data":
                continue
            positions = self._positions_for_saved_simulation(simulation)
            if not positions:
                continue
            resolved = self.simulator.resolve_future_simulation(
                simulation,
                asset_kind=details.get("asset_kind", "stock"),
                asset_identifier=str(details.get("asset_identifier", simulation.get("portfolio_name") or "")),
                positions=positions,
            )
            if resolved is None:
                continue
            resolved_details = resolved.get("details") or {}
            if resolved_details.get("status") == "completed" and not resolved_details.get("ai_analysis"):
                analysis = self._build_simulation_analysis(
                    result=self._enrich_simulation_record(resolved),
                    model_specs=self._simulation_model_specs(
                        horizon_unit=resolved["horizon_unit"],
                        simulation_type="future",
                        force_fallback=True,
                    ),
                )
                resolved_details["ai_analysis"] = analysis
                self.repository.update_simulation(
                    resolved["sim_id"],
                    predicted_return=resolved.get("predicted_return"),
                    actual_return=resolved.get("actual_return"),
                    rmse=resolved.get("rmse"),
                    mape=resolved.get("mape"),
                    directional_accuracy=resolved.get("directional_accuracy"),
                    details=resolved_details,
                )

    def _positions_for_saved_simulation(self, simulation: dict[str, Any]) -> list[PortfolioPosition]:
        details = simulation.get("details") or {}
        asset_kind = details.get("asset_kind")
        asset_identifier = str(details.get("asset_identifier") or "")
        if asset_kind == "basket":
            basket = self.repository.get_basket(int(asset_identifier))
            if basket is None:
                return []
            return [
                PortfolioPosition(symbol=item["symbol"], weight=float(item["weight"]))
                for item in basket["constituents"]
            ]
        if not asset_identifier:
            asset_identifier = str(simulation.get("portfolio_name") or "")
        if not asset_identifier:
            return []
        return [PortfolioPosition(symbol=asset_identifier.upper(), weight=1.0)]

    def _enrich_simulation_record(self, simulation: dict[str, Any]) -> dict[str, Any]:
        details = simulation.get("details") or {}
        models = list(details.get("model_results") or [])
        if not models:
            models = self._legacy_model_results(simulation)
            if models and "model_results" not in details:
                details["model_results"] = models
        models_used = details.get("models_used") or [item.get("display_name") for item in models if item.get("display_name")]
        simulation_type = details.get("simulation_type")
        if not simulation_type:
            simulation_type = "past" if simulation.get("actual_return") is not None else "future"
        status = details.get("status")
        if not status:
            status = "completed" if simulation.get("actual_return") is not None else "awaiting_actual_data"
        ai_analysis = details.get("ai_analysis")
        if not ai_analysis and models:
            ai_analysis = self._fallback_simulation_analysis(
                result={
                    "status": status,
                    "models": models,
                    "initial_investment": simulation.get("initial_capital"),
                },
                model_descriptions=[],
            )
        key_outcome_summary = details.get("key_outcome_summary")
        if not key_outcome_summary and models:
            key_outcome_summary = (
                _safe_summary_from_models(models, status=status)
                if status == "completed"
                else "Predictions are stored and waiting for end-of-period market data."
            )
        return {
            **simulation,
            "simulation_type": simulation_type,
            "status": status,
            "models_used": models_used,
            "ai_analysis": ai_analysis,
            "key_outcome_summary": key_outcome_summary,
            "best_model": details.get("best_model"),
            "model_results": models,
            "models_count": len(models_used or models),
            "asset_kind": details.get("asset_kind"),
            "asset_identifier": details.get("asset_identifier"),
        }

    def _legacy_model_results(self, simulation: dict[str, Any]) -> list[dict[str, Any]]:
        result_rows = self.repository.list_simulation_results(int(simulation["sim_id"]))
        if not result_rows:
            return []
        initial = float(simulation.get("initial_capital") or 0.0)
        ranked = sorted(result_rows, key=lambda item: item.get("absolute_error") if item.get("absolute_error") is not None else float("inf"))
        rank_map = {item["model"]: index for index, item in enumerate(ranked, start=1)}
        return [
            {
                "model_key": _semantic_model_key_from_name(row["model"]),
                "display_name": _display_model_name(row["model"]),
                "forecast_model": row["model"],
                "version_id": None,
                "explanation": "Legacy run reconstructed from stored simulation results.",
                "predicted_return": row.get("predicted_value"),
                "actual_return": row.get("actual_value"),
                "predicted_ending_value": initial * (1 + float(row["predicted_value"])) if row.get("predicted_value") is not None else None,
                "actual_ending_value": initial * (1 + float(row["actual_value"])) if row.get("actual_value") is not None else None,
                "predicted_gain_loss": initial * float(row["predicted_value"]) if row.get("predicted_value") is not None else None,
                "actual_gain_loss": initial * float(row["actual_value"]) if row.get("actual_value") is not None else None,
                "absolute_error": row.get("absolute_error"),
                "percentage_error": row.get("percentage_error"),
                "directional_accuracy": None,
                "status": "completed" if row.get("actual_value") is not None else "awaiting_actual_data",
                "rank": rank_map.get(row["model"]),
                "latest_updated_working_version": None,
                "component_predictions": {},
                "component_actuals": {},
            }
            for row in result_rows
        ]

    def _simulation_config(
        self,
        *,
        asset_kind: str,
        asset_identifier: str,
        horizon_unit: str,
        model_name: str,
        initial_capital: float,
        start_date: str,
        end_date: str,
    ) -> SimulationConfig:
        if asset_kind == "basket":
            basket = self.repository.get_basket(int(asset_identifier))
            if basket is None:
                raise KeyError(f"Unknown basket_id {asset_identifier}.")
            positions = [
                PortfolioPosition(symbol=item["symbol"], weight=float(item["weight"]))
                for item in basket["constituents"]
            ]
            return SimulationConfig(
                portfolio_name=str(basket["name"]),
                positions=positions,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                horizon=1,
                horizon_unit=horizon_unit,
                model_name=model_name,
                basket_id=int(asset_identifier),
            )
        symbol = asset_identifier.upper()
        return SimulationConfig(
            portfolio_name=symbol,
            positions=[PortfolioPosition(symbol=symbol, weight=1.0)],
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            horizon=1,
            horizon_unit=horizon_unit,
            model_name=model_name,
        )

    def _risk_metrics_from_closes(self, closes: list[float]) -> dict[str, Any] | None:
        if len(closes) < 3:
            return None
        try:
            report = build_risk_report(closes, lookback=min(252, len(closes)))
            return _risk_report_to_dict(report)
        except RiskComputationError:
            returns = compute_returns(closes, lookback=min(252, len(closes)))
            return {
                "volatility": _safe_metric(lambda: volatility(returns)),
                "covariance": None,
                "correlation": None,
                "sharpe": _safe_metric(lambda: sharpe_ratio(returns)),
                "sortino": _safe_metric(lambda: sortino_ratio(returns)),
                "beta": None,
                "var_parametric": _safe_metric(lambda: value_at_risk_parametric(returns)),
                "var_historical": _safe_metric(lambda: value_at_risk_historical(returns)),
                "var_monte_carlo": _safe_metric(lambda: value_at_risk_monte_carlo(returns)),
                "cvar": _safe_metric(lambda: conditional_value_at_risk(returns)),
                "max_drawdown": _safe_metric(lambda: maximum_drawdown(closes)),
            }

    def _build_basket_history(self, constituents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not constituents:
            return []
        per_symbol: dict[str, dict[str, float]] = {}
        weights: dict[str, float] = {}
        all_dates: set[str] = set()
        for constituent in constituents:
            symbol = constituent["symbol"]
            weights[symbol] = float(constituent["weight"])
            series = self.repository.get_price_series(symbol)
            if not series:
                continue
            closes = {row["trading_date"]: float(row["close"]) for row in series if row.get("close") is not None}
            if not closes:
                continue
            per_symbol[symbol] = closes
            all_dates.update(closes)
        if not per_symbol:
            return []
        baseline = {symbol: next(iter(series.values())) for symbol, series in per_symbol.items()}
        history: list[dict[str, Any]] = []
        for trading_date in sorted(all_dates):
            basket_value = 0.0
            included = 0
            for symbol, closes in per_symbol.items():
                if trading_date not in closes:
                    continue
                base = baseline[symbol]
                if base == 0:
                    continue
                basket_value += weights[symbol] * (closes[trading_date] / base)
                included += 1
            if included:
                history.append(
                    {
                        "trading_date": trading_date,
                        "timestamp_utc": f"{trading_date}T00:00:00+00:00",
                        "close": basket_value * 100.0,
                    }
                )
        return history


def _display_model_name(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in {"truth_model", "truth model", "naive", "baseline"}:
        return "Truth Model"
    if text in {"working_model", "working model", "arima"}:
        return "Working Model"
    if text in {"updated_working_model", "updated working model", "prophet"}:
        return "Updated Working Model"
    return value or "Model"


def _semantic_model_key_from_name(value: str | None) -> str:
    display = _display_model_name(value)
    if display == "Truth Model":
        return "truth_model"
    if display == "Working Model":
        return "working_model"
    if display == "Updated Working Model":
        return "updated_working_model"
    return "working_model"


def _safe_summary_from_models(models: list[dict[str, Any]], *, status: str) -> str:
    if status != "completed":
        return "Predictions are stored and waiting for end-of-period market data."
    ranked = sorted(models, key=lambda item: item.get("absolute_error") if item.get("absolute_error") is not None else float("inf"))
    if not ranked:
        return "No summary available."
    best = ranked[0]
    predicted = float(best.get("predicted_return") or 0.0)
    actual = float(best.get("actual_return") or 0.0)
    return f"{best.get('display_name', 'Model')} performed best with predicted {predicted:.2%} versus actual {actual:.2%}."


def _risk_report_to_dict(report: RiskReport) -> dict[str, Any]:
    return {
        "volatility": report.volatility,
        "sharpe": report.sharpe,
        "sortino": report.sortino,
        "beta": report.beta,
        "var_parametric": report.var_parametric,
        "var_historical": report.var_historical,
        "var_monte_carlo": report.var_monte_carlo,
        "cvar": report.cvar,
        "max_drawdown": report.max_drawdown,
        "covariance": report.covariance,
        "correlation": report.correlation,
    }


def _safe_change(previous: Any, current: Any) -> float | None:
    if previous in (None, 0) or current is None:
        return None
    return (float(current) / float(previous)) - 1.0


def _safe_metric(func: Any) -> float | None:
    try:
        value = func()
    except RiskComputationError:
        return None
    return float(value) if value is not None else None
