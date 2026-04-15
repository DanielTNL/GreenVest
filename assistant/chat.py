"""Chat assistant wrapper that uses the backend service layer only."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .nlu_parser import ParsedIntent, parse_user_message
from .openai_client import OpenAIChatClient, OpenAIChatError

if TYPE_CHECKING:
    from api.service import AppService


class ChatAssistant:
    """Interprets chat messages and routes them to backend capabilities."""

    def __init__(self, service: "AppService", llm_client: OpenAIChatClient | None = None) -> None:
        self.service = service
        settings = getattr(getattr(service, "repository", None), "settings", None)
        self.llm_client = llm_client or (OpenAIChatClient(settings) if settings is not None else None)

    def handle_message(self, message: str) -> dict[str, Any]:
        intent = parse_user_message(message)
        if intent.name == "guardrail":
            response = {
                "reply": _t(
                    intent.language,
                    "I can help with market data, risk metrics, and scenario analysis, but I can’t give personalised investment advice. If you want, I can compare risk, volatility, and recent forecasts for a few symbols so you can make your own decision.",
                    "Ik kan helpen met marktdata, risicomaatstaven en scenario-analyses, maar ik kan geen persoonlijk beleggingsadvies geven. Ik kan wel risico, volatiliteit en recente verwachtingen voor een paar symbolen vergelijken zodat je zelf een beslissing kunt nemen.",
                ),
                "actions": [
                    {"title": _t(intent.language, "Compare AAPL and MSFT", "Vergelijk AAPL en MSFT"), "prompt": "Compare AAPL and MSFT risk metrics."}
                ],
                "intent": intent.name,
            }
            return self._finalize_response(message, intent, response)
        try:
            response = self._dispatch(intent)
        except Exception as exc:
            response = {
                "reply": _t(
                    intent.language,
                    f"I hit a backend error while handling that request: {exc}",
                    f"Ik liep tegen een backendfout aan bij deze aanvraag: {exc}",
                ),
                "actions": [],
                "intent": intent.name,
            }
        return self._finalize_response(message, intent, response)

    def _dispatch(self, intent: ParsedIntent) -> dict[str, Any]:
        if intent.name == "calculate_risk_metrics":
            symbol = intent.entities.get("symbol")
            if not symbol:
                return self._missing_symbol(intent)
            detail = self.service.get_stock_detail(symbol)
            risk_metrics = detail.get("risk_metrics") or {}
            metric_key = intent.entities.get("metric_key")
            metric_value = risk_metrics.get(metric_key)
            label = metric_key.replace("_", " ") if metric_key else "risk metric"
            reply = _t(
                intent.language,
                f"Latest {label} for {symbol.upper()} is {self.service.format_metric(metric_key, metric_value)}.",
                f"De nieuwste {label} voor {symbol.upper()} is {self.service.format_metric(metric_key, metric_value)}.",
            )
            return {
                "reply": reply,
                "actions": [
                    {
                        "title": _t(intent.language, "Run weekly simulation", "Start wekelijkse simulatie"),
                        "prompt": f"Run a weekly simulation for {symbol.upper()}",
                    }
                ],
                "intent": intent.name,
                "data": {"symbol": symbol.upper(), "risk_metrics": risk_metrics},
            }
        if intent.name == "create_basket":
            symbols = intent.entities.get("symbols") or []
            if not symbols:
                return {
                    "reply": _t(
                        intent.language,
                        "I need at least one stock symbol to create a basket.",
                        "Ik heb minstens één aandelensymbool nodig om een mandje te maken.",
                    ),
                    "actions": [],
                    "intent": intent.name,
                }
            basket = self.service.create_basket(
                name=intent.entities["basket_name"],
                description=_t(intent.language, "Created from chat assistant.", "Aangemaakt via chatassistent."),
                symbols=symbols,
                equal_weight=bool(intent.entities.get("equal_weight", True)),
            )
            return {
                "reply": _t(
                    intent.language,
                    f"Created basket {basket['name']} with {', '.join(symbols)}.",
                    f"Mandje {basket['name']} is aangemaakt met {', '.join(symbols)}.",
                ),
                "actions": [
                    {
                        "title": _t(intent.language, "Run weekly simulation", "Start wekelijkse simulatie"),
                        "prompt": f"Run a weekly simulation for the portfolio named '{basket['name']}'",
                    }
                ],
                "intent": intent.name,
                "data": basket,
            }
        if intent.name in {"run_simulation", "predict_future_returns"}:
            symbol = intent.entities.get("symbols", [None])[0]
            basket_name = intent.entities.get("basket_name")
            if basket_name:
                basket = self.service.find_basket_by_name(str(basket_name))
                if basket is None:
                    return {
                        "reply": _t(
                            intent.language,
                            f"I couldn't find a basket named {basket_name}.",
                            f"Ik kon geen mandje vinden met de naam {basket_name}.",
                        ),
                        "actions": [],
                        "intent": intent.name,
                    }
                result = self.service.run_simulation(
                    asset_kind="basket",
                    asset_identifier=str(basket["basket_id"]),
                    horizon_unit=intent.entities.get("horizon_unit", "weekly"),
                )
                name = basket["name"]
            elif symbol:
                result = self.service.run_simulation(
                    asset_kind="stock",
                    asset_identifier=symbol,
                    horizon_unit=intent.entities.get("horizon_unit", "weekly"),
                )
                name = symbol.upper()
            else:
                return self._missing_symbol(intent)
            return {
                "reply": _t(
                    intent.language,
                    f"{intent.entities.get('horizon_unit', 'weekly').title()} simulation for {name} predicts {self.service.format_percent(result['predicted_portfolio_return'])} with realised return {self.service.format_percent(result['actual_portfolio_return'])}.",
                    f"De {intent.entities.get('horizon_unit', 'weekly')} simulatie voor {name} voorspelt {self.service.format_percent(result['predicted_portfolio_return'])} met een gerealiseerd rendement van {self.service.format_percent(result['actual_portfolio_return'])}.",
                ),
                "actions": [
                    {
                        "title": _t(intent.language, "Show alerts", "Toon waarschuwingen"),
                        "prompt": "Show me the latest system alerts.",
                    }
                ],
                "intent": intent.name,
                "data": result,
            }
        if intent.name == "get_market_data":
            symbol = intent.entities.get("symbol")
            if not symbol:
                return self._missing_symbol(intent)
            detail = self.service.get_stock_detail(symbol)
            latest_close = detail.get("latest_close")
            return {
                "reply": _t(
                    intent.language,
                    f"{symbol.upper()} last closed at {self.service.format_currency(latest_close)} and has {len(detail.get('price_history', []))} recent price points available.",
                    f"{symbol.upper()} sloot voor het laatst op {self.service.format_currency(latest_close)} en heeft {len(detail.get('price_history', []))} recente koerspunten beschikbaar.",
                ),
                "actions": [
                    {
                        "title": _t(intent.language, "Show volatility", "Toon volatiliteit"),
                        "prompt": f"Show me today's volatility for {symbol.upper()}",
                    }
                ],
                "intent": intent.name,
                "data": detail,
            }
        if intent.name == "run_full_etl":
            return {
                "reply": _t(
                    intent.language,
                    "The chat assistant can’t run ingestion jobs directly from the app UI yet, but the local API is ready for data refresh orchestration from the backend scheduler.",
                    "De chatassistent kan nog geen ETL-taken direct vanuit de app starten, maar de lokale API is wel klaar voor data-refresh via de backend scheduler.",
                ),
                "actions": [],
                "intent": intent.name,
            }
        return {
            "reply": _t(
                intent.language,
                "I can help with stock metrics, basket creation, and simulations. Try: 'show me today's volatility for Apple' or 'create a tech basket with Apple, Microsoft and Google at equal weights'.",
                "Ik kan helpen met aandelenmetrics, mandjes en simulaties. Probeer bijvoorbeeld: 'toon me de volatiliteit van Apple vandaag' of 'maak een tech mandje met Apple, Microsoft en Google met gelijke weging'.",
            ),
            "actions": [],
            "intent": intent.name,
        }

    def _missing_symbol(self, intent: ParsedIntent) -> dict[str, Any]:
        return {
            "reply": _t(
                intent.language,
                "I need a stock symbol or company name to answer that.",
                "Ik heb een aandelensymbool of bedrijfsnaam nodig om dat te beantwoorden.",
            ),
            "actions": [],
            "intent": intent.name,
        }

    def _finalize_response(
        self,
        message: str,
        intent: ParsedIntent,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        ai_mode = "rules"
        if self.llm_client and self.llm_client.is_configured():
            try:
                refined_reply = self.llm_client.generate_reply(
                    user_message=message,
                    language=intent.language,
                    intent_name=intent.name,
                    structured_response=response,
                )
            except OpenAIChatError:
                refined_reply = None
            if refined_reply:
                response["reply"] = refined_reply
                ai_mode = "openai"
        response["ai_mode"] = ai_mode
        return response


def _t(language: str, english: str, dutch: str) -> str:
    return dutch if language == "nl" else english
