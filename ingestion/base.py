"""Shared HTTP, retry, rate limiting, and raw archival utilities."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Settings


class APIClientError(RuntimeError):
    """Raised when an upstream API responds with an invalid payload or error."""


class RateLimitExceeded(APIClientError):
    """Raised when a provider's configured quota has been exhausted."""


@dataclass(slots=True)
class RateLimitPolicy:
    """Provider rate-limit constraints."""

    min_interval_seconds: float = 0.0
    max_calls_per_day: int | None = None


class PersistentRateLimiter:
    """Small JSON-backed rate limiter so limits survive separate script runs."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self._lock = Lock()
        if not self.state_path.exists():
            self.state_path.write_text("{}", encoding="utf-8")

    def acquire(self, provider: str, policy: RateLimitPolicy) -> None:
        with self._lock:
            state = self._load_state()
            provider_state = state.setdefault(provider, {})
            today = datetime.now(timezone.utc).date().isoformat()
            last_call_ts = provider_state.get("last_call_ts")
            if last_call_ts and policy.min_interval_seconds > 0:
                elapsed = time.time() - float(last_call_ts)
                remaining = policy.min_interval_seconds - elapsed
                if remaining > 0:
                    time.sleep(remaining)
            if policy.max_calls_per_day is not None:
                calls_by_day = provider_state.setdefault("calls_by_day", {})
                calls_today = int(calls_by_day.get(today, 0))
                if calls_today >= policy.max_calls_per_day:
                    raise RateLimitExceeded(
                        f"{provider} daily quota reached ({policy.max_calls_per_day} calls/day)."
                    )
                calls_by_day[today] = calls_today + 1
            provider_state["last_call_ts"] = time.time()
            self._save_state(state)

    def _load_state(self) -> dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


class RawDataStore:
    """Persists raw provider payloads under data/raw with provider/date partitioning."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def persist(
        self,
        provider: str,
        endpoint: str,
        payload: Any,
        entity_key: str | None = None,
    ) -> tuple[Path, str]:
        timestamp = utc_now()
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        directory = (
            self.settings.raw_data_dir
            / provider
            / f"{dt.year:04d}"
            / f"{dt.month:02d}"
            / f"{dt.day:02d}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        safe_key = _sanitize_path_component(entity_key or "payload")
        file_name = f"{endpoint}_{safe_key}_{dt.strftime('%H%M%S')}.json"
        file_path = directory / file_name
        body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
        file_path.write_text(body, encoding="utf-8")
        checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
        return file_path, checksum


class BaseAPIClient:
    """Common API client with retries and persistent rate limiting."""

    provider_name: str = "base"
    base_url: str = ""
    rate_limit_policy: RateLimitPolicy = RateLimitPolicy()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rate_limiter = PersistentRateLimiter(settings.rate_limit_state_path)
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.mount("http://", HTTPAdapter(max_retries=retries))
        return session

    def request(
        self,
        path: str = "",
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        self.rate_limiter.acquire(self.provider_name, self.rate_limit_policy)
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}" if path else self.base_url
        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=self.settings.requests_timeout_seconds,
        )
        if response.status_code >= 400:
            raise APIClientError(
                f"{self.provider_name} returned HTTP {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise APIClientError(f"{self.provider_name} returned non-JSON response.") from exc
        self.validate_payload(payload)
        return payload

    def validate_payload(self, payload: Any) -> None:
        """Override in subclasses for provider-specific error validation."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp without microseconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_utc_timestamp(
    value: str,
    source_timezone: str = "UTC",
    *,
    date_only_to_midnight: bool = True,
) -> str:
    """Convert a source timestamp or date string to UTC."""

    raw_value = value.strip()
    if len(raw_value) == 10 and date_only_to_midnight:
        dt = datetime.fromisoformat(raw_value).replace(
            tzinfo=ZoneInfo(source_timezone),
            hour=0,
            minute=0,
            second=0,
        )
    else:
        normalized = raw_value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(source_timezone))
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def trading_date_from_timestamp(timestamp_utc: str) -> str:
    """Derive the trading date from a UTC timestamp."""

    dt = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    return dt.date().isoformat()


def coerce_float(value: Any) -> float | None:
    if value in (None, "", "."):
        return None
    return float(value)


def coerce_int(value: Any) -> int | None:
    if value in (None, "", "."):
        return None
    return int(float(value))


def safe_json_loads(value: str | list[Any] | dict[str, Any] | None) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _sanitize_path_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)[:80]
