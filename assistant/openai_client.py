"""Lightweight OpenAI-backed reply generation for the app assistant."""

from __future__ import annotations

import json
from typing import Any

import requests

from config import Settings


class OpenAIChatError(RuntimeError):
    """Raised when the OpenAI chat integration fails."""


class OpenAIChatClient:
    """Thin REST client for generating assistant responses through OpenAI."""

    api_url = "https://api.openai.com/v1/chat/completions"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    def generate_reply(
        self,
        *,
        user_message: str,
        language: str,
        intent_name: str,
        structured_response: dict[str, Any],
    ) -> str | None:
        if not self.is_configured():
            return None

        payload = {
            "model": self.settings.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are GreenVest, a concise educational investment app assistant. "
                        "Use only the structured response and user message provided. "
                        "You may explain finance concepts in general terms, but do not invent live market facts. "
                        "Never give personalized financial advice or say the user should buy or sell a security. "
                        "If data is missing, say so plainly. Match the requested language. "
                        "Keep the answer short, natural, and mobile-friendly. Return plain text only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "language": language,
                            "intent": intent_name,
                            "user_message": user_message,
                            "structured_response": structured_response,
                        },
                        ensure_ascii=True,
                        default=str,
                    ),
                },
            ],
        }
        try:
            response = self.session.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=min(self.settings.requests_timeout_seconds, 8),
            )
        except requests.RequestException as exc:
            raise OpenAIChatError(f"OpenAI request failed: {exc}") from exc
        if response.status_code >= 400:
            raise OpenAIChatError(f"OpenAI returned HTTP {response.status_code}: {response.text[:300]}")
        try:
            body = response.json()
        except ValueError as exc:
            raise OpenAIChatError("OpenAI returned non-JSON output.") from exc

        choices = body.get("choices") or []
        if not choices:
            raise OpenAIChatError("OpenAI returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        text = _coerce_content_to_text(content)
        if not text:
            raise OpenAIChatError("OpenAI returned an empty assistant message.")
        return text.strip()

    def generate_json_object(
        self,
        *,
        system_instruction: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.is_configured():
            return None
        payload = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": json.dumps(input_payload, ensure_ascii=True, default=str),
                },
            ],
        }
        try:
            response = self.session.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=min(self.settings.requests_timeout_seconds, 8),
            )
        except requests.RequestException as exc:
            raise OpenAIChatError(f"OpenAI request failed: {exc}") from exc
        if response.status_code >= 400:
            raise OpenAIChatError(f"OpenAI returned HTTP {response.status_code}: {response.text[:300]}")
        try:
            body = response.json()
        except ValueError as exc:
            raise OpenAIChatError("OpenAI returned non-JSON output.") from exc
        choices = body.get("choices") or []
        if not choices:
            raise OpenAIChatError("OpenAI returned no choices.")
        message = choices[0].get("message") or {}
        content = _coerce_content_to_text(message.get("content"))
        if not content:
            raise OpenAIChatError("OpenAI returned empty structured output.")
        try:
            return json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as exc:
            raise OpenAIChatError("OpenAI returned invalid JSON content.") from exc


def _coerce_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif isinstance(item.get("text"), dict) and isinstance(item["text"].get("value"), str):
                    text_parts.append(item["text"]["value"])
        return "\n".join(part for part in text_parts if part)
    return ""


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text
