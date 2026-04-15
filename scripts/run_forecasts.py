"""CLI for portfolio forecast simulations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings
from db import KnowledgeBaseManager, MarketRepository, initialize_knowledge_bases, initialize_market_database
from analytics.forecasting import DependencyUnavailableError
from simulations.simulator import PortfolioPosition, PortfolioSimulator, SimulationConfig


def _parse_positions(raw_positions: list[str]) -> list[PortfolioPosition]:
    positions: list[PortfolioPosition] = []
    for raw in raw_positions:
        symbol, weight = raw.split(":", 1)
        positions.append(PortfolioPosition(symbol=symbol.upper(), weight=float(weight)))
    return positions


def main() -> None:
    parser = argparse.ArgumentParser(description="Run forecast-vs-actual portfolio simulations.")
    parser.add_argument("--name", default="CLI Portfolio", help="Portfolio name.")
    parser.add_argument("--positions", nargs="+", required=True, help="Position specs like AAPL:0.5 MSFT:0.5")
    parser.add_argument("--start-date", required=True, help="Simulation start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Simulation end date, YYYY-MM-DD.")
    parser.add_argument("--initial-capital", type=float, default=10000.0, help="Initial capital.")
    parser.add_argument(
        "--model",
        default="baseline",
        choices=["baseline", "arima", "garch", "prophet"],
        help="Forecasting model.",
    )
    parser.add_argument("--horizon", type=int, default=1, help="Forecast horizon count.")
    parser.add_argument(
        "--horizon-unit",
        default="daily",
        choices=["daily", "weekly", "monthly"],
        help="Forecast horizon unit.",
    )
    args = parser.parse_args()
    settings = get_settings()
    initialize_market_database(settings)
    initialize_knowledge_bases(settings)
    simulator = PortfolioSimulator(MarketRepository(settings), KnowledgeBaseManager(settings))
    config = SimulationConfig(
        portfolio_name=args.name,
        positions=_parse_positions(args.positions),
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        horizon=args.horizon,
        horizon_unit=args.horizon_unit,
        model_name=args.model,
    )
    try:
        result = simulator.run_forecast_simulation(config)
    except DependencyUnavailableError as exc:
        if args.model == "baseline":
            raise
        print(f"Requested model '{args.model}' is unavailable ({exc}); retrying with baseline.")
        config.model_name = "baseline"
        result = simulator.run_forecast_simulation(config)
    print(result)


if __name__ == "__main__":
    main()
