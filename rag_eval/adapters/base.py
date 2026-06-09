"""Shared adapter interfaces for online application execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rag_eval.shared.models import NormalizedSample


class AppAdapter(ABC):
    """Abstract base class for adapters that fetch answers and contexts from apps."""

    @abstractmethod
    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        """Execute the target application for a single question."""
        raise NotImplementedError

    async def enrich_sample(self, sample: NormalizedSample) -> NormalizedSample:
        """Merge adapter output into an existing normalized sample."""
        response = await self.run(question=sample.question, **sample.metadata)
        answer = str(response.get("answer", "")).strip()
        contexts = response.get("contexts") or []
        # Drop empty context fragments so downstream metrics receive clean lists.
        normalized_contexts = [str(item).strip() for item in contexts if str(item).strip()]
        return NormalizedSample(
            sample_id=sample.sample_id,
            question=sample.question,
            contexts=normalized_contexts,
            answer=answer,
            ground_truth=sample.ground_truth,
            scenario=sample.scenario,
            language=sample.language,
            retrieval_config=sample.retrieval_config,
            metadata={**sample.metadata, "raw_response": response.get("raw_response")},
            raw=sample.raw,
        )
