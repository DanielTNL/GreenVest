"""Tool-style router for connecting an assistant to backend functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from analytics.risk import build_risk_report
from audits.daily_audit import run_daily_audit
from db import KnowledgeBaseManager, MarketRepository
from ingestion import DataIngestionPipeline
from simulations.simulator import PortfolioPosition, PortfolioSimulator, SimulationConfig


class FunctionRouter:
    """Maps tool names to backend callables."""

    def __init__(self, pipeline: DataIngestionPipeline, repository: MarketRepository, knowledge_manager: KnowledgeBaseManager) -> None:
        self.pipeline = pipeline
        self.repository = repository
        self.knowledge_manager = knowledge_manager
        self.simulator = PortfolioSimulator(repository, knowledge_manager)
        self._routes: dict[str, Callable[..., Any]] = {
            "run_full_etl": self.pipeline.run_full_etl,
            "create_basket": self.repository.create_basket,
            "get_market_data": self._get_market_data,
            "calculate_risk_metrics": self._calculate_risk_metrics,
            "get_alert_feed": self.repository.list_alert_feed,
            "list_baskets": self.repository.list_baskets_with_constituents,
            "run_simulation": self._run_simulation,
            "predict_future_returns": self._run_simulation,
            "trigger_daily_audit": run_daily_audit,
            "run_forecast_simulation": self.simulator.run_forecast_simulation,
            "run_historical_backtest": self.simulator.run_historical_backtest,
        }

    def available_tools(self) -> list[str]:
        return sorted(self._routes)

    def dispatch(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name not in self._routes:
            raise KeyError(f"Unknown tool '{tool_name}'.")
        return self._routes[tool_name](**kwargs)

    def _get_market_data(self, symbol: str) -> dict[str, Any] | None:
        return self.repository.get_stock(symbol)

    def _calculate_risk_metrics(self, symbol: str, lookback: int = 252) -> dict[str, Any]:
        price_rows = self.repository.get_price_series(symbol)
        closes = [float(row["close"]) for row in price_rows if row.get("close") is not None]
        report = build_risk_report(closes, lookback=min(lookback, len(closes)))
        return {
            "symbol": symbol.upper(),
            "volatility": report.volatility,
            "sharpe": report.sharpe,
            "sortino": report.sortino,
            "beta": report.beta,
            "value_at_risk": report.var_historical,
            "max_drawdown": report.max_drawdown,
        }

    def _run_simulation(
        self,
        *,
        symbol: str | None = None,
        basket_id: int | None = None,
        horizon_unit: str = "weekly",
        model_name: str = "baseline",
        initial_capital: float = 10000.0,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        positions: list[PortfolioPosition] = []
        portfolio_name = symbol or "Portfolio"
        if basket_id is not None:
            basket = self.repository.get_basket(basket_id)
            if basket is None:
                raise KeyError(f"Unknown basket_id {basket_id}.")
            positions = [
                PortfolioPosition(symbol=item["symbol"], weight=float(item["weight"]))
                for item in basket["constituents"]
            ]
            portfolio_name = str(basket["name"])
        elif symbol is not None:
            positions = [PortfolioPosition(symbol=symbol.upper(), weight=1.0)]
        else:
            raise ValueError("Either symbol or basket_id must be supplied for simulations.")
        end_value = end_date or datetime.now(timezone.utc).date().isoformat()
        start_value = start_date or (datetime.now(timezone.utc).date() - timedelta(days=365)).isoformat()
        config = SimulationConfig(
            portfolio_name=portfolio_name,
            positions=positions,
            start_date=start_value,
            end_date=end_value,
            initial_capital=initial_capital,
            horizon=1,
            horizon_unit=horizon_unit,
            model_name=model_name,
            basket_id=basket_id,
        )
        return self.simulator.run_forecast_simulation(config)
