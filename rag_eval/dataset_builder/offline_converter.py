"""Utilities for converting draft online datasets into offline smoke-test datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from rag_eval.shared.utils import ensure_directory


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dictionaries."""
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def build_offline_smoke_dataset(
    *,
    draft_dataset_path: Path,
    source_chunks_path: Path,
    output_path: Path,
) -> Path:
    """Derive an offline-evaluable dataset by reusing ground truth as answer and chunk text as contexts."""
    draft_frame = pd.read_csv(draft_dataset_path)
    chunk_rows = _load_jsonl(source_chunks_path)
    chunk_lookup = {str(row["chunk_id"]): row for row in chunk_rows}

    output_rows: list[dict[str, Any]] = []
    for _, row in draft_frame.iterrows():
        chunk_ids = row.get("source_chunk_ids")
        if isinstance(chunk_ids, str):
            parsed_chunk_ids = json.loads(chunk_ids)
        elif isinstance(chunk_ids, list):
            parsed_chunk_ids = chunk_ids
        else:
            parsed_chunk_ids = []

        contexts = [
            str(chunk_lookup[chunk_id]["text"]).strip()
            for chunk_id in parsed_chunk_ids
            if chunk_id in chunk_lookup and str(chunk_lookup[chunk_id]["text"]).strip()
        ]
        ground_truth = str(row.get("ground_truth", "")).strip()
        output_rows.append(
            {
                "sample_id": row.get("sample_id", ""),
                "question": row.get("question", ""),
                "contexts": json.dumps(contexts, ensure_ascii=False),
                "answer": ground_truth,
                "ground_truth": ground_truth,
                "scenario": row.get("scenario", ""),
                "language": row.get("language", ""),
                "retrieval_config": "offline-smoke-from-pdf-build",
                "doc_id": row.get("doc_id", ""),
                "doc_name": row.get("doc_name", ""),
                "section_path": row.get("section_path", ""),
                "page_start": row.get("page_start", ""),
                "page_end": row.get("page_end", ""),
                "source_chunk_ids": row.get("source_chunk_ids", ""),
                "question_type": row.get("question_type", ""),
                "difficulty": row.get("difficulty", ""),
                "review_status": row.get("review_status", ""),
                "review_notes": row.get("review_notes", ""),
            }
        )

    ensure_directory(output_path.parent)
    pd.DataFrame(output_rows).to_csv(output_path, index=False)
    return output_path
