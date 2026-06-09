"""Compatibility CLI for running offline evaluations without YAML scenarios."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from rag_eval.execution.runner import run_scenario
from rag_eval.settings import EvaluationSettings


def parse_args(settings: EvaluationSettings) -> argparse.Namespace:
    """Parse compatibility CLI arguments using defaults from application settings."""
    parser = argparse.ArgumentParser(
        description="Run offline Ragas evaluation with a compatibility CLI."
    )
    parser.add_argument("--input", required=True, help="Path to a CSV or XLSX file.")
    parser.add_argument(
        "--output",
        default="runs/offline-compat",
        help="Directory where the run artifacts will be written.",
    )
    parser.add_argument(
        "--judge-model",
        default=settings.ragas_judge_model,
        help="OpenAI judge model used by Ragas.",
    )
    parser.add_argument(
        "--embedding-model",
        default=settings.ragas_embedding_model,
        help="OpenAI embedding model used for Ragas.",
    )
    parser.add_argument(
        "--batch-size",
        default=settings.batch_size,
        type=int,
        help="Maximum number of samples scored concurrently.",
    )
    parser.add_argument(
        "--max-samples",
        default=None,
        type=int,
        help="Optional cap for quick iteration.",
    )
    return parser.parse_args()


def build_compat_scenario_file(args: argparse.Namespace) -> Path:
    """Build a temporary scenario file that maps legacy CLI flags to the new runner."""
    output_dir = Path(args.output)
    if output_dir.suffix.lower() == ".csv":
        output_dir = output_dir.parent / output_dir.stem

    # Materialize the legacy CLI input as a standard scenario so the runner stays unified.
    scenario = {
        "scenario_name": "offline-compat-cli",
        "mode": "offline",
        "app_adapter": None,
        "dataset": str(Path(args.input).resolve()),
        "judge_model": args.judge_model,
        "embedding_model": args.embedding_model,
        "metrics": [
            "faithfulness",
            "answer_relevancy",
            "context_recall",
            "context_precision",
        ],
        "output_dir": str(output_dir.resolve()),
        "runtime": {
            "batch_size": args.batch_size,
            "max_samples": args.max_samples,
        },
    }
    scenario_file = output_dir.resolve().parent / ".offline-compat-scenario.yaml"
    scenario_file.write_text(
        yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return scenario_file


def main() -> None:
    """Run the compatibility CLI and print the artifact location when it finishes."""
    settings = EvaluationSettings()
    args = parse_args(settings)
    scenario_file = build_compat_scenario_file(args)
    result = run_scenario(str(scenario_file), settings=settings)
    print(f"Offline Ragas evaluation complete: {result.scenario.output_dir}")


if __name__ == "__main__":
    main()
