"""Repositories for persisting normalized records."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from config import Settings

from .connection import connect_sqlite


class MarketRepository:
    """Persistence layer for normalized market, analytics, and audit records."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_basket(
        self,
        name: str,
        description: str,
        constituents: Sequence[tuple[str, float]],
    ) -> int:
        with connect_sqlite(self.settings.database_path) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO baskets(name, description) VALUES (?, ?)",
                (name, description),
            )
            if cursor.lastrowid:
                basket_id = int(cursor.lastrowid)
            else:
                basket_id = int(
                    connection.execute(
                        "SELECT basket_id FROM baskets WHERE name = ?",
                        (name,),
                    ).fetchone()["basket_id"]
                )
                connection.execute(
                    "UPDATE baskets SET description = ? WHERE basket_id = ?",
                    (description, basket_id),
                )
                connection.execute(
                    "DELETE FROM basket_constituents WHERE basket_id = ?",
                    (basket_id,),
                )
            for symbol, weight in constituents:
                connection.execute(
                    """
                    INSERT INTO basket_constituents(basket_id, symbol, weight)
                    VALUES (?, ?, ?)
                    ON CONFLICT(basket_id, symbol) DO UPDATE SET weight = excluded.weight
                    """,
                    (basket_id, symbol, weight),
                )
            return basket_id

    def get_basket_constituents(self, basket_id: int) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT basket_id, symbol, weight
                FROM basket_constituents
                WHERE basket_id = ?
                ORDER BY symbol
                """,
                (basket_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def track_stock_symbol(self, symbol: str) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO tracked_stocks(symbol)
                VALUES (?)
                ON CONFLICT(symbol) DO NOTHING
                """,
                (symbol.upper(),),
            )

    def list_tracked_stock_symbols(self) -> list[str]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                "SELECT symbol FROM tracked_stocks ORDER BY added_at_utc DESC, symbol ASC"
            ).fetchall()
        return [row["symbol"] for row in rows]

    def upsert_stocks(self, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO stocks(symbol, name, exchange, asset_type, source, updated_at_utc)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(symbol) DO UPDATE SET
                        name = excluded.name,
                        exchange = excluded.exchange,
                        asset_type = excluded.asset_type,
                        source = excluded.source,
                        updated_at_utc = CURRENT_TIMESTAMP
                    """,
                    (
                        record.get("symbol"),
                        record.get("name"),
                        record.get("exchange"),
                        record.get("asset_type"),
                        record.get("source"),
                    ),
                )

    def upsert_stock_prices(self, records: Iterable[dict[str, Any]]) -> None:
        self._upsert_price_records("stock_prices", records)

    def upsert_macro_indicator(self, record: dict[str, Any]) -> int:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO macro_indicators(name, fred_series_id, frequency, units)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    fred_series_id = excluded.fred_series_id,
                    frequency = excluded.frequency,
                    units = excluded.units
                """,
                (
                    record["name"],
                    record["fred_series_id"],
                    record.get("frequency"),
                    record.get("units"),
                ),
            )
            row = connection.execute(
                "SELECT id FROM macro_indicators WHERE name = ?",
                (record["name"],),
            ).fetchone()
            return int(row["id"])

    def upsert_macro_observations(self, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO macro_observations(
                        macro_id,
                        observation_date,
                        timestamp_utc,
                        value,
                        realtime_start,
                        realtime_end,
                        source,
                        raw_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(macro_id, observation_date) DO UPDATE SET
                        timestamp_utc = excluded.timestamp_utc,
                        value = excluded.value,
                        realtime_start = excluded.realtime_start,
                        realtime_end = excluded.realtime_end,
                        source = excluded.source,
                        raw_path = excluded.raw_path
                    """,
                    (
                        record["macro_id"],
                        record["observation_date"],
                        record["timestamp_utc"],
                        record.get("value"),
                        record.get("realtime_start"),
                        record.get("realtime_end"),
                        record.get("source", "fred"),
                        record.get("raw_path"),
                    ),
                )

    def upsert_commodities(self, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO commodities(symbol, name, source)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        name = excluded.name,
                        source = excluded.source
                    """,
                    (record["symbol"], record.get("name"), record.get("source")),
                )

    def upsert_commodity_prices(self, records: Iterable[dict[str, Any]]) -> None:
        self._upsert_price_records("commodity_prices", records)

    def upsert_prediction_markets(self, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO prediction_markets(
                        market_id,
                        event_id,
                        slug,
                        question,
                        description,
                        active,
                        closed,
                        end_date_utc,
                        tags_json,
                        source,
                        raw_path,
                        updated_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(market_id) DO UPDATE SET
                        event_id = excluded.event_id,
                        slug = excluded.slug,
                        question = excluded.question,
                        description = excluded.description,
                        active = excluded.active,
                        closed = excluded.closed,
                        end_date_utc = excluded.end_date_utc,
                        tags_json = excluded.tags_json,
                        source = excluded.source,
                        raw_path = excluded.raw_path,
                        updated_at_utc = CURRENT_TIMESTAMP
                    """,
                    (
                        record["market_id"],
                        record.get("event_id"),
                        record.get("slug"),
                        record["question"],
                        record.get("description"),
                        int(record.get("active", False)),
                        int(record.get("closed", False)),
                        record.get("end_date_utc"),
                        json.dumps(record.get("tags", [])),
                        record.get("source", "polymarket"),
                        record.get("raw_path"),
                    ),
                )

    def upsert_prediction_market_odds(self, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO prediction_market_odds(
                        market_id,
                        timestamp_utc,
                        yes_prob,
                        no_prob,
                        last_trade_price,
                        volume,
                        liquidity,
                        raw_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(market_id, timestamp_utc) DO UPDATE SET
                        yes_prob = excluded.yes_prob,
                        no_prob = excluded.no_prob,
                        last_trade_price = excluded.last_trade_price,
                        volume = excluded.volume,
                        liquidity = excluded.liquidity,
                        raw_path = excluded.raw_path
                    """,
                    (
                        record["market_id"],
                        record["timestamp_utc"],
                        record.get("yes_prob"),
                        record.get("no_prob"),
                        record.get("last_trade_price"),
                        record.get("volume"),
                        record.get("liquidity"),
                        record.get("raw_path"),
                    ),
                )

    def save_risk_metrics(self, record: dict[str, Any]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO risk_metrics_history(
                    symbol,
                    basket_id,
                    benchmark_symbol,
                    calculation_date,
                    lookback_window,
                    confidence_level,
                    volatility,
                    covariance,
                    correlation,
                    sharpe,
                    sortino,
                    beta,
                    var_parametric,
                    var_historical,
                    var_monte_carlo,
                    cvar,
                    max_drawdown
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("symbol"),
                    record.get("basket_id"),
                    record.get("benchmark_symbol"),
                    record["calculation_date"],
                    record.get("lookback_window"),
                    record.get("confidence_level"),
                    record.get("volatility"),
                    record.get("covariance"),
                    record.get("correlation"),
                    record.get("sharpe"),
                    record.get("sortino"),
                    record.get("beta"),
                    record.get("var_parametric"),
                    record.get("var_historical"),
                    record.get("var_monte_carlo"),
                    record.get("cvar"),
                    record.get("max_drawdown"),
                ),
            )

    def save_forecast(self, record: dict[str, Any]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO forecasts(
                    symbol,
                    model,
                    run_timestamp_utc,
                    horizon,
                    horizon_unit,
                    forecast_value,
                    lower_bound,
                    upper_bound,
                    exogenous_features_json,
                    version_id,
                    actual_value,
                    error_metric,
                    error_value,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["symbol"],
                    record["model"],
                    record["run_timestamp_utc"],
                    record["horizon"],
                    record["horizon_unit"],
                    record.get("forecast_value"),
                    record.get("lower_bound"),
                    record.get("upper_bound"),
                    json.dumps(record.get("exogenous_features")),
                    record.get("version_id"),
                    record.get("actual_value"),
                    record.get("error_metric"),
                    record.get("error_value"),
                    record.get("status", "generated"),
                ),
            )

    def save_simulation(self, record: dict[str, Any]) -> int:
        with connect_sqlite(self.settings.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO simulations(
                    basket_id,
                    portfolio_name,
                    start_date,
                    end_date,
                    horizon,
                    horizon_unit,
                    initial_capital,
                    predicted_return,
                    actual_return,
                    rmse,
                    mape,
                    directional_accuracy,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("basket_id"),
                    record.get("portfolio_name"),
                    record["start_date"],
                    record["end_date"],
                    record["horizon"],
                    record["horizon_unit"],
                    record["initial_capital"],
                    record.get("predicted_return"),
                    record.get("actual_return"),
                    record.get("rmse"),
                    record.get("mape"),
                    record.get("directional_accuracy"),
                    json.dumps(record.get("details")),
                ),
            )
            return int(cursor.lastrowid)

    def update_simulation(
        self,
        sim_id: int,
        *,
        predicted_return: float | None = None,
        actual_return: float | None = None,
        rmse: float | None = None,
        mape: float | None = None,
        directional_accuracy: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                UPDATE simulations
                SET predicted_return = ?,
                    actual_return = ?,
                    rmse = ?,
                    mape = ?,
                    directional_accuracy = ?,
                    details_json = ?
                WHERE sim_id = ?
                """,
                (
                    predicted_return,
                    actual_return,
                    rmse,
                    mape,
                    directional_accuracy,
                    json.dumps(details or {}),
                    sim_id,
                ),
            )

    def save_simulation_results(self, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    """
                    INSERT INTO simulation_results(
                        simulation_id,
                        evaluation_timestamp_utc,
                        model,
                        predicted_value,
                        actual_value,
                        absolute_error,
                        squared_error,
                        percentage_error
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(simulation_id, evaluation_timestamp_utc, model) DO UPDATE SET
                        predicted_value = excluded.predicted_value,
                        actual_value = excluded.actual_value,
                        absolute_error = excluded.absolute_error,
                        squared_error = excluded.squared_error,
                        percentage_error = excluded.percentage_error
                    """,
                    (
                        record["simulation_id"],
                        record["evaluation_timestamp_utc"],
                        record["model"],
                        record.get("predicted_value"),
                        record.get("actual_value"),
                        record.get("absolute_error"),
                        record.get("squared_error"),
                        record.get("percentage_error"),
                    ),
                )

    def get_simulation(self, sim_id: int) -> dict[str, Any] | None:
        with connect_sqlite(self.settings.database_path) as connection:
            row = connection.execute(
                """
                SELECT sim_id, basket_id, portfolio_name, start_date, end_date, horizon, horizon_unit,
                       initial_capital, predicted_return, actual_return, rmse, mape,
                       directional_accuracy, details_json, created_at_utc
                FROM simulations
                WHERE sim_id = ?
                """,
                (sim_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json") or "{}")
        return item

    def list_simulation_results(self, simulation_id: int) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT simulation_id, evaluation_timestamp_utc, model, predicted_value, actual_value,
                       absolute_error, squared_error, percentage_error
                FROM simulation_results
                WHERE simulation_id = ?
                ORDER BY evaluation_timestamp_utc DESC, model
                """,
                (simulation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_simulation(self, sim_id: int) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute("DELETE FROM simulation_results WHERE simulation_id = ?", (sim_id,))
            connection.execute("DELETE FROM simulations WHERE sim_id = ?", (sim_id,))

    def log_audit(self, component: str, level: str, message: str, metadata: dict[str, Any] | None = None) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO audit_logs(timestamp_utc, component, level, message, metadata_json)
                VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?)
                """,
                (component, level, message, json.dumps(metadata or {})),
            )

    def log_raw_ingestion(self, record: dict[str, Any]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO raw_ingestions(
                    provider,
                    endpoint,
                    entity_key,
                    requested_at_utc,
                    raw_path,
                    status,
                    http_status,
                    checksum
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["provider"],
                    record["endpoint"],
                    record.get("entity_key"),
                    record["requested_at_utc"],
                    record["raw_path"],
                    record["status"],
                    record.get("http_status"),
                    record.get("checksum"),
                ),
            )

    def get_price_series(
        self,
        symbol: str,
        interval: str = "1day",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT symbol, source, interval, timestamp_utc, trading_date, open, high, low, close, volume
            FROM stock_prices
            WHERE symbol = ? AND interval = ?
        """
        params: list[Any] = [symbol, interval]
        if start_date:
            query += " AND trading_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trading_date <= ?"
            params.append(end_date)
        query += " ORDER BY timestamp_utc"
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def latest_stock_symbols(self) -> list[str]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT symbol
                FROM stocks
                WHERE UPPER(COALESCE(source, '')) NOT IN ('UNIT', 'TEST')
                ORDER BY symbol
                """
            ).fetchall()
        return [row["symbol"] for row in rows]

    def get_stock(self, symbol: str) -> dict[str, Any] | None:
        with connect_sqlite(self.settings.database_path) as connection:
            row = connection.execute(
                """
                SELECT symbol, name, exchange, asset_type, source, created_at_utc, updated_at_utc
                FROM stocks
                WHERE symbol = ?
                """,
                (symbol.upper(),),
            ).fetchone()
        return dict(row) if row else None

    def search_stocks(self, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        like_value = None
        statement = """
            SELECT
                s.symbol,
                s.name,
                s.exchange,
                s.asset_type,
                s.source,
                (
                    SELECT close
                    FROM stock_prices sp
                    WHERE sp.symbol = s.symbol
                    ORDER BY sp.timestamp_utc DESC
                    LIMIT 1
                ) AS latest_close,
                (
                    SELECT timestamp_utc
                    FROM stock_prices sp
                    WHERE sp.symbol = s.symbol
                    ORDER BY sp.timestamp_utc DESC
                    LIMIT 1
                ) AS latest_price_timestamp_utc
            FROM stocks s
            WHERE UPPER(COALESCE(s.source, '')) NOT IN ('UNIT', 'TEST')
        """
        parameters: list[Any] = []
        if query:
            like_value = f"%{query.upper()}%"
            statement += """
                AND (
                    UPPER(s.symbol) LIKE ?
                    OR UPPER(COALESCE(s.name, '')) LIKE ?
                )
            """
            parameters.extend([like_value, like_value])
        statement += " ORDER BY s.symbol LIMIT ?"
        parameters.append(limit)
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [dict(row) for row in rows]

    def list_tracked_stocks(self, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        statement = """
            SELECT
                s.symbol,
                s.name,
                s.exchange,
                s.asset_type,
                s.source,
                (
                    SELECT close
                    FROM stock_prices sp
                    WHERE sp.symbol = s.symbol
                    ORDER BY sp.timestamp_utc DESC
                    LIMIT 1
                ) AS latest_close,
                (
                    SELECT timestamp_utc
                    FROM stock_prices sp
                    WHERE sp.symbol = s.symbol
                    ORDER BY sp.timestamp_utc DESC
                    LIMIT 1
                ) AS latest_price_timestamp_utc
            FROM tracked_stocks ts
            INNER JOIN stocks s ON s.symbol = ts.symbol
            WHERE 1 = 1
        """
        parameters: list[Any] = []
        if query:
            like_value = f"%{query.upper()}%"
            statement += """
                AND (
                    UPPER(s.symbol) LIKE ?
                    OR UPPER(COALESCE(s.name, '')) LIKE ?
                )
            """
            parameters.extend([like_value, like_value])
        statement += " ORDER BY ts.added_at_utc DESC, s.symbol ASC LIMIT ?"
        parameters.append(limit)
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [dict(row) for row in rows]

    def replace_watch_suggestions(self, suggestion_date: str, records: Sequence[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                "DELETE FROM watch_suggestions WHERE suggestion_date = ?",
                (suggestion_date,),
            )
            for record in records:
                connection.execute(
                    """
                    INSERT INTO watch_suggestions(
                        suggestion_date,
                        symbol,
                        rank,
                        name,
                        theme,
                        rationale,
                        score,
                        latest_close
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        suggestion_date,
                        record["symbol"],
                        int(record["rank"]),
                        record.get("name"),
                        record.get("theme"),
                        record.get("rationale"),
                        record.get("score"),
                        record.get("latest_close"),
                    ),
                )

    def list_watch_suggestions(
        self,
        *,
        suggestion_date: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if suggestion_date is None:
            with connect_sqlite(self.settings.database_path) as connection:
                latest = connection.execute(
                    "SELECT MAX(suggestion_date) AS value FROM watch_suggestions"
                ).fetchone()
                suggestion_date = latest["value"]
        if suggestion_date is None:
            return []
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    ws.suggestion_date,
                    ws.symbol,
                    ws.rank,
                    ws.name,
                    ws.theme,
                    ws.rationale,
                    ws.score,
                    ws.latest_close,
                    CASE WHEN ts.symbol IS NULL THEN 0 ELSE 1 END AS is_tracked
                FROM watch_suggestions ws
                LEFT JOIN tracked_stocks ts ON ts.symbol = ws.symbol
                WHERE ws.suggestion_date = ?
                ORDER BY ws.rank ASC, ws.symbol ASC
                LIMIT ?
                """,
                (suggestion_date, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_baskets(self) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                "SELECT basket_id, name, description, created_at_utc FROM baskets ORDER BY basket_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_baskets_with_constituents(self) -> list[dict[str, Any]]:
        baskets = self.list_baskets()
        for basket in baskets:
            basket["constituents"] = self.get_basket_constituents(int(basket["basket_id"]))
        return baskets

    def get_basket(self, basket_id: int) -> dict[str, Any] | None:
        with connect_sqlite(self.settings.database_path) as connection:
            row = connection.execute(
                """
                SELECT basket_id, name, description, created_at_utc
                FROM baskets
                WHERE basket_id = ?
                """,
                (basket_id,),
            ).fetchone()
        if row is None:
            return None
        basket = dict(row)
        basket["constituents"] = self.get_basket_constituents(basket_id)
        return basket

    def latest_risk_metric(
        self,
        *,
        symbol: str | None = None,
        basket_id: int | None = None,
    ) -> dict[str, Any] | None:
        if symbol is None and basket_id is None:
            raise ValueError("Either symbol or basket_id must be provided.")
        clause = "symbol = ?" if symbol is not None else "basket_id = ?"
        value = symbol.upper() if symbol is not None else basket_id
        with connect_sqlite(self.settings.database_path) as connection:
            row = connection.execute(
                f"""
                SELECT *
                FROM risk_metrics_history
                WHERE {clause}
                ORDER BY calculation_date DESC, id DESC
                LIMIT 1
                """,
                (value,),
            ).fetchone()
        return dict(row) if row else None

    def latest_forecast(self, symbol: str) -> dict[str, Any] | None:
        with connect_sqlite(self.settings.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM forecasts
                WHERE symbol = ?
                ORDER BY run_timestamp_utc DESC, id DESC
                LIMIT 1
                """,
                (symbol.upper(),),
            ).fetchone()
        return dict(row) if row else None

    def list_recent_simulations(self, limit: int = 20) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT sim_id, basket_id, portfolio_name, start_date, end_date, horizon, horizon_unit,
                       initial_capital, predicted_return, actual_return, rmse, mape,
                       directional_accuracy, details_json, created_at_utc
                FROM simulations
                ORDER BY created_at_utc DESC, sim_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        simulations: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            simulations.append(item)
        return simulations

    def list_macro_indicators(self, history_limit: int = 60) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            indicators = connection.execute(
                """
                SELECT id, name, fred_series_id, frequency, units
                FROM macro_indicators
                ORDER BY name
                """
            ).fetchall()
            results: list[dict[str, Any]] = []
            for indicator in indicators:
                item = dict(indicator)
                latest = connection.execute(
                    """
                    SELECT observation_date, timestamp_utc, value
                    FROM macro_observations
                    WHERE macro_id = ?
                    ORDER BY observation_date DESC
                    LIMIT 1
                    """,
                    (indicator["id"],),
                ).fetchone()
                history_rows = connection.execute(
                    """
                    SELECT observation_date, value
                    FROM macro_observations
                    WHERE macro_id = ?
                    ORDER BY observation_date DESC
                    LIMIT ?
                    """,
                    (indicator["id"], history_limit),
                ).fetchall()
                item["latest_observation"] = dict(latest) if latest else None
                item["history"] = [dict(row) for row in reversed(history_rows)]
                results.append(item)
        return results

    def get_macro_indicator_by_name(self, name: str, history_limit: int = 60) -> dict[str, Any] | None:
        for indicator in self.list_macro_indicators(history_limit=history_limit):
            if str(indicator["name"]).lower() == name.lower():
                return indicator
        return None

    def list_commodities(self, history_limit: int = 60) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            commodities = connection.execute(
                """
                SELECT symbol, name, source
                FROM commodities
                ORDER BY symbol
                """
            ).fetchall()
            results: list[dict[str, Any]] = []
            for commodity in commodities:
                item = dict(commodity)
                latest = connection.execute(
                    """
                    SELECT timestamp_utc, close, open, high, low, volume
                    FROM commodity_prices
                    WHERE symbol = ?
                    ORDER BY timestamp_utc DESC
                    LIMIT 1
                    """,
                    (commodity["symbol"],),
                ).fetchone()
                history_rows = connection.execute(
                    """
                    SELECT trading_date, close
                    FROM commodity_prices
                    WHERE symbol = ?
                    ORDER BY timestamp_utc DESC
                    LIMIT ?
                    """,
                    (commodity["symbol"], history_limit),
                ).fetchall()
                item["latest_price"] = dict(latest) if latest else None
                item["history"] = [dict(row) for row in reversed(history_rows)]
                results.append(item)
        return results

    def list_prediction_markets(self, limit: int = 25) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    pm.market_id,
                    pm.slug,
                    pm.question,
                    pm.description,
                    pm.active,
                    pm.closed,
                    pm.end_date_utc,
                    pm.updated_at_utc,
                    pmo.timestamp_utc,
                    pmo.yes_prob,
                    pmo.no_prob,
                    pmo.last_trade_price,
                    pmo.volume,
                    pmo.liquidity
                FROM prediction_markets pm
                LEFT JOIN prediction_market_odds pmo
                  ON pmo.market_id = pm.market_id
                 AND pmo.timestamp_utc = (
                    SELECT MAX(inner_pmo.timestamp_utc)
                    FROM prediction_market_odds inner_pmo
                    WHERE inner_pmo.market_id = pm.market_id
                 )
                ORDER BY pm.updated_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_prediction_market_snapshots(self) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT pmo.*
                FROM prediction_market_odds pmo
                INNER JOIN (
                    SELECT market_id, MAX(timestamp_utc) AS max_timestamp
                    FROM prediction_market_odds
                    GROUP BY market_id
                ) latest
                    ON latest.market_id = pmo.market_id
                    AND latest.max_timestamp = pmo.timestamp_utc
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def list_alert_feed(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect_sqlite(self.settings.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM (
                    SELECT
                        'alert-' || alert_id AS feed_id,
                        'alert' AS source,
                        level,
                        symbol,
                        message AS title,
                        message,
                        alert_date_utc AS timestamp_utc
                    FROM alerts
                    UNION ALL
                    SELECT
                        'audit-' || id AS feed_id,
                        component AS source,
                        level,
                        NULL AS symbol,
                        component AS title,
                        message,
                        timestamp_utc
                    FROM audit_logs
                )
                ORDER BY timestamp_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_alert(
        self,
        message: str,
        *,
        level: str = "info",
        symbol: str = "SYSTEM",
        threshold: float = 0.0,
        triggered_value: float | None = None,
    ) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            connection.execute(
                """
                INSERT INTO alerts(symbol, threshold, triggered_value, alert_date_utc, message, level)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (symbol, threshold, triggered_value, message, level),
            )

    def get_system_status(self) -> dict[str, Any]:
        with connect_sqlite(self.settings.database_path) as connection:
            status = {
                "stock_count": connection.execute("SELECT COUNT(*) AS count FROM stocks").fetchone()["count"],
                "basket_count": connection.execute("SELECT COUNT(*) AS count FROM baskets").fetchone()["count"],
                "forecast_count": connection.execute("SELECT COUNT(*) AS count FROM forecasts").fetchone()["count"],
                "simulation_count": connection.execute("SELECT COUNT(*) AS count FROM simulations").fetchone()["count"],
                "last_stock_update_utc": connection.execute(
                    "SELECT MAX(timestamp_utc) AS value FROM stock_prices"
                ).fetchone()["value"],
                "last_macro_update_utc": connection.execute(
                    "SELECT MAX(timestamp_utc) AS value FROM macro_observations"
                ).fetchone()["value"],
                "last_prediction_market_update_utc": connection.execute(
                    "SELECT MAX(timestamp_utc) AS value FROM prediction_market_odds"
                ).fetchone()["value"],
                "last_audit_utc": connection.execute(
                    "SELECT MAX(timestamp_utc) AS value FROM audit_logs"
                ).fetchone()["value"],
            }
        return status

    def _upsert_price_records(self, table_name: str, records: Iterable[dict[str, Any]]) -> None:
        with connect_sqlite(self.settings.database_path) as connection:
            for record in records:
                connection.execute(
                    f"""
                    INSERT INTO {table_name}(
                        symbol,
                        source,
                        interval,
                        timestamp_utc,
                        trading_date,
                        price,
                        open,
                        high,
                        low,
                        close,
                        volume,
                        raw_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, source, interval, timestamp_utc) DO UPDATE SET
                        trading_date = excluded.trading_date,
                        price = excluded.price,
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        volume = excluded.volume,
                        raw_path = excluded.raw_path
                    """,
                    (
                        record["symbol"],
                        record["source"],
                        record["interval"],
                        record["timestamp_utc"],
                        record["trading_date"],
                        record.get("price"),
                        record.get("open"),
                        record.get("high"),
                        record.get("low"),
                        record.get("close"),
                        record.get("volume"),
                        record.get("raw_path"),
                    ),
                )
