"""Scenario file loading and conversion into internal runtime models."""

from __future__ import annotations

from pathlib import Path

import yaml

from rag_eval.shared.models import AppAdapterConfig, DatasetConfig, RuntimeConfig, Scenario

from .schema import ScenarioModel
from .validators import validate_scenario


def load_scenario(path: str | Path) -> Scenario:
    """Load, validate, and resolve a scenario file into the internal scenario model."""
    scenario_path = Path(path).resolve()
    payload = yaml.safe_load(scenario_path.read_text(encoding="utf-8")) or {}
    model = ScenarioModel.model_validate(payload)
    base_dir = scenario_path.parent

    app_adapter = None
    if model.app_adapter is not None:
        # Convert the validated Pydantic model into the lightweight runtime dataclass.
        app_adapter = AppAdapterConfig(
            type=model.app_adapter.type,
            endpoint=model.app_adapter.endpoint,
            method=model.app_adapter.method,
            timeout_seconds=model.app_adapter.timeout_seconds,
            callable=model.app_adapter.callable,
            request_template=model.app_adapter.request_template,
            response_mapping=model.app_adapter.response_mapping,
            static_kwargs=model.app_adapter.static_kwargs,
        )

    scenario = Scenario(
        scenario_name=model.scenario_name,
        mode=model.mode,
        app_adapter=app_adapter,
        dataset=DatasetConfig(path=model.resolve_path(base_dir, model.dataset)),
        judge_model=model.judge_model,
        embedding_model=model.embedding_model,
        metrics=model.metrics,
        output_dir=model.resolve_path(base_dir, model.output_dir),
        runtime=RuntimeConfig(
            batch_size=model.runtime.batch_size,
            app_concurrency=model.runtime.app_concurrency,
            metric_concurrency=model.runtime.metric_concurrency,
            max_samples=model.runtime.max_samples,
        ),
        source_path=scenario_path,
    )
    # Run cross-field checks after all relative paths have been resolved.
    validate_scenario(scenario)
    return scenario
