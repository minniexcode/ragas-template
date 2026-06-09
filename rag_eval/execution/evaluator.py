"""Core evaluation workflow for offline and online scenarios."""

from __future__ import annotations

import asyncio
from typing import Any

from rag_eval.adapters.base import AppAdapter
from rag_eval.datasets.loader import load_dataset_records
from rag_eval.datasets.normalizers import normalize_records
from rag_eval.execution.concurrency import gather_with_limit
from rag_eval.metrics.pipeline import MetricPipeline
from rag_eval.shared.models import EvaluationResult, InvalidSample, NormalizedSample, Scenario
from rag_eval.shared.utils import utc_now_iso


class Evaluator:
    """Coordinate dataset loading, optional app execution, and metric scoring."""

    def __init__(
        self,
        scenario: Scenario,
        metric_pipeline: MetricPipeline,
        app_adapter: AppAdapter | None = None,
    ):
        """Create an evaluator for one resolved scenario."""
        self.scenario = scenario
        self.metric_pipeline = metric_pipeline
        self.app_adapter = app_adapter

    def evaluate(self) -> EvaluationResult:
        """Execute the full evaluation flow and return the collected results."""
        started_at = utc_now_iso()
        raw_records = load_dataset_records(self.scenario.dataset.path)
        samples, invalid_samples = normalize_records(
            raw_records,
            max_samples=self.scenario.runtime.max_samples,
        )

        if self.scenario.mode == "online":
            # Online mode enriches each sample by calling the target application first.
            samples, online_invalids = asyncio.run(self._enrich_online_samples(samples))
            invalid_samples.extend(online_invalids)

        metric_scores = asyncio.run(
            self.metric_pipeline.score_samples(
                samples,
                max_concurrency=self.scenario.runtime.metric_limit(),
            )
        )
        finished_at = utc_now_iso()
        score_rows = [self._merge_score(sample, score) for sample, score in zip(samples, metric_scores)]
        run_id = finished_at.replace(":", "-")
        return EvaluationResult(
            scenario=self.scenario,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            valid_samples=samples,
            invalid_samples=invalid_samples,
            score_rows=score_rows,
        )

    async def _enrich_online_samples(
        self,
        samples: list[NormalizedSample],
    ) -> tuple[list[NormalizedSample], list[InvalidSample]]:
        """Populate answers and contexts by calling the configured application adapter."""
        if self.app_adapter is None:
            raise ValueError("online mode requires an app adapter.")

        factories = [
            (lambda sample=sample: self.app_adapter.enrich_sample(sample))
            for sample in samples
        ]
        results = await gather_with_limit(factories, self.scenario.runtime.app_limit())

        valid: list[NormalizedSample] = []
        invalid: list[InvalidSample] = []
        for sample in results:
            # Treat incomplete adapter payloads as invalid so reporting stays explicit.
            errors: list[str] = []
            if not sample.answer:
                errors.append("adapter returned empty answer")
            if not sample.contexts:
                errors.append("adapter returned empty contexts")
            if errors:
                invalid.append(
                    InvalidSample(
                        sample_id=sample.sample_id,
                        error="; ".join(errors),
                        raw=sample.raw,
                    )
                )
                continue
            valid.append(sample)
        return valid, invalid

    def _merge_score(self, sample: NormalizedSample, score: Any) -> dict[str, Any]:
        """Combine sample data, metric results, and run metadata into one output row."""
        record = sample.to_record()
        record["contexts"] = sample.contexts
        record.update(score.metrics)
        record["error"] = score.error
        record["judge_model"] = self.scenario.judge_model
        record["embedding_model"] = self.scenario.embedding_model
        record["run_id"] = self.scenario.scenario_name
        return record
