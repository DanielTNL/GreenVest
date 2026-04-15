"""Truth and working knowledge base management."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from config import Settings

from .connection import connect_sqlite


TRUTH_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS truth_versions (
        version_id TEXT PRIMARY KEY,
        label TEXT NOT NULL UNIQUE,
        created_at_utc TEXT NOT NULL,
        notes TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS metric_definitions (
        metric_key TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        formula TEXT NOT NULL,
        explanation TEXT,
        assumptions TEXT,
        truth_version_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY (truth_version_id) REFERENCES truth_versions(version_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS econometric_definitions (
        model_key TEXT PRIMARY KEY,
        model_name TEXT NOT NULL,
        description TEXT NOT NULL,
        assumptions TEXT,
        supports_exogenous INTEGER NOT NULL DEFAULT 0,
        truth_version_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY (truth_version_id) REFERENCES truth_versions(version_id)
    );
    """,
)


WORKING_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS working_versions (
        version_id TEXT PRIMARY KEY,
        parent_version_id TEXT,
        period TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        based_on_date TEXT,
        summary TEXT,
        metadata_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS model_parameters (
        model_key TEXT NOT NULL,
        symbol TEXT NOT NULL,
        period TEXT NOT NULL,
        version_id TEXT NOT NULL,
        parameter_name TEXT NOT NULL,
        parameter_value REAL,
        updated_at_utc TEXT NOT NULL,
        PRIMARY KEY (model_key, symbol, period, version_id, parameter_name),
        FOREIGN KEY (version_id) REFERENCES working_versions(version_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        model_key TEXT NOT NULL,
        period TEXT NOT NULL,
        prediction_timestamp_utc TEXT NOT NULL,
        target_timestamp_utc TEXT NOT NULL,
        predicted_value REAL,
        actual_value REAL,
        absolute_error REAL,
        squared_error REAL,
        mape REAL,
        direction_correct INTEGER,
        version_id TEXT NOT NULL,
        metadata_json TEXT,
        FOREIGN KEY (version_id) REFERENCES working_versions(version_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_rollups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_period TEXT NOT NULL,
        target_period TEXT NOT NULL,
        version_id TEXT NOT NULL,
        summary_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY (version_id) REFERENCES working_versions(version_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS version_aliases (
        period TEXT PRIMARY KEY,
        active_version_id TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        FOREIGN KEY (active_version_id) REFERENCES working_versions(version_id)
    );
    """,
)


TRUTH_METRICS: tuple[dict[str, str], ...] = (
    {
        "metric_key": "volatility",
        "display_name": "Annualised Volatility",
        "formula": "sigma_annualised = stdev(returns) * sqrt(periods_per_year)",
        "explanation": "Measures total dispersion of returns over a configurable lookback window.",
        "assumptions": "Most interpretable when returns are approximately stationary.",
    },
    {
        "metric_key": "covariance",
        "display_name": "Covariance",
        "formula": "Cov(X,Y) = E[(X-mu_x)(Y-mu_y)]",
        "explanation": "Measures how two return series move together in absolute terms.",
        "assumptions": "Linear dependence measure and scale-dependent.",
    },
    {
        "metric_key": "correlation",
        "display_name": "Correlation",
        "formula": "Corr(X,Y) = Cov(X,Y) / (sigma_x * sigma_y)",
        "explanation": "Normalised co-movement between two return series.",
        "assumptions": "Captures linear dependence only.",
    },
    {
        "metric_key": "sharpe_ratio",
        "display_name": "Sharpe Ratio",
        "formula": "Sharpe = (mu - R_f) / sigma",
        "explanation": "Measures excess return per unit of total risk.",
        "assumptions": "Most stable when returns are not heavily skewed or auto-correlated.",
    },
    {
        "metric_key": "sortino_ratio",
        "display_name": "Sortino Ratio",
        "formula": "Sortino = (mu - R_f) / downside_deviation",
        "explanation": "Measures excess return per unit of downside risk.",
        "assumptions": "Only penalises returns below the target threshold.",
    },
    {
        "metric_key": "beta",
        "display_name": "Beta",
        "formula": "Beta = Cov(R_i, R_m) / Var(R_m)",
        "explanation": "Measures systematic sensitivity to a benchmark return series.",
        "assumptions": "Benchmark must be representative and non-constant.",
    },
    {
        "metric_key": "value_at_risk_parametric",
        "display_name": "Parametric VaR",
        "formula": "VaR_alpha = -(mu + z_alpha * sigma)",
        "explanation": "Gaussian loss threshold at a chosen confidence level.",
        "assumptions": "Assumes near-normal return distribution.",
    },
    {
        "metric_key": "value_at_risk_historical",
        "display_name": "Historical VaR",
        "formula": "VaR_alpha = -quantile(returns, 1 - alpha)",
        "explanation": "Empirical loss threshold estimated from historical returns.",
        "assumptions": "Depends on historical window quality and regime coverage.",
    },
    {
        "metric_key": "conditional_value_at_risk",
        "display_name": "Conditional Value at Risk",
        "formula": "CVaR_alpha = mean(losses | losses >= VaR_alpha)",
        "explanation": "Average tail loss beyond the VaR threshold.",
        "assumptions": "Tail estimate quality depends on enough extreme observations.",
    },
    {
        "metric_key": "maximum_drawdown",
        "display_name": "Maximum Drawdown",
        "formula": "MDD = min((price - cummax(price)) / cummax(price))",
        "explanation": "Largest peak-to-trough decline over the evaluation window.",
        "assumptions": "Path dependent and sensitive to the chosen window.",
    },
)


TRUTH_MODELS: tuple[dict[str, Any], ...] = (
    {
        "model_key": "arima",
        "model_name": "ARIMA/SARIMAX",
        "description": "Linear time-series model with optional exogenous regressors.",
        "assumptions": "Requires stationarity or differencing, and stable temporal structure.",
        "supports_exogenous": 1,
    },
    {
        "model_key": "garch",
        "model_name": "GARCH",
        "description": "Volatility model for heteroskedastic return series and clustering.",
        "assumptions": "Works best on return data with time-varying volatility.",
        "supports_exogenous": 0,
    },
    {
        "model_key": "prophet",
        "model_name": "Prophet",
        "description": "Additive trend and seasonality model for longer-horizon forecasting.",
        "assumptions": "Performs best when trends and seasonality dominate over noise.",
        "supports_exogenous": 1,
    },
)


def initialize_knowledge_bases(settings: Settings) -> None:
    """Create truth_db and working_db and seed immutable definitions."""

    with connect_sqlite(settings.truth_db_path) as connection:
        for statement in TRUTH_SCHEMA:
            connection.execute(statement)
        if connection.execute("SELECT COUNT(*) AS count FROM truth_versions").fetchone()["count"] == 0:
            version_id = "truth-v1"
            timestamp = _utc_now()
            connection.execute(
                "INSERT INTO truth_versions(version_id, label, created_at_utc, notes) VALUES (?, ?, ?, ?)",
                (version_id, "initial-authoritative-formulas", timestamp, "Seeded from architecture documents."),
            )
            for metric in TRUTH_METRICS:
                connection.execute(
                    """
                    INSERT INTO metric_definitions(
                        metric_key,
                        display_name,
                        formula,
                        explanation,
                        assumptions,
                        truth_version_id,
                        created_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metric["metric_key"],
                        metric["display_name"],
                        metric["formula"],
                        metric["explanation"],
                        metric["assumptions"],
                        version_id,
                        timestamp,
                    ),
                )
            for model in TRUTH_MODELS:
                connection.execute(
                    """
                    INSERT INTO econometric_definitions(
                        model_key,
                        model_name,
                        description,
                        assumptions,
                        supports_exogenous,
                        truth_version_id,
                        created_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        model["model_key"],
                        model["model_name"],
                        model["description"],
                        model["assumptions"],
                        model["supports_exogenous"],
                        version_id,
                        timestamp,
                    ),
                )

    with connect_sqlite(settings.working_db_path) as connection:
        for statement in WORKING_SCHEMA:
            connection.execute(statement)
        if connection.execute("SELECT COUNT(*) AS count FROM working_versions").fetchone()["count"] == 0:
            timestamp = _utc_now()
            for period in ("daily", "weekly", "monthly"):
                version_id = f"{period}-bootstrap"
                connection.execute(
                    """
                    INSERT INTO working_versions(
                        version_id,
                        parent_version_id,
                        period,
                        created_at_utc,
                        based_on_date,
                        summary,
                        metadata_json
                    )
                    VALUES (?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        period,
                        timestamp,
                        timestamp[:10],
                        f"Bootstrap version for {period} learning state.",
                        json.dumps({"seed": True}),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO version_aliases(period, active_version_id, updated_at_utc)
                    VALUES (?, ?, ?)
                    """,
                    (period, version_id, timestamp),
                )


class KnowledgeBaseManager:
    """Handles immutable truth definitions and rolling working knowledge updates."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def initialize(self) -> None:
        initialize_knowledge_bases(self.settings)

    def get_active_version(self, period: str) -> str:
        with connect_sqlite(self.settings.working_db_path) as connection:
            row = connection.execute(
                "SELECT active_version_id FROM version_aliases WHERE period = ?",
                (period,),
            ).fetchone()
        if row is None:
            raise ValueError(f"No active working version configured for period '{period}'.")
        return str(row["active_version_id"])

    def create_child_version(
        self,
        period: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        parent_version_id = self.get_active_version(period)
        version_id = f"{period}-{uuid.uuid4().hex[:10]}"
        timestamp = _utc_now()
        with connect_sqlite(self.settings.working_db_path) as connection:
            connection.execute(
                """
                INSERT INTO working_versions(
                    version_id,
                    parent_version_id,
                    period,
                    created_at_utc,
                    based_on_date,
                    summary,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    parent_version_id,
                    period,
                    timestamp,
                    timestamp[:10],
                    summary,
                    json.dumps(metadata or {}),
                ),
            )
            connection.execute(
                """
                UPDATE version_aliases
                SET active_version_id = ?, updated_at_utc = ?
                WHERE period = ?
                """,
                (version_id, timestamp, period),
            )
        return version_id

    def update_from_prediction_outcomes(
        self,
        period: str,
        outcomes: Sequence[dict[str, Any]],
    ) -> str:
        """Record prediction outcomes and produce a new working version."""

        if not outcomes:
            return self.get_active_version(period)

        summary_stats = self._summarize_outcomes(outcomes)
        version_id = self.create_child_version(
            period=period,
            summary=summary_stats["summary_text"],
            metadata=summary_stats,
        )
        timestamp = _utc_now()
        with connect_sqlite(self.settings.working_db_path) as connection:
            for outcome in outcomes:
                connection.execute(
                    """
                    INSERT INTO prediction_outcomes(
                        symbol,
                        model_key,
                        period,
                        prediction_timestamp_utc,
                        target_timestamp_utc,
                        predicted_value,
                        actual_value,
                        absolute_error,
                        squared_error,
                        mape,
                        direction_correct,
                        version_id,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outcome["symbol"],
                        outcome["model_key"],
                        period,
                        outcome["prediction_timestamp_utc"],
                        outcome["target_timestamp_utc"],
                        outcome.get("predicted_value"),
                        outcome.get("actual_value"),
                        outcome.get("absolute_error"),
                        outcome.get("squared_error"),
                        outcome.get("mape"),
                        int(outcome.get("direction_correct", False)),
                        version_id,
                        json.dumps(outcome.get("metadata", {})),
                    ),
                )
            for model_key, aggregates in summary_stats["model_rollups"].items():
                connection.execute(
                    """
                    INSERT INTO model_parameters(
                        model_key,
                        symbol,
                        period,
                        version_id,
                        parameter_name,
                        parameter_value,
                        updated_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        model_key,
                        "__aggregate__",
                        period,
                        version_id,
                        "mean_absolute_error",
                        aggregates["mae"],
                        timestamp,
                    ),
                )
        if period == "daily":
            self.merge_period_insights("daily", "weekly")
            self.merge_period_insights("daily", "monthly")
        elif period == "weekly":
            self.merge_period_insights("weekly", "monthly")
        return version_id

    def merge_period_insights(self, source_period: str, target_period: str) -> str:
        """Summarise lower-frequency learning into a higher-level working copy."""

        source_outcomes = self.list_recent_outcomes(source_period)
        if not source_outcomes:
            return self.get_active_version(target_period)
        summary = self._summarize_outcomes(source_outcomes)
        target_version_id = self.create_child_version(
            period=target_period,
            summary=f"Merged {source_period} insights into {target_period} working copy.",
            metadata={"merged_from": source_period, "summary": summary},
        )
        with connect_sqlite(self.settings.working_db_path) as connection:
            connection.execute(
                """
                INSERT INTO insight_rollups(
                    source_period,
                    target_period,
                    version_id,
                    summary_json,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    source_period,
                    target_period,
                    target_version_id,
                    json.dumps(summary),
                    _utc_now(),
                ),
            )
        return target_version_id

    def list_recent_outcomes(self, period: str, limit: int = 250) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.working_db_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM prediction_outcomes
                WHERE period = ?
                ORDER BY prediction_timestamp_utc DESC
                LIMIT ?
                """,
                (period, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _summarize_outcomes(self, outcomes: Sequence[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        absolute_errors: list[float] = []
        percentage_errors: list[float] = []
        direction_hits: list[float] = []
        for outcome in outcomes:
            grouped[outcome["model_key"]].append(outcome)
            if outcome.get("absolute_error") is not None:
                absolute_errors.append(float(outcome["absolute_error"]))
            if outcome.get("mape") is not None:
                percentage_errors.append(float(outcome["mape"]))
            if outcome.get("direction_correct") is not None:
                direction_hits.append(float(bool(outcome["direction_correct"])))
        model_rollups: dict[str, dict[str, float]] = {}
        for model_key, model_outcomes in grouped.items():
            model_abs_errors = [
                float(item["absolute_error"])
                for item in model_outcomes
                if item.get("absolute_error") is not None
            ]
            model_rollups[model_key] = {
                "mae": mean(model_abs_errors) if model_abs_errors else 0.0,
                "count": float(len(model_outcomes)),
            }
        summary_text = (
            f"{len(outcomes)} outcomes processed; "
            f"mean absolute error={mean(absolute_errors):.6f} "
            f"mean MAPE={mean(percentage_errors):.6f} "
            f"directional accuracy={mean(direction_hits):.6f}"
            if absolute_errors and percentage_errors and direction_hits
            else f"{len(outcomes)} outcomes processed."
        )
        return {
            "summary_text": summary_text,
            "mean_absolute_error": mean(absolute_errors) if absolute_errors else None,
            "mean_mape": mean(percentage_errors) if percentage_errors else None,
            "directional_accuracy": mean(direction_hits) if direction_hits else None,
            "model_rollups": model_rollups,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
