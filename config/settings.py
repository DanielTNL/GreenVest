"""Runtime configuration for the AI investment backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_ENV_LOADED = False


def _load_local_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    project_root = Path(__file__).resolve().parents[1]
    for candidate in (project_root / ".env.local", project_root / "config" / ".env.local"):
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _env(name: str, default: str | None = None) -> str | None:
    _load_local_env()
    return os.getenv(name, default)


@dataclass(slots=True)
class Settings:
    """Application settings derived from environment variables and project layout."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    storage_root: Path = field(
        default_factory=lambda: Path(
            _env("APP_STORAGE_ROOT") or str(Path(__file__).resolve().parents[1])
        )
    )
    database_name: str = "market_data.sqlite3"
    truth_database_name: str = "truth.db"
    working_database_name: str = "working.db"
    alpha_vantage_api_key: str | None = field(default_factory=lambda: _env("ALPHAVANTAGE_API_KEY"))
    fmp_api_key: str | None = field(default_factory=lambda: _env("FMP_API_KEY"))
    eodhd_api_key: str | None = field(default_factory=lambda: _env("EODHD_API_KEY"))
    fred_api_key: str | None = field(default_factory=lambda: _env("FRED_API_KEY"))
    openai_api_key: str | None = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-5-mini") or "gpt-5-mini")
    default_stock_symbols: tuple[str, ...] = ("AAPL", "MSFT", "SPY")
    default_macro_series: dict[str, str] = field(
        default_factory=lambda: {
            "GDP": "GDP",
            "CPI": "CPIAUCSL",
            "Fed Funds Rate": "FEDFUNDS",
            "Unemployment Rate": "UNRATE",
            "WTI Oil": "DCOILWTICO",
        }
    )
    geopolitical_risk_series_id: str | None = field(default_factory=lambda: _env("GEOPOLITICAL_RISK_FRED_SERIES_ID"))
    geopolitical_risk_series_name: str = field(
        default_factory=lambda: _env("GEOPOLITICAL_RISK_SERIES_NAME", "Geopolitical Risk Index") or "Geopolitical Risk Index"
    )
    default_commodity_symbols: tuple[str, ...] = ("GCUSD",)
    default_polymarket_limit: int = 100
    alpha_vantage_min_interval_seconds: float = 12.5
    fmp_max_calls_per_day: int = 250
    eodhd_max_calls_per_day: int = 1000
    requests_timeout_seconds: int = 30
    scheduler_timezone: str = "UTC"
    market_timezone: str = "UTC"

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def data_dir(self) -> Path:
        return self.storage_root / "data"

    @property
    def raw_data_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_data_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def db_dir(self) -> Path:
        return self.storage_root / "db"

    @property
    def log_dir(self) -> Path:
        return self.storage_root / "logs"

    @property
    def database_path(self) -> Path:
        return self.db_dir / self.database_name

    @property
    def truth_db_path(self) -> Path:
        return self.db_dir / self.truth_database_name

    @property
    def working_db_path(self) -> Path:
        return self.db_dir / self.working_database_name

    @property
    def rate_limit_state_path(self) -> Path:
        return self.processed_data_dir / "rate_limit_state.json"

    def configured_macro_series(self, *, include_geopolitical: bool = True) -> dict[str, str]:
        series = dict(self.default_macro_series)
        if include_geopolitical and self.geopolitical_risk_series_id:
            series[self.geopolitical_risk_series_name] = self.geopolitical_risk_series_id
        return series


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Return a singleton settings object."""

    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()
    return _SETTINGS
