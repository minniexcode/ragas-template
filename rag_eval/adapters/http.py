"""HTTP adapter implementation for online evaluation scenarios."""

from __future__ import annotations

from typing import Any

import httpx

from rag_eval.shared.models import AppAdapterConfig

from .base import AppAdapter


class HttpAppAdapter(AppAdapter):
    """Call an HTTP endpoint and map its JSON response into the normalized adapter shape."""

    def __init__(self, config: AppAdapterConfig):
        """Store the HTTP adapter configuration for later requests."""
        self.config = config

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """Send one HTTP request and return the normalized response payload."""
        payload = dict(self.config.request_template)
        payload["question"] = question
        payload.update(self.config.static_kwargs)
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.request(
                self.config.method.upper(),
                self.config.endpoint or "",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        # Allow scenario config to rename answer/context fields without custom code.
        mapping = self.config.response_mapping or {}
        answer_key = mapping.get("answer", "answer")
        contexts_key = mapping.get("contexts", "contexts")
        return {
            "answer": body.get(answer_key, ""),
            "contexts": body.get(contexts_key, []),
            "raw_response": body,
        }
