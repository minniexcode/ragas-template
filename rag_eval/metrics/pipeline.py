"""Execution pipeline for scoring normalized samples with RAGAS metrics."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any

from rag_eval.shared.models import MetricScore, NormalizedSample


@dataclass(slots=True)
class MetricPipeline:
    """Score one or many normalized samples against a configured metric set."""

    metrics: dict[str, Any]
    metric_timeout_seconds: float | None = None

    async def score_sample(self, sample: NormalizedSample) -> MetricScore:
        """Score a single sample and capture metric-level failures without aborting."""
        results = {name: math.nan for name in self.metrics}
        errors: list[str] = []

        for name, metric in self.metrics.items():
            try:
                result = await self._run_metric(name, metric, sample)
                results[name] = float(result.value)
            except Exception as exc:
                errors.append(f"{name}: {exc}")
        return MetricScore(metrics=results, error=" | ".join(errors))

    async def _run_metric(self, name: str, metric: Any, sample: NormalizedSample) -> Any:
        """Dispatch one metric call with the argument shape expected by that metric."""
        timeout = None
        if self.metric_timeout_seconds is not None:
            timeout = max(1.0, float(self.metric_timeout_seconds))

        if name == "faithfulness":
            coroutine = metric.ascore(
                user_input=sample.question,
                response=sample.answer,
                retrieved_contexts=sample.contexts,
            )
        elif name == "answer_relevancy":
            coroutine = metric.ascore(
                user_input=sample.question,
                response=sample.answer,
            )
        elif name == "context_recall":
            coroutine = metric.ascore(
                user_input=sample.question,
                retrieved_contexts=sample.contexts,
                reference=sample.ground_truth,
            )
        elif name == "context_precision":
            coroutine = metric.ascore(
                user_input=sample.question,
                reference=sample.ground_truth,
                retrieved_contexts=sample.contexts,
            )
        else:
            raise ValueError(f"Unsupported metric: {name}")

        if timeout is None:
            return await coroutine
        return await asyncio.wait_for(coroutine, timeout=timeout)

    async def score_samples(
        self,
        samples: list[NormalizedSample],
        max_concurrency: int,
    ) -> list[MetricScore]:
        """Score all samples while respecting the configured concurrency limit."""
        semaphore = asyncio.Semaphore(max(1, max_concurrency))

        async def guarded(sample: NormalizedSample) -> MetricScore:
            """Throttle a single sample-scoring coroutine with the shared semaphore."""
            async with semaphore:
                return await self.score_sample(sample)

        return await asyncio.gather(*(guarded(sample) for sample in samples))
