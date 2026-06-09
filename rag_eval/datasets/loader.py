"""Dataset file readers for supported offline evaluation formats."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_dataset_records(path: Path) -> list[dict[str, Any]]:
    """Load a dataset file into a list of record dictionaries."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    elif suffix == ".jsonl":
        frame = pd.read_json(path, lines=True)
    else:
        raise ValueError(f"Unsupported dataset file type: {path.suffix}")
    return frame.to_dict(orient="records")
