"""Daily audit and anomaly checks."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.risk import RiskComputationError, build_risk_report
from config import Settings, get_settings
from db import MarketRepository


def run_daily_audit(settings: Settings | None = None, lookback: int = 252) -> list[dict]:
    active_settings = settings or get_settings()
    repository = MarketRepository(active_settings)
    symbols = repository.latest_stock_symbols()
    audit_results: list[dict] = []
    today = datetime.now(timezone.utc).date().isoformat()
    for symbol in symbols:
        try:
            records = repository.get_price_series(symbol)
            closes = [float(record["close"]) for record in records if record.get("close") is not None]
            if len(closes) < 3:
                repository.log_audit("daily_audit", "warning", f"Insufficient price history for {symbol}.")
                continue
            risk_report = build_risk_report(closes, lookback=min(lookback, len(closes)))
            repository.save_risk_metrics(
                {
                    "symbol": symbol,
                    "basket_id": None,
                    "benchmark_symbol": None,
                    "calculation_date": today,
                    "lookback_window": min(lookback, len(closes)),
                    "confidence_level": 0.95,
                    "volatility": risk_report.volatility,
                    "covariance": risk_report.covariance,
                    "correlation": risk_report.correlation,
                    "sharpe": risk_report.sharpe,
                    "sortino": risk_report.sortino,
                    "beta": risk_report.beta,
                    "var_parametric": risk_report.var_parametric,
                    "var_historical": risk_report.var_historical,
                    "var_monte_carlo": risk_report.var_monte_carlo,
                    "cvar": risk_report.cvar,
                    "max_drawdown": risk_report.max_drawdown,
                }
            )
            audit_results.append({"symbol": symbol, "status": "ok", "volatility": risk_report.volatility})
        except RiskComputationError as exc:
            repository.log_audit("daily_audit", "warning", f"Risk calculation skipped for {symbol}: {exc}")
            audit_results.append({"symbol": symbol, "status": "warning", "message": str(exc)})
    if not audit_results:
        repository.log_audit("daily_audit", "info", "No symbols available for audit.")
    return audit_results
