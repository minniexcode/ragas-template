"""Writers that persist evaluation outputs as local run artifacts."""

from __future__ import annotations

import json

import pandas as pd
import yaml

from rag_eval.reporting.artifacts import build_artifact_paths
from rag_eval.reporting.summary import build_summary_markdown
from rag_eval.shared.models import EvaluationResult
from rag_eval.shared.utils import ensure_directory


def write_run_artifacts(result: EvaluationResult) -> None:
    """Write all standard run artifacts for a completed evaluation result."""
    artifact_paths = build_artifact_paths(result.scenario.output_dir, result.run_id)
    ensure_directory(artifact_paths.root_dir)

    artifact_paths.scenario_snapshot.write_text(
        yaml.safe_dump(result.scenario.snapshot(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    pd.DataFrame(result.score_rows).to_csv(artifact_paths.scores_csv, index=False)
    pd.DataFrame(
        [sample.to_record() for sample in result.invalid_samples]
    ).to_csv(artifact_paths.invalid_csv, index=False)

    artifact_paths.summary_md.write_text(
        build_summary_markdown(result),
        encoding="utf-8",
    )

    # Keep a compact machine-readable summary alongside the larger CSV and markdown outputs.
    metadata = {
        "run_id": result.run_id,
        "scenario_name": result.scenario.scenario_name,
        "mode": result.scenario.mode,
        "judge_model": result.scenario.judge_model,
        "embedding_model": result.scenario.embedding_model,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "dataset": result.scenario.dataset.path.as_posix(),
        "valid_samples": len(result.valid_samples),
        "invalid_samples": len(result.invalid_samples),
    }
    artifact_paths.metadata_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
