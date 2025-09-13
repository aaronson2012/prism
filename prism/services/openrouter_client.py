from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type


log = logging.getLogger(__name__)


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class OpenRouterConfig:
    api_key: str
    default_model: str
    fallback_model: str
    site_url: Optional[str] = None
    app_name: Optional[str] = None
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
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Calls OpenRouter Chat Completions API and returns (text, meta).
        On certain failures, retries with fallback model.
        """

        chosen_model = model or self.cfg.default_model
        try:
            text, meta = await self._chat_completion_once(messages, chosen_model, temperature, max_tokens)
            return text, meta
        except Exception as e:
            log.warning("OpenRouter primary model failed (%s): %s; trying fallback %s", chosen_model, e, self.cfg.fallback_model)
            # Attempt fallback once without re-raising via retry decorator.
            text, meta = await self._chat_completion_once(messages, self.cfg.fallback_model, temperature, max_tokens)
            return text, meta

    async def _chat_completion_once(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
    ) -> Tuple[str, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        resp = await self._client.post("/chat/completions", content=json.dumps(payload))
        request_id = resp.headers.get("x-request-id")
        try:
            data = resp.json()
        except json.JSONDecodeError:
            log.error("OpenRouter returned non-JSON response, status=%s id=%s", resp.status_code, request_id)
            resp.raise_for_status()
            raise OpenRouterError("Invalid JSON from OpenRouter")

        if resp.status_code >= 400:
            # Provide meaningful error details.
            message = data.get("error", {}).get("message") or data.get("message") or str(data)[:200]
            raise OpenRouterError(f"OpenRouter error {resp.status_code}: {message}")

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise OpenRouterError(f"Malformed response from OpenRouter: {data}") from exc

        meta = {
            "request_id": request_id,
            "model": data.get("model", model),
            "usage": data.get("usage"),
        }
        return text, meta

