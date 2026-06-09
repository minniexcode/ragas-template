"""Row-level validation helpers for raw dataset records."""

from __future__ import annotations

from typing import Any

REQUIRED_FIELDS = ("question", "contexts", "answer", "ground_truth")
OPTIONAL_FIELDS = ("sample_id", "scenario", "language", "retrieval_config")


def validate_required_fields(record: dict[str, Any]) -> list[str]:
    """Return missing required-field errors for a raw dataset record."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")
    return errors
