from __future__ import annotations

import argparse

from rag_eval.execution.runner import run_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a RAG evaluation scenario.")
    parser.add_argument(
        "--scenario",
        required=True,
        help="Path to a YAML scenario file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_scenario(args.scenario)
    print(f"Completed run: {result.scenario.output_dir}")


if __name__ == "__main__":
    main()
