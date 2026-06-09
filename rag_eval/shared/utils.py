"""General-purpose helpers shared across configuration, datasets, and reporting."""

from __future__ import annotations

import ast
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def ensure_directory(path: Path) -> None:
    """Create a directory path if it does not already exist."""
    path.mkdir(parents=True, exist_ok=True)


def parse_contexts(value: Any) -> list[str]:
    """Normalize a context payload into a list of non-empty strings."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []

    text = str(value).strip()
    if not text:
        return []

    # Accept serialized lists from CSV exports before falling back to plain text.
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]

    # Preserve paragraph-style context dumps by splitting on blank lines first.
    if "\n\n" in text:
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        if chunks:
            return chunks

    return [text]
