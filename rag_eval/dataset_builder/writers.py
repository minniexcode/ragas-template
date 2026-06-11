"""Artifact writers for dataset build runs."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from rag_eval.shared.utils import ensure_directory

from .models import DatasetBuildArtifactPaths, DatasetBuildResult


def build_artifact_paths(root_dir: Path) -> DatasetBuildArtifactPaths:
    """Construct canonical output paths for one dataset build run."""
    return DatasetBuildArtifactPaths(
        root_dir=root_dir,
        documents_jsonl=root_dir / "documents.jsonl",
        semantic_blocks_jsonl=root_dir / "semantic_blocks.jsonl",
        source_chunks_jsonl=root_dir / "source_chunks.jsonl",
        dataset_draft_csv=root_dir / "dataset_draft.csv",
        parse_failures_csv=root_dir / "parse_failures.csv",
        metadata_json=root_dir / "metadata.json",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a list of dictionaries as JSON Lines."""
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    """Write flat records into a CSV file, including list values as JSON strings."""
    normalized_rows: list[dict[str, Any]] = []
    resolved_fieldnames = list(fieldnames or [])
    for row in rows:
        normalized_row: dict[str, Any] = {}
        for key, value in row.items():
            if key not in resolved_fieldnames:
                resolved_fieldnames.append(key)
            if isinstance(value, list):
                normalized_row[key] = json.dumps(value, ensure_ascii=False)
            else:
                normalized_row[key] = value
        normalized_rows.append(normalized_row)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=resolved_fieldnames or ["placeholder"])
        writer.writeheader()
        if normalized_rows:
            writer.writerows(normalized_rows)


def _write_latest_alias_assets(result: DatasetBuildResult) -> None:
    """Publish stable alias files so sample scenarios can target the latest build output."""
    latest_dir = result.job.artifact_dir / "latest"
    ensure_directory(latest_dir)

    # Keep the canonical run directory and also expose a stable entrypoint for tutorials.
    shutil.copyfile(result.artifact_paths.source_chunks_jsonl, latest_dir / "source_chunks.jsonl")
    shutil.copyfile(result.artifact_paths.dataset_draft_csv, latest_dir / "dataset_draft.csv")
    shutil.copyfile(result.artifact_paths.metadata_json, latest_dir / "metadata.json")


def write_dataset_build_artifacts(result: DatasetBuildResult) -> None:
    """Persist dataset build outputs and metadata to disk."""
    artifact_paths = result.artifact_paths
    ensure_directory(artifact_paths.root_dir)
    ensure_directory(result.job.dataset_path.parent)

    _write_jsonl(artifact_paths.documents_jsonl, [item.to_record() for item in result.documents])
    _write_jsonl(
        artifact_paths.semantic_blocks_jsonl,
        [block.to_record() for item in result.documents for block in item.semantic_blocks],
    )
    _write_jsonl(
        artifact_paths.source_chunks_jsonl,
        [chunk.to_record() for item in result.documents for chunk in item.source_chunks],
    )

    draft_rows = [sample.to_record() for sample in result.draft_samples]
    _write_csv(
        artifact_paths.dataset_draft_csv,
        draft_rows,
        fieldnames=[
            "sample_id",
            "question",
            "ground_truth",
            "scenario",
            "language",
            "doc_id",
            "doc_name",
            "section_path",
            "page_start",
            "page_end",
            "source_chunk_ids",
            "question_type",
            "difficulty",
            "review_status",
            "review_notes",
        ],
    )
    _write_csv(
        result.job.dataset_path,
        draft_rows,
        fieldnames=[
            "sample_id",
            "question",
            "ground_truth",
            "scenario",
            "language",
            "doc_id",
            "doc_name",
            "section_path",
            "page_start",
            "page_end",
            "source_chunk_ids",
            "question_type",
            "difficulty",
            "review_status",
            "review_notes",
        ],
    )
    _write_csv(
        artifact_paths.parse_failures_csv,
        [item.to_record() for item in result.parse_failures],
        fieldnames=["file_path", "error"],
    )

    metadata = {
        "run_id": result.run_id,
        "job": result.job.snapshot(),
        "stats": {
            "documents_processed": len(result.documents),
            "draft_samples": len(result.draft_samples),
            "parse_failures": len(result.parse_failures),
        },
    }
    artifact_paths.metadata_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_latest_alias_assets(result)
