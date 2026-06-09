"""Markdown summary generation for completed evaluation runs."""

from __future__ import annotations

import math

import pandas as pd

from rag_eval.shared.models import EvaluationResult


def _table_from_frame(frame: pd.DataFrame) -> str:
    """Render a small dataframe as a fixed-width markdown-friendly text table."""
    if frame.empty:
        return "No rows."

    columns = list(frame.columns)
    rows = [[str(value) for value in row] for row in frame.astype(object).values.tolist()]
    widths = []
    for index, column in enumerate(columns):
        column_width = len(str(column))
        row_width = max((len(row[index]) for row in rows), default=0)
        widths.append(max(column_width, row_width))

    header = " | ".join(str(column).ljust(widths[idx]) for idx, column in enumerate(columns))
    separator = "-|-".join("-" * widths[idx] for idx in range(len(columns)))
    body = [
        " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(columns)))
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def build_summary_markdown(result: EvaluationResult) -> str:
    """Build the human-readable markdown summary written for each evaluation run."""
    total = len(result.valid_samples) + len(result.invalid_samples)
    scores = pd.DataFrame(result.score_rows)

    lines = [
        f"# {result.scenario.scenario_name}",
        "",
        f"- run_id: `{result.run_id}`",
        f"- mode: `{result.scenario.mode}`",
        f"- total_samples: `{total}`",
        f"- valid_samples: `{len(result.valid_samples)}`",
        f"- invalid_samples: `{len(result.invalid_samples)}`",
        f"- judge_model: `{result.scenario.judge_model}`",
        f"- embedding_model: `{result.scenario.embedding_model}`",
        "",
        "## Metric Means",
        "",
    ]

    if scores.empty:
        lines.append("No valid samples were scored.")
        return "\n".join(lines) + "\n"

    for metric in result.scenario.metrics:
        mean_value = scores[metric].mean(numeric_only=True)
        if isinstance(mean_value, float) and not math.isnan(mean_value):
            lines.append(f"- {metric}: `{mean_value:.4f}`")
        else:
            lines.append(f"- {metric}: `n/a`")

    # Surface the weakest-scoring samples first to make manual inspection faster.
    lowest_metric = result.scenario.metrics[0]
    preview_columns = ["sample_id", lowest_metric]
    preview = scores.nsmallest(min(3, len(scores)), lowest_metric)[preview_columns]
    lines.extend(
        [
            "",
            f"## Lowest {lowest_metric}",
            "",
            "```text",
            _table_from_frame(preview),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"
