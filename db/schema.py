"""Primary market database schema management."""

from __future__ import annotations

from collections.abc import Iterable

from config import Settings

from .connection import connect_sqlite


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS stocks (
        symbol TEXT PRIMARY KEY,
        name TEXT,
        exchange TEXT,
        asset_type TEXT,
        source TEXT,
        created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_prices (
        symbol TEXT NOT NULL,
        source TEXT NOT NULL,
        interval TEXT NOT NULL DEFAULT '1day',
        timestamp_utc TEXT NOT NULL,
        trading_date TEXT NOT NULL,
        price REAL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        raw_path TEXT,
        ingested_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, source, interval, timestamp_utc),
        FOREIGN KEY (symbol) REFERENCES stocks(symbol)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_stock_prices_symbol_date ON stock_prices(symbol, trading_date);",
    """
    CREATE TABLE IF NOT EXISTS baskets (
        basket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS basket_constituents (
        basket_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        weight REAL NOT NULL,
        PRIMARY KEY (basket_id, symbol),
        FOREIGN KEY (basket_id) REFERENCES baskets(basket_id),
        FOREIGN KEY (symbol) REFERENCES stocks(symbol)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tracked_stocks (
        symbol TEXT PRIMARY KEY,
        added_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (symbol) REFERENCES stocks(symbol)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        fred_series_id TEXT NOT NULL UNIQUE,
        frequency TEXT,
        units TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS macro_observations (
        macro_id INTEGER NOT NULL,
        observation_date TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        value REAL,
        realtime_start TEXT,
        realtime_end TEXT,
        source TEXT DEFAULT 'fred',
        raw_path TEXT,
        PRIMARY KEY (macro_id, observation_date),
        FOREIGN KEY (macro_id) REFERENCES macro_indicators(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS commodities (
        symbol TEXT PRIMARY KEY,
        name TEXT,
        source TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS commodity_prices (
        symbol TEXT NOT NULL,
        source TEXT NOT NULL,
        interval TEXT NOT NULL DEFAULT '1day',
        timestamp_utc TEXT NOT NULL,
        trading_date TEXT NOT NULL,
        price REAL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        raw_path TEXT,
        ingested_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, source, interval, timestamp_utc),
        FOREIGN KEY (symbol) REFERENCES commodities(symbol)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_commodity_prices_symbol_date ON commodity_prices(symbol, trading_date);",
    """
    CREATE TABLE IF NOT EXISTS prediction_markets (
        market_id TEXT PRIMARY KEY,
        event_id TEXT,
        slug TEXT,
        question TEXT NOT NULL,
        description TEXT,
        active INTEGER NOT NULL DEFAULT 0,
        closed INTEGER NOT NULL DEFAULT 0,
        end_date_utc TEXT,
        tags_json TEXT,
        source TEXT DEFAULT 'polymarket',
        raw_path TEXT,
        updated_at_utc TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS prediction_market_odds (
        market_id TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        yes_prob REAL,
        no_prob REAL,
        last_trade_price REAL,
        volume REAL,
        liquidity REAL,
        raw_path TEXT,
        PRIMARY KEY (market_id, timestamp_utc),
        FOREIGN KEY (market_id) REFERENCES prediction_markets(market_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_metrics_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        basket_id INTEGER,
        benchmark_symbol TEXT,
        calculation_date TEXT NOT NULL,
        lookback_window INTEGER,
        confidence_level REAL,
        volatility REAL,
        covariance REAL,
        correlation REAL,
        sharpe REAL,
        sortino REAL,
        beta REAL,
        var_parametric REAL,
        var_historical REAL,
        var_monte_carlo REAL,
        cvar REAL,
        max_drawdown REAL,
        created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (basket_id) REFERENCES baskets(basket_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        model TEXT NOT NULL,
        run_timestamp_utc TEXT NOT NULL,
        horizon INTEGER NOT NULL,
        horizon_unit TEXT NOT NULL,
        forecast_value REAL,
        lower_bound REAL,
        upper_bound REAL,
        exogenous_features_json TEXT,
        version_id TEXT,
        actual_value REAL,
        error_metric TEXT,
        error_value REAL,
        status TEXT DEFAULT 'generated'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS simulations (
        sim_id INTEGER PRIMARY KEY AUTOINCREMENT,
        basket_id INTEGER,
        portfolio_name TEXT,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        horizon INTEGER NOT NULL,
        horizon_unit TEXT NOT NULL,
        initial_capital REAL NOT NULL,
        predicted_return REAL,
        actual_return REAL,
        rmse REAL,
        mape REAL,
        directional_accuracy REAL,
        details_json TEXT,
        created_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (basket_id) REFERENCES baskets(basket_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS simulation_results (
        simulation_id INTEGER NOT NULL,
        evaluation_timestamp_utc TEXT NOT NULL,
        model TEXT NOT NULL,
        predicted_value REAL,
        actual_value REAL,
        absolute_error REAL,
        squared_error REAL,
        percentage_error REAL,
        PRIMARY KEY (simulation_id, evaluation_timestamp_utc, model),
        FOREIGN KEY (simulation_id) REFERENCES simulations(sim_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_utc TEXT NOT NULL,
        component TEXT NOT NULL,
        level TEXT NOT NULL,
        message TEXT NOT NULL,
        metadata_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        threshold REAL NOT NULL,
        triggered_value REAL,
        alert_date_utc TEXT NOT NULL,
        message TEXT NOT NULL,
        level TEXT DEFAULT 'info'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_ingestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        endpoint TEXT NOT NULL,
        entity_key TEXT,
        requested_at_utc TEXT NOT NULL,
        raw_path TEXT NOT NULL,
        status TEXT NOT NULL,
        http_status INTEGER,
        checksum TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS watch_suggestions (
        suggestion_date TEXT NOT NULL,
        symbol TEXT NOT NULL,
        rank INTEGER NOT NULL,
        name TEXT,
        theme TEXT,
        rationale TEXT,
        score REAL,
        latest_close REAL,
        generated_at_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (suggestion_date, symbol)
    );
    """,
)


def initialize_market_database(settings: Settings) -> None:
    """Create all market database tables and indexes."""

    with connect_sqlite(settings.database_path) as connection:
        _execute_statements(connection, SCHEMA_STATEMENTS)
        _ensure_column(connection, "stock_prices", "price", "REAL")


def _execute_statements(connection, statements: Iterable[str]) -> None:
    for statement in statements:
        connection.execute(statement)


def _ensure_column(connection, table_name: str, column_name: str, column_type: str) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
