"""Row-level validation helpers for raw dataset records."""

from __future__ import annotations

from typing import Any

from rag_eval.shared.models import Mode


MODE_REQUIRED_FIELDS: dict[Mode, tuple[str, ...]] = {
    "offline": ("question", "contexts", "answer", "ground_truth"),
    "online": ("question", "ground_truth"),
}
OPTIONAL_FIELDS = ("sample_id", "scenario", "language", "retrieval_config")


def validate_required_fields(record: dict[str, Any], mode: Mode) -> list[str]:
    """Return missing required-field errors for a raw dataset record."""
    errors: list[str] = []
    for field in MODE_REQUIRED_FIELDS[mode]:
        if field not in record:
            errors.append(f"missing field: {field}")
    return errors
