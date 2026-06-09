"""Factories for OpenAI-backed RAGAS models and metric pipelines."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from rag_eval.compat import ensure_ragas_import_compat
from rag_eval.settings import EvaluationSettings
from rag_eval.shared.models import Scenario

ensure_ragas_import_compat()

from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from .pipeline import MetricPipeline


def build_models(
    judge_model: str,
    embedding_model: str,
    settings: EvaluationSettings,
) -> tuple[Any, Any]:
    """Create the LLM and embedding clients required by the selected RAGAS metrics."""
    client = AsyncOpenAI(**settings.openai_client_kwargs)
    llm = llm_factory(judge_model, client=client)
    embeddings = embedding_factory(provider="openai", model=embedding_model, client=client)
    return llm, embeddings


def build_metric_pipeline(
    scenario: Scenario,
    settings: EvaluationSettings,
) -> MetricPipeline:
    """Build a metric pipeline containing only the metrics requested by the scenario."""
    llm, embeddings = build_models(
        scenario.judge_model,
        scenario.embedding_model,
        settings,
    )
    # Build the full registry once, then slice it by configured metric names.
    registry: dict[str, Any] = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_recall": ContextRecall(llm=llm),
        "context_precision": ContextPrecision(llm=llm),
    }
    return MetricPipeline(metrics={name: registry[name] for name in scenario.metrics})
