"""Helpers for deriving file-system paths for run artifacts."""

from __future__ import annotations

from pathlib import Path

from rag_eval.shared.models import RunArtifactPaths


def build_artifact_paths(output_dir: Path, run_id: str) -> RunArtifactPaths:
    """Build the canonical artifact file paths for a single evaluation run."""
    run_dir = output_dir / run_id
    return RunArtifactPaths(
        root_dir=run_dir,
        scenario_snapshot=run_dir / "scenario.snapshot.yaml",
        scores_csv=run_dir / "scores.csv",
        invalid_csv=run_dir / "invalid.csv",
        summary_md=run_dir / "summary.md",
        metadata_json=run_dir / "metadata.json",
    )
