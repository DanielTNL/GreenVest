"""Backend diagnostics and readiness checks."""

from __future__ import annotations

import importlib.util
import warnings
from typing import Any

from analytics.forecasting import DependencyUnavailableError, generate_forecast
from analytics.risk import RiskComputationError, build_risk_report
from config import Settings, get_settings
from db import KnowledgeBaseManager, MarketRepository, initialize_knowledge_bases, initialize_market_database


def run_backend_diagnostics(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    initialize_market_database(active_settings)
    initialize_knowledge_bases(active_settings)
    repository = MarketRepository(active_settings)
    knowledge_manager = KnowledgeBaseManager(active_settings)

    dependencies = _dependency_status()
    api_keys = _api_key_status(active_settings)
    econometrics = _econometric_status()
    geopolitical = _geopolitical_status(active_settings, repository)
    assistant = _assistant_status(active_settings)
    system_status = repository.get_system_status()

    return {
        "environment": {
            "project_root": str(active_settings.project_root),
            "database_path": str(active_settings.database_path),
            "truth_db_path": str(active_settings.truth_db_path),
            "working_db_path": str(active_settings.working_db_path),
        },
        "api_keys": api_keys,
        "dependencies": dependencies,
        "econometrics": econometrics,
        "assistant": assistant,
        "databases": {
            "market_db_exists": active_settings.database_path.exists(),
            "truth_db_exists": active_settings.truth_db_path.exists(),
            "working_db_exists": active_settings.working_db_path.exists(),
            "system_status": system_status,
            "working_versions": {
                period: knowledge_manager.get_active_version(period)
                for period in ("daily", "weekly", "monthly")
            },
        },
        "geopolitical": geopolitical,
        "readiness": _readiness_status(api_keys, econometrics, geopolitical, assistant, system_status),
        "recommendations": _recommendations(api_keys, dependencies, econometrics, geopolitical, assistant, system_status),
    }


def _api_key_status(settings: Settings) -> dict[str, dict[str, Any]]:
    return {
        "alpha_vantage": {
            "env_var": "ALPHAVANTAGE_API_KEY",
            "configured": bool(settings.alpha_vantage_api_key),
            "required_for": ["daily_equity_prices", "intraday_equity_prices"],
        },
        "fmp": {
            "env_var": "FMP_API_KEY",
            "configured": bool(settings.fmp_api_key),
            "required_for": ["daily_equity_prices", "intraday_equity_prices", "commodity_prices"],
        },
        "eodhd": {
            "env_var": "EODHD_API_KEY",
            "configured": bool(settings.eodhd_api_key),
            "required_for": ["commodity_prices"],
        },
        "fred": {
            "env_var": "FRED_API_KEY",
            "configured": bool(settings.fred_api_key),
            "required_for": ["macro_indicators", "geopolitical_series_if_configured"],
        },
        "openai": {
            "env_var": "OPENAI_API_KEY",
            "configured": bool(settings.openai_api_key),
            "required_for": ["assistant_ai_responses"],
        },
        "polymarket": {
            "env_var": None,
            "configured": True,
            "required_for": ["prediction_market_odds"],
        },
    }


def _dependency_status() -> dict[str, dict[str, Any]]:
    return {
        "requests": _package_status("requests"),
        "apscheduler": _package_status("apscheduler"),
        "statsmodels": _package_status("statsmodels"),
        "arch": _package_status("arch"),
        "prophet": _package_status("prophet"),
        "pandas": _package_status("pandas"),
    }


def _econometric_status() -> dict[str, Any]:
    prices = [100.0, 101.5, 100.9, 103.2, 102.6, 104.8, 105.1, 104.3, 106.2, 107.0]
    benchmark = [100.0, 101.0, 100.7, 102.4, 102.0, 103.8, 104.1, 103.7, 105.0, 105.8]
    returns = [0.01, -0.005, 0.007, 0.011, -0.002, 0.009, 0.004, -0.003, 0.006, 0.008, 0.004, 0.005]
    risk_status: dict[str, Any]
    try:
        report = build_risk_report(prices, benchmark_prices=benchmark, lookback=len(prices))
        risk_status = {
            "operational": True,
            "volatility": report.volatility,
            "sharpe": report.sharpe,
            "sortino": report.sortino,
            "beta": report.beta,
            "var_historical": report.var_historical,
        }
    except RiskComputationError as exc:
        risk_status = {"operational": False, "error": str(exc)}

    models: dict[str, dict[str, Any]] = {"baseline": _forecast_model_check("baseline", returns)}
    models["arima"] = _forecast_model_check(
        "arima",
        returns,
        exogenous={"macro": [0.1] * len(returns)},
    )
    models["garch"] = _forecast_model_check("garch", returns)
    models["prophet"] = _forecast_model_check(
        "prophet",
        returns,
        dates=[f"2026-01-{index + 1:02d}" for index in range(len(returns))],
        exogenous={"macro": [0.1] * len(returns)},
    )
    advanced_model_names = ("arima", "garch", "prophet")
    warning_messages = sorted(
        {
            warning
            for name in advanced_model_names
            for warning in models[name].get("warnings", [])
        }
    )
    return {
        "risk_engine": risk_status,
        "forecast_models": models,
        "advanced_model_names": list(advanced_model_names),
        "advanced_models_ready": all(
            models[name].get("operational") and not models[name].get("warnings")
            for name in advanced_model_names
        ),
        "warning_messages": warning_messages,
    }


def _forecast_model_check(
    model_name: str,
    series: list[float],
    *,
    dates: list[str] | None = None,
    exogenous: Any = None,
) -> dict[str, Any]:
    try:
        if exogenous is not None:
            exogenous_future = {"macro": [0.1, 0.1]} if isinstance(exogenous, dict) else None
        else:
            exogenous_future = None
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            result = generate_forecast(
                model_name,
                series,
                horizon=2,
                dates=dates,
                exogenous=exogenous,
                exogenous_future=exogenous_future,
            )
        warning_messages = sorted(
            {
                str(item.message).strip()
                for item in caught_warnings
                if str(item.message).strip()
            }
        )
        return {
            "operational": True,
            "prediction_count": len(result.predictions),
            "supports_exogenous": bool(exogenous is not None),
            "readiness": "warning" if warning_messages else "ok",
            "warning_count": len(warning_messages),
            "warnings": warning_messages,
        }
    except DependencyUnavailableError as exc:
        return {
            "operational": False,
            "reason": "dependency_unavailable",
            "error": str(exc),
            "readiness": "blocked",
            "warning_count": 0,
            "warnings": [],
        }
    except Exception as exc:
        return {
            "operational": False,
            "reason": "runtime_error",
            "error": str(exc),
            "readiness": "blocked",
            "warning_count": 0,
            "warnings": [],
        }


def _geopolitical_status(settings: Settings, repository: MarketRepository) -> dict[str, Any]:
    configured = bool(settings.geopolitical_risk_series_id)
    indicator = (
        repository.get_macro_indicator_by_name(settings.geopolitical_risk_series_name)
        if configured
        else None
    )
    prediction_markets = repository.list_prediction_markets(limit=10)
    return {
        "fred_series_configured": configured,
        "fred_series_name": settings.geopolitical_risk_series_name,
        "fred_series_id": settings.geopolitical_risk_series_id,
        "fred_api_key_configured": bool(settings.fred_api_key),
        "fred_indicator_ingested": indicator is not None,
        "latest_fred_observation": indicator.get("latest_observation") if indicator else None,
        "prediction_market_feed_operational": len(prediction_markets) > 0,
        "prediction_market_records": len(prediction_markets),
    }


def _assistant_status(settings: Settings) -> dict[str, Any]:
    return {
        "mode": "openai" if settings.openai_api_key else "rules_only",
        "openai_configured": bool(settings.openai_api_key),
        "openai_model": settings.openai_model if settings.openai_api_key else None,
    }


def _readiness_status(
    api_keys: dict[str, dict[str, Any]],
    econometrics: dict[str, Any],
    geopolitical: dict[str, Any],
    assistant: dict[str, Any],
    system_status: dict[str, Any],
) -> dict[str, Any]:
    required_provider_keys = ("alpha_vantage", "fmp", "eodhd", "fred")
    cloud_deploy_ready = all(api_keys[name]["configured"] for name in required_provider_keys)
    risk_engine_ready = bool(econometrics["risk_engine"].get("operational"))
    advanced_models_ready = bool(econometrics.get("advanced_models_ready"))
    geopolitical_ready = bool(geopolitical["prediction_market_feed_operational"]) and (
        not geopolitical["fred_series_configured"] or geopolitical["fred_indicator_ingested"]
    )

    warnings_list: list[str] = []
    blocking_issues: list[str] = []

    if econometrics.get("warning_messages"):
        warnings_list.extend(
            f"Forecast model warning: {message}" for message in econometrics["warning_messages"]
        )
    if not assistant["openai_configured"]:
        warnings_list.append("OPENAI_API_KEY is not configured; assistant responses will remain rules-only.")
    if system_status["stock_count"] == 0:
        warnings_list.append("No tracked stocks are stored yet; the app will show sparse dashboards until ETL runs.")
    if not geopolitical["prediction_market_feed_operational"]:
        warnings_list.append("Polymarket prediction-market data has not been ingested yet.")

    if not cloud_deploy_ready:
        blocking_issues.append("One or more required provider API keys are missing.")
    if not risk_engine_ready:
        blocking_issues.append("The risk engine is not operational.")
    if not advanced_models_ready:
        warnings_list.append("Advanced forecasting models are not fully ready yet; baseline models remain available.")
    if geopolitical["fred_series_configured"] and not geopolitical["fred_indicator_ingested"]:
        warnings_list.append("A FRED geopolitical series is configured but has not been ingested yet.")

    return {
        "operational": not blocking_issues,
        "cloud_deploy_ready": cloud_deploy_ready,
        "risk_engine_ready": risk_engine_ready,
        "advanced_models_ready": advanced_models_ready,
        "assistant_ready": bool(assistant["openai_configured"]),
        "geopolitical_ready": geopolitical_ready,
        "warnings": warnings_list,
        "blocking_issues": blocking_issues,
    }


def _recommendations(
    api_keys: dict[str, dict[str, Any]],
    dependencies: dict[str, dict[str, Any]],
    econometrics: dict[str, Any],
    geopolitical: dict[str, Any],
    assistant: dict[str, Any],
    system_status: dict[str, Any],
) -> list[str]:
    recommendations: list[str] = []
    missing_keys = [
        name
        for name, status in api_keys.items()
        if status.get("env_var") and not status["configured"] and name != "openai"
    ]
    if missing_keys:
        recommendations.append(
            "Configure the missing provider API keys before expecting live ingestion: "
            + ", ".join(sorted(missing_keys))
            + "."
        )
    if not assistant["openai_configured"]:
        recommendations.append("Set OPENAI_API_KEY to enable model-backed chat instead of the rules-only assistant.")
    for package_name in ("statsmodels", "arch", "prophet", "pandas", "apscheduler"):
        if not dependencies[package_name]["installed"]:
            recommendations.append(f"Install optional dependency '{package_name}' to unlock the related backend feature set.")
    unavailable_models = [
        name
        for name, status in econometrics["forecast_models"].items()
        if not status["operational"] and name != "baseline"
    ]
    if unavailable_models:
        recommendations.append(
            "Advanced forecasting models are not fully operational on this machine yet: "
            + ", ".join(sorted(unavailable_models))
            + "."
        )
    if not geopolitical["fred_series_configured"]:
        recommendations.append(
            "Set GEOPOLITICAL_RISK_FRED_SERIES_ID to your preferred geopolitical-risk FRED series if you want a dedicated index beyond Polymarket."
        )
    elif geopolitical["fred_series_configured"] and not geopolitical["fred_indicator_ingested"]:
        recommendations.append(
            "Run ingestion after configuring FRED so the geopolitical risk series is stored and exposed to the app."
        )
    if system_status["stock_count"] == 0 or not system_status["last_stock_update_utc"]:
        recommendations.append("Run the ETL pipeline after configuring keys so the iOS app has actual market data to display.")
    return recommendations


def _package_status(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    return {"installed": spec is not None}
