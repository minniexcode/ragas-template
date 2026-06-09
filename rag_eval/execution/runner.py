"""High-level scenario runner used by the package and CLI entrypoints."""

from __future__ import annotations

from rag_eval.adapters.http import HttpAppAdapter
from rag_eval.adapters.python import PythonFunctionAdapter
from rag_eval.config.loader import load_scenario
from rag_eval.metrics.factory import build_metric_pipeline
from rag_eval.reporting.writers import write_run_artifacts
from rag_eval.settings import EvaluationSettings
from rag_eval.shared.models import Scenario

from .evaluator import Evaluator


def build_adapter(scenario: Scenario):
    """Instantiate the adapter required by the resolved scenario, if any."""
    if scenario.app_adapter is None:
        return None
    if scenario.app_adapter.type == "http":
        return HttpAppAdapter(scenario.app_adapter)
    if scenario.app_adapter.type == "python":
        return PythonFunctionAdapter(scenario.app_adapter)
    raise ValueError(f"Unsupported adapter type: {scenario.app_adapter.type}")


def run_scenario(
    scenario_path: str,
    settings: EvaluationSettings | None = None,
):
    """Run one scenario end to end and persist its reporting artifacts."""
    settings = settings or EvaluationSettings()
    if not settings.openai_api_key:
        raise EnvironmentError("OPENAI_API_KEY must be set before running the evaluator.")

    scenario = load_scenario(scenario_path)
    adapter = build_adapter(scenario)
    pipeline = build_metric_pipeline(scenario, settings)
    evaluator = Evaluator(scenario=scenario, metric_pipeline=pipeline, app_adapter=adapter)
    result = evaluator.evaluate()
    write_run_artifacts(result)
    return result
