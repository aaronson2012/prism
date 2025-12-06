from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type


log = logging.getLogger(__name__)


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class OpenRouterConfig:
    api_key: str
    default_model: str
    fallback_model: str
    site_url: str | None = None
    app_name: str | None = None
    timeout_seconds: float = 60.0


class OpenRouterError(Exception):
    pass


class OpenRouterClient:
    def __init__(self, cfg: OpenRouterConfig) -> None:
        self.cfg = cfg
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        if cfg.site_url:
            headers["HTTP-Referer"] = cfg.site_url
        if cfg.app_name:
            headers["X-Title"] = cfg.app_name

        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers=headers,
            timeout=cfg.timeout_seconds,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        reraise=True,
        wait=wait_exponential_jitter(initial=1, max=8),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
    )
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Calls OpenRouter Chat Completions API and returns (text, meta).
        On certain failures, retries with fallback model.
        """

        chosen_model = model or self.cfg.default_model
        try:
            text, meta = await self._chat_completion_once(messages, chosen_model, temperature, max_tokens)
            return text, meta
        except (OpenRouterError, httpx.HTTPError, httpx.TimeoutException, httpx.TransportError) as e:
            log.warning("OpenRouter primary model failed (%s): %s; trying fallback %s", chosen_model, e, self.cfg.fallback_model)
            # Attempt fallback once without re-raising via retry decorator.
            try:
                text, meta = await self._chat_completion_once(messages, self.cfg.fallback_model, temperature, max_tokens)
                return text, meta
            except (OpenRouterError, httpx.HTTPError, httpx.TimeoutException, httpx.TransportError) as fallback_error:
                log.error("OpenRouter fallback model also failed (%s): %s", self.cfg.fallback_model, fallback_error)
                raise OpenRouterError(f"Both primary ({chosen_model}) and fallback ({self.cfg.fallback_model}) models failed. Last error: {fallback_error}") from fallback_error

    async def _chat_completion_once(
        self,
        messages: list[dict[str, Any]],
        model: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        resp = await self._client.post("/chat/completions", content=json.dumps(payload))
        request_id = resp.headers.get("x-request-id")
        data: dict[str, Any] | None = None
        try:
            data = resp.json()
        except json.JSONDecodeError:
            # Read response text for error details before raising
            try:
                response_text = resp.text[:500]  # Limit length for logging
                log.error("OpenRouter returned non-JSON response, status=%s id=%s body=%s", resp.status_code, request_id, response_text)
            except Exception:
                log.error("OpenRouter returned non-JSON response, status=%s id=%s (could not read body)", resp.status_code, request_id)
            # Don't call raise_for_status as it may mask the real issue
            raise OpenRouterError(f"Invalid JSON from OpenRouter (status={resp.status_code})")

        if resp.status_code >= 400:
            # Provide meaningful error details.
            if data is None:
                raise OpenRouterError(f"OpenRouter error {resp.status_code}: No response data")
            error_obj = data.get("error") if isinstance(data.get("error"), dict) else {}
            message = error_obj.get("message") or data.get("message") or str(data)[:200]
            raise OpenRouterError(f"OpenRouter error {resp.status_code}: {message}")

        # Validate response structure
        if not data:
            raise OpenRouterError("Empty response from OpenRouter")

        choices = data.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise OpenRouterError(f"Malformed response from OpenRouter: missing choices: {data}")

        try:
            choice = choices[0]
            message_obj = choice.get("message") or {}
            text = message_obj.get("content") or ""
            # Ensure text is a string (some APIs return None or other types)
            if not isinstance(text, str):
                text = str(text) if text is not None else ""
        except (KeyError, TypeError, IndexError) as exc:
            raise OpenRouterError(f"Malformed response from OpenRouter: {data}") from exc

        meta = {
            "request_id": request_id,
            "model": data.get("model", model),
            "usage": data.get("usage"),
        }
        return text, meta

