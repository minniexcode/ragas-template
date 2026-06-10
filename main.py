from __future__ import annotations

import argparse

from rag_eval.dataset_builder.runner import run_dataset_build
from rag_eval.execution.runner import run_scenario


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for either evaluation or dataset build workflows."""
    parser = argparse.ArgumentParser(description="Run a RAG evaluation scenario.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--scenario",
        help="Path to a YAML scenario file.",
    )
    group.add_argument(
        "--dataset-build-config",
        help="Path to a YAML dataset build config file.",
    )
    return parser.parse_args()


def main() -> None:
    """Dispatch the CLI call to the requested workflow."""
    args = parse_args()
    if args.dataset_build_config:
        result = run_dataset_build(args.dataset_build_config)
        print(f"Completed dataset build: {result.artifact_paths.root_dir}")
        return

    result = run_scenario(args.scenario)
    print(f"Completed run: {result.scenario.output_dir}")


if __name__ == "__main__":
    main()
