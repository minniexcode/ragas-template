from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rag_eval.compat import ensure_ragas_import_compat

ensure_ragas_import_compat()

from datasets import Dataset
from ragas import evaluate
from ragas.embeddings import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)


REQUIRED_INPUT_COLUMNS = ("question", "contexts", "answer", "ground_truth")
OPTIONAL_INPUT_COLUMNS = ("sample_id", "scenario", "language", "retrieval_config")


@dataclass
class EvaluationRunConfig:
    input_file: Path
    output_file: Path
    judge_model: str
    embedding_model: str
    batch_size: int
    max_samples: int | None


def parse_args() -> EvaluationRunConfig:
    parser = argparse.ArgumentParser(
        description="Run offline Ragas evaluation for exported RAG samples."
    )
    parser.add_argument("--input", required=True, help="Path to a CSV or XLSX file.")
    parser.add_argument(
        "--output",
        default="outputs/ragas_scores.csv",
        help="Where to write the per-sample score CSV.",
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("RAGAS_JUDGE_MODEL", "gpt-4o-mini"),
        help="OpenAI judge model used by Ragas.",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.getenv("RAGAS_EMBEDDING_MODEL", "text-embedding-3-large"),
        help="OpenAI embedding model used for answer relevancy.",
    )
    parser.add_argument(
        "--batch-size",
        default=int(os.getenv("BATCH_SIZE", "8")),
        type=int,
        help="Batch size passed to ragas.evaluate.",
    )
    parser.add_argument(
        "--max-samples",
        default=None,
        type=int,
        help="Optional cap for quick iteration.",
    )
    args = parser.parse_args()
    return EvaluationRunConfig(
        input_file=Path(args.input),
        output_file=Path(args.output),
        judge_model=args.judge_model,
        embedding_model=args.embedding_model,
        batch_size=args.batch_size,
        max_samples=args.max_samples,
    )


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Unsupported file type: {path.suffix}. Use CSV or Excel.")


def parse_contexts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []

    text = str(value).strip()
    if not text:
        return []

    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue

    if "\n\n" in text:
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        if chunks:
            return chunks

    return [text]


def validate_columns(df: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_INPUT_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            f"Input file is missing required columns: {', '.join(missing)}"
        )


def normalize_samples(df: pd.DataFrame, max_samples: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_columns(df)

    working = df.copy()
    if max_samples is not None:
        working = working.head(max_samples).copy()

    if "sample_id" not in working.columns:
        working["sample_id"] = [f"sample-{index + 1}" for index in range(len(working))]

    for column in OPTIONAL_INPUT_COLUMNS:
        if column not in working.columns:
            working[column] = ""

    working["contexts"] = working["contexts"].apply(parse_contexts)
    working["question"] = working["question"].fillna("").astype(str).str.strip()
    working["answer"] = working["answer"].fillna("").astype(str).str.strip()
    working["ground_truth"] = working["ground_truth"].fillna("").astype(str).str.strip()
    working["language"] = working["language"].fillna("").astype(str).str.strip()
    working["scenario"] = working["scenario"].fillna("").astype(str).str.strip()
    working["retrieval_config"] = working["retrieval_config"].fillna("").astype(str).str.strip()

    valid_mask = (
        working["question"].ne("")
        & working["answer"].ne("")
        & working["ground_truth"].ne("")
        & working["contexts"].apply(bool)
    )
    invalid = working.loc[~valid_mask].copy()
    valid = working.loc[valid_mask].copy()
    return valid, invalid


def build_ragas_dataset(df: pd.DataFrame) -> Dataset:
    payload = {
        "user_input": df["question"].tolist(),
        "retrieved_contexts": df["contexts"].tolist(),
        "response": df["answer"].tolist(),
        "reference": df["ground_truth"].tolist(),
    }
    return Dataset.from_dict(payload)


def build_models(judge_model: str, embedding_model: str):
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    llm = llm_factory(judge_model, client=client)
    embeddings = embedding_factory(
        provider="openai",
        model=embedding_model,
        client=client,
    )
    return llm, embeddings


def run_evaluation(df: pd.DataFrame, config: EvaluationRunConfig) -> pd.DataFrame:
    dataset = build_ragas_dataset(df)
    llm, embeddings = build_models(config.judge_model, config.embedding_model)

    metrics = [
        Faithfulness(),
        AnswerRelevancy(),
        ContextRecall(),
        ContextPrecision(),
    ]
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
        batch_size=config.batch_size,
        raise_exceptions=False,
    )
    scores_df = result.to_pandas()
    merged = pd.concat([df.reset_index(drop=True), scores_df.reset_index(drop=True)], axis=1)
    merged["judge_model"] = config.judge_model
    merged["embedding_model"] = config.embedding_model
    merged["run_timestamp"] = datetime.now(timezone.utc).isoformat()
    merged["error"] = ""
    return merged


def summarize_results(scored: pd.DataFrame, invalid: pd.DataFrame) -> None:
    print("Offline Ragas evaluation complete.")
    print(f"Valid samples: {len(scored)}")
    print(f"Discarded invalid samples: {len(invalid)}")

    metric_columns = [
        column
        for column in ("faithfulness", "answer_relevancy", "context_recall", "context_precision")
        if column in scored.columns
    ]
    if metric_columns:
        print("\nOverall metric means:")
        means = scored[metric_columns].mean(numeric_only=True)
        for metric_name, value in means.items():
            print(f"- {metric_name}: {value:.4f}")

    for group_column in ("scenario", "language"):
        non_empty = scored[group_column].astype(str).str.strip().ne("").any()
        if non_empty:
            print(f"\nGrouped means by {group_column}:")
            grouped = scored.groupby(group_column)[metric_columns].mean(numeric_only=True)
            print(grouped.to_string())

    if "faithfulness" in scored.columns:
        print("\nLowest-faithfulness samples:")
        preview = scored.nsmallest(min(5, len(scored)), "faithfulness")[
            ["sample_id", "question", "faithfulness"]
        ]
        print(preview.to_string(index=False))


def persist_outputs(scored: pd.DataFrame, invalid: pd.DataFrame, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(output_file, index=False)
    if not invalid.empty:
        invalid_path = output_file.with_name(f"{output_file.stem}_invalid{output_file.suffix}")
        invalid.to_csv(invalid_path, index=False)


def main() -> None:
    config = parse_args()
    if "OPENAI_API_KEY" not in os.environ:
        raise EnvironmentError("OPENAI_API_KEY must be set before running the evaluator.")

    raw_df = load_table(config.input_file)
    valid_df, invalid_df = normalize_samples(raw_df, config.max_samples)
    if valid_df.empty:
        raise ValueError("No valid samples remained after normalization.")

    scored_df = run_evaluation(valid_df, config)
    persist_outputs(scored_df, invalid_df, config.output_file)
    summarize_results(scored_df, invalid_df)


if __name__ == "__main__":
    main()
