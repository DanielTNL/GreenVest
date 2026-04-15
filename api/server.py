"""Threaded stdlib JSON API for the SwiftUI iOS client."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from assistant.chat import ChatAssistant
from config import Settings
from db import KnowledgeBaseManager, MarketRepository, initialize_knowledge_bases, initialize_market_database

from .service import AppService


class _RequestHandler(BaseHTTPRequestHandler):
    service: AppService
    chat_assistant: ChatAssistant

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                self._send_json(self.service.health())
                return
            if path == "/api/stocks/search":
                query_value = _first(query, "q") or ""
                limit_value = int(_first(query, "limit") or "12")
                self._send_json(self.service.search_stock_catalog(query=query_value, limit=limit_value))
                return
            if path == "/api/stocks/suggestions":
                limit_value = int(_first(query, "limit") or "5")
                self._send_json(self.service.daily_watch_suggestions(limit=limit_value))
                return
            if path == "/api/stocks":
                self._send_json(self.service.list_stocks(query=_first(query, "q")))
                return
            if path.startswith("/api/stocks/"):
                symbol = path.split("/")[-1]
                self._send_json(self.service.get_stock_detail(symbol))
                return
            if path == "/api/baskets":
                self._send_json(self.service.list_baskets())
                return
            if path.startswith("/api/baskets/"):
                basket_id = int(path.split("/")[-1])
                self._send_json(self.service.get_basket_detail(basket_id))
                return
            if path == "/api/simulation-options":
                self._send_json(self.service.simulation_options())
                return
            if path == "/api/simulations/recent":
                self._send_json(self.service.recent_simulations())
                return
            if path == "/api/metrics":
                self._send_json(self.service.get_metrics_snapshot(knowledge_base=_first(query, "knowledge_base") or "working"))
                return
            if path == "/api/macro":
                self._send_json(self.service.get_macro_geopolitics())
                return
            if path == "/api/alerts":
                self._send_json(self.service.get_alerts())
                return
            if path == "/api/diagnostics":
                self._send_json(self.service.get_diagnostics())
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - defensive API boundary
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        payload = self._read_json_body()
        try:
            if path == "/api/stocks/track":
                result = self.service.track_stock(
                    symbol=payload["symbol"],
                    name=payload.get("name"),
                    exchange=payload.get("exchange"),
                )
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/baskets":
                result = self.service.create_basket(
                    name=payload["name"],
                    description=payload.get("description", ""),
                    symbols=list(payload.get("symbols", [])),
                    equal_weight=bool(payload.get("equal_weight", True)),
                )
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/simulations/run":
                result = self.service.run_simulation(
                    asset_kind=payload["asset_kind"],
                    asset_identifier=str(payload["asset_identifier"]),
                    simulation_type=payload.get("simulation_type", "past"),
                    horizon_unit=payload.get("horizon_unit", "weekly"),
                    model_name=payload.get("model_name", "updated_working_model"),
                    initial_capital=float(payload.get("initial_capital", 10000)),
                    start_date=payload.get("start_date"),
                    end_date=payload.get("end_date"),
                )
                self._send_json(result, status=HTTPStatus.CREATED)
                return
            if path == "/api/chat":
                self._send_json(self.chat_assistant.handle_message(str(payload.get("message", ""))))
                return
            if path == "/api/audit/run":
                self._send_json(self.service.run_manual_audit(lookback=int(payload.get("lookback", 252))))
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")
        except KeyError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, f"Missing field: {exc}")
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - defensive API boundary
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            if path.startswith("/api/simulations/"):
                simulation_id = int(path.split("/")[-1])
                self._send_json(self.service.delete_simulation(simulation_id))
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found.")
        except KeyError as exc:
            self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - defensive API boundary
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)


def run_server(
    settings: Settings | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    active_settings = settings or Settings()
    initialize_market_database(active_settings)
    initialize_knowledge_bases(active_settings)
    service = AppService(MarketRepository(active_settings), KnowledgeBaseManager(active_settings))
    chat_assistant = ChatAssistant(service)

    class Handler(_RequestHandler):
        pass

    Handler.service = service
    Handler.chat_assistant = chat_assistant

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        print(f"Local API listening on http://{host}:{port}/api")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key) or []
    return values[0] if values else None


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
