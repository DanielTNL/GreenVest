"""APScheduler entrypoint for recurring ETL, risk, and simulation jobs."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import get_settings
from analytics.forecasting import DependencyUnavailableError
from audits.daily_audit import run_daily_audit
from assistant.discovery import StockDiscoveryService
from db import KnowledgeBaseManager, MarketRepository, initialize_knowledge_bases, initialize_market_database
from ingestion import DataIngestionPipeline
from simulations.simulator import PortfolioPosition, PortfolioSimulator, SimulationConfig


def _run_scheduled_simulations(
    simulator: PortfolioSimulator,
    repository: MarketRepository,
    *,
    horizon_unit: str,
) -> None:
    baskets = repository.list_baskets()
    if not baskets:
        repository.log_audit(
            "scheduler",
            "info",
            f"No baskets configured; skipping {horizon_unit} forecast simulation.",
        )
        return
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=730)).isoformat()
    for basket in baskets:
        positions = [
            PortfolioPosition(symbol=row["symbol"], weight=float(row["weight"]))
            for row in repository.get_basket_constituents(int(basket["basket_id"]))
        ]
        if not positions:
            repository.log_audit(
                "scheduler",
                "warning",
                f"Basket {basket['basket_id']} has no constituents; skipping scheduled simulation.",
            )
            continue
        config = SimulationConfig(
            portfolio_name=basket["name"],
            positions=positions,
            start_date=start_date,
            end_date=end_date,
            initial_capital=10000.0,
            horizon=1,
            horizon_unit=horizon_unit,
            model_name="baseline",
            basket_id=int(basket["basket_id"]),
        )
        try:
            simulator.run_forecast_simulation(config)
        except DependencyUnavailableError as exc:
            repository.log_audit(
                "scheduler",
                "warning",
                f"Scheduled {horizon_unit} simulation for basket {basket['name']} fell back due to model dependency issue: {exc}",
            )


def main() -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError as exc:
        raise SystemExit("APScheduler is not installed. Run `pip install -r requirements.txt`.") from exc
    settings = get_settings()
    initialize_market_database(settings)
    initialize_knowledge_bases(settings)
    pipeline = DataIngestionPipeline(settings)
    repository = MarketRepository(settings)
    simulator = PortfolioSimulator(repository, KnowledgeBaseManager(settings))
    discovery = StockDiscoveryService(settings, repository)
    scheduler = BlockingScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(lambda: pipeline.run_full_etl(include_intraday=False), trigger="cron", hour=0, minute=15)
    scheduler.add_job(lambda: pipeline.run_full_etl(include_intraday=True), trigger="cron", minute="*/15", day_of_week="mon-fri")
    scheduler.add_job(lambda: run_daily_audit(settings=settings), trigger="cron", hour=1, minute=0)
    scheduler.add_job(
        lambda: _run_scheduled_simulations(simulator, repository, horizon_unit="daily"),
        trigger="cron",
        hour=1,
        minute=30,
    )
    scheduler.add_job(
        lambda: _run_scheduled_simulations(simulator, repository, horizon_unit="weekly"),
        trigger="cron",
        day_of_week="mon",
        hour=2,
        minute=0,
    )
    scheduler.add_job(
        lambda: _run_scheduled_simulations(simulator, repository, horizon_unit="monthly"),
        trigger="cron",
        day=1,
        hour=3,
        minute=0,
    )
    scheduler.add_job(
        lambda: discovery.generate_daily_suggestions(limit=5),
        trigger="cron",
        hour=6,
        minute=30,
    )
    print("Scheduler started. Press Ctrl+C to stop.")
    scheduler.start()


if __name__ == "__main__":
    main()
