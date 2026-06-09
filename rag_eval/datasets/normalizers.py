"""Normalization helpers that convert raw dataset rows into evaluation samples."""

from __future__ import annotations

from typing import Any

from rag_eval.shared.models import InvalidSample, NormalizedSample
from rag_eval.shared.utils import parse_contexts

from .validators import validate_required_fields


def _normalize_text(value: Any) -> str:
    """Convert nullable values into trimmed strings."""
    if value is None:
        return ""
    return str(value).strip()


def normalize_records(
    records: list[dict[str, Any]],
    max_samples: int | None = None,
) -> tuple[list[NormalizedSample], list[InvalidSample]]:
    """Split raw dataset records into valid normalized samples and invalid rows."""
    working_records = records[:max_samples] if max_samples is not None else records
    valid_samples: list[NormalizedSample] = []
    invalid_samples: list[InvalidSample] = []

    for index, raw in enumerate(working_records, start=1):
        sample_id = _normalize_text(raw.get("sample_id")) or f"sample-{index}"
        field_errors = validate_required_fields(raw)
        if field_errors:
            invalid_samples.append(
                InvalidSample(sample_id=sample_id, error="; ".join(field_errors), raw=raw)
            )
            continue

        # Preserve extra columns as metadata so adapters can use them during online runs.
        sample = NormalizedSample(
            sample_id=sample_id,
            question=_normalize_text(raw.get("question")),
            contexts=parse_contexts(raw.get("contexts")),
            answer=_normalize_text(raw.get("answer")),
            ground_truth=_normalize_text(raw.get("ground_truth")),
            scenario=_normalize_text(raw.get("scenario")),
            language=_normalize_text(raw.get("language")),
            retrieval_config=_normalize_text(raw.get("retrieval_config")),
            metadata={
                key: raw[key]
                for key in raw.keys()
                if key
                not in {
                    "sample_id",
                    "question",
                    "contexts",
                    "answer",
                    "ground_truth",
                    "scenario",
                    "language",
                    "retrieval_config",
                }
            },
            raw=raw,
        )

        # Fail fast on blank required values after normalization, even if the columns exist.
        errors: list[str] = []
        if not sample.question:
            errors.append("question is empty")
        if not sample.contexts:
            errors.append("contexts is empty")
        if not sample.answer:
            errors.append("answer is empty")
        if not sample.ground_truth:
            errors.append("ground_truth is empty")

        if errors:
            invalid_samples.append(
                InvalidSample(sample_id=sample.sample_id, error="; ".join(errors), raw=raw)
            )
            continue

        valid_samples.append(sample)

    return valid_samples, invalid_samples
