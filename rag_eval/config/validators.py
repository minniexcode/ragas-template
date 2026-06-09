"""Cross-field validation helpers for resolved runtime scenarios."""

from __future__ import annotations

from rag_eval.metrics.registry import SUPPORTED_METRICS
from rag_eval.shared.models import Scenario


def validate_scenario(scenario: Scenario) -> None:
    """Validate metric selection and mode-specific runtime constraints."""
    unsupported = [name for name in scenario.metrics if name not in SUPPORTED_METRICS]
    if unsupported:
        supported = ", ".join(sorted(SUPPORTED_METRICS))
        raise ValueError(
            f"Unsupported metrics: {', '.join(unsupported)}. Supported metrics: {supported}"
        )
    if scenario.mode == "offline" and scenario.app_adapter is not None:
        raise ValueError("offline mode should not define app_adapter.")
    if scenario.runtime.batch_size < 1:
        raise ValueError("runtime.batch_size must be >= 1.")
