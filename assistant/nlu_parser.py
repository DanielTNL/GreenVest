"""Regex-first NLU parser for English and Dutch assistant queries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


RISK_KEYWORDS = {
    "volatility": ("volatility", "volatiliteit"),
    "sharpe": ("sharpe",),
    "sortino": ("sortino",),
    "beta": ("beta",),
    "value_at_risk": ("var", "value at risk", "waarde op risico"),
    "conditional_value_at_risk": ("cvar", "conditional var"),
    "max_drawdown": ("drawdown", "maximum drawdown", "maximale drawdown"),
}

HORIZON_KEYWORDS = {
    "daily": ("daily", "day", "today", "dagelijks", "dag", "vandaag"),
    "weekly": ("weekly", "week", "wekelijkse", "wekelijks", "weekelijks"),
    "monthly": ("monthly", "month", "maandelijkse", "maandelijks", "maand"),
}

SYMBOL_ALIASES = {
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "apple": "AAPL",
    "asml": "ASML",
    "google": "GOOGL",
    "microsoft": "MSFT",
    "meta": "META",
    "nvidia": "NVDA",
    "philips": "PHG",
    "shell": "SHEL",
    "tesla": "TSLA",
}

ENGLISH_HINTS = {"show", "create", "run", "today", "weekly", "monthly", "basket", "simulation"}
DUTCH_HINTS = {"toon", "maak", "voorspel", "vandaag", "wekelijks", "maandelijks", "mandje", "portefeuille"}
RECOMMENDATION_HINTS = (
    "should i buy",
    "what should i invest in",
    "recommend a stock",
    "geef mij koopadvies",
    "moet ik kopen",
    "welke aandelen moet ik kopen",
)


@dataclass(slots=True)
class ParsedIntent:
    """Structured representation of a chat request."""

    name: str
    language: str
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


def detect_language(user_message: str) -> str:
    text = user_message.lower()
    dutch_score = sum(1 for hint in DUTCH_HINTS if hint in text)
    english_score = sum(1 for hint in ENGLISH_HINTS if hint in text)
    return "nl" if dutch_score > english_score else "en"


def extract_symbols(user_message: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    lowered = user_message.lower()
    for match in re.finditer(r"\b[A-Z]{1,5}\b", user_message):
        matches.append((match.start(), match.group(0)))
    for alias, symbol in SYMBOL_ALIASES.items():
        for match in re.finditer(rf"\b{re.escape(alias)}\b", lowered):
            matches.append((match.start(), symbol))
    symbols: list[str] = []
    seen: set[str] = set()
    for _, symbol in sorted(matches, key=lambda item: item[0]):
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def parse_user_message(user_message: str) -> ParsedIntent:
    text = user_message.strip()
    lowered = text.lower()
    language = detect_language(text)
    symbols = extract_symbols(text)

    if any(hint in lowered for hint in RECOMMENDATION_HINTS):
        return ParsedIntent("guardrail", language, confidence=0.98)

    if _contains_any(lowered, ("create", "make", "maak", "creëer")) and _contains_any(
        lowered, ("basket", "portfolio", "mandje", "portefeuille")
    ):
        basket_name = _extract_named_value(text, "basket")
        return ParsedIntent(
            "create_basket",
            language,
            entities={
                "basket_name": basket_name or _derive_basket_name(text),
                "symbols": symbols,
                "equal_weight": _contains_any(lowered, ("equal", "equally", "gelijke", "gelijk", "evenly")),
            },
            confidence=0.92 if symbols else 0.6,
        )

    if _contains_any(lowered, ("simulation", "simulate", "backtest", "simulatie", "simuleren")):
        return ParsedIntent(
            "run_simulation",
            language,
            entities={
                "symbols": symbols,
                "basket_name": _extract_named_value(text, "portfolio") or _extract_named_value(text, "basket"),
                "horizon_unit": _extract_horizon(lowered),
            },
            confidence=0.88,
        )

    metric_key = _extract_metric(lowered)
    if metric_key is not None:
        return ParsedIntent(
            "calculate_risk_metrics",
            language,
            entities={"metric_key": metric_key, "symbol": symbols[0] if symbols else None},
            confidence=0.9 if symbols else 0.65,
        )

    if _contains_any(lowered, ("forecast", "predict", "prediction", "voorspel", "prognose")):
        return ParsedIntent(
            "predict_future_returns",
            language,
            entities={"symbol": symbols[0] if symbols else None, "horizon_unit": _extract_horizon(lowered)},
            confidence=0.86,
        )

    if _contains_any(lowered, ("ingest", "etl", "refresh data", "refresh", "ververs", "haal data op")):
        return ParsedIntent("run_full_etl", language, confidence=0.82)

    if symbols or _contains_any(lowered, ("price", "stock", "market data", "koers", "aandeel", "marktdata")):
        return ParsedIntent(
            "get_market_data",
            language,
            entities={"symbol": symbols[0] if symbols else None},
            confidence=0.7 if symbols else 0.45,
        )

    return ParsedIntent("unknown", language, confidence=0.1)


def infer_tool_name(user_message: str) -> str | None:
    intent = parse_user_message(user_message)
    return None if intent.name == "unknown" else intent.name


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def _extract_metric(text: str) -> str | None:
    for metric_key, aliases in RISK_KEYWORDS.items():
        if _contains_any(text, aliases):
            return metric_key
    return None


def _extract_horizon(text: str) -> str:
    for horizon, aliases in HORIZON_KEYWORDS.items():
        if _contains_any(text, aliases):
            return horizon
    return "weekly"


def _extract_named_value(text: str, fallback_kind: str) -> str | None:
    patterns = (
        r"""(?:named|called|genaamd)\s+["']?([^"']+)["']?""",
        rf"""{re.escape(fallback_kind)}\s+named\s+["']?([^"']+)["']?""",
        rf"""{re.escape(fallback_kind)}\s+genaamd\s+["']?([^"']+)["']?""",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return value.rstrip("?.!,")
    return None


def _derive_basket_name(text: str) -> str:
    match = re.search(
        r"""(?:create|make|maak|creëer)\s+(?:a|an|een)?\s*([A-Za-z][A-Za-z\s&-]+?)\s+(?:basket|portfolio|mandje|portefeuille)""",
        text,
        re.IGNORECASE,
    )
    if not match:
        return "Custom Basket"
    stem = match.group(1).strip().title()
    return f"{stem} Basket"
