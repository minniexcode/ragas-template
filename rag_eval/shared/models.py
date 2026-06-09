"""Shared runtime data models exchanged across the evaluation pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


Mode = Literal["offline", "online"]
AdapterType = Literal["http", "python"]


@dataclass(slots=True)
class RuntimeConfig:
    """Concurrency and sampling controls for one evaluation run."""

    batch_size: int = 4
    app_concurrency: int | None = None
    metric_concurrency: int | None = None
    max_samples: int | None = None

    def metric_limit(self) -> int:
        """Return the effective metric-scoring concurrency limit."""
        return self.metric_concurrency or self.batch_size

    def app_limit(self) -> int:
        """Return the effective application-call concurrency limit."""
        return self.app_concurrency or self.batch_size


@dataclass(slots=True)
class AppAdapterConfig:
    """Resolved adapter configuration used by online scenarios."""

    type: AdapterType
    endpoint: str | None = None
    method: str = "POST"
    timeout_seconds: int = 30
    callable: str | None = None
    request_template: dict[str, Any] = field(default_factory=dict)
    response_mapping: dict[str, str] = field(default_factory=dict)
    static_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DatasetConfig:
    """Dataset location information for a scenario."""

    path: Path
    format: str | None = None


@dataclass(slots=True)
class Scenario:
    """Resolved evaluation scenario consumed by the execution pipeline."""

    scenario_name: str
    mode: Mode
    dataset: DatasetConfig
    judge_model: str
    embedding_model: str
    metrics: list[str]
    output_dir: Path
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    app_adapter: AppAdapterConfig | None = None
    source_path: Path | None = None

    def snapshot(self) -> dict[str, Any]:
        """Serialize the scenario into a reporting-friendly dictionary snapshot."""
        payload = asdict(self)
        payload["dataset"]["path"] = self.dataset.path.as_posix()
        payload["output_dir"] = self.output_dir.as_posix()
        if self.source_path is not None:
            payload["source_path"] = self.source_path.as_posix()
        return payload


@dataclass(slots=True)
class NormalizedSample:
    """Canonical sample shape used by adapters, metrics, and reporting."""

    sample_id: str
    question: str
    contexts: list[str]
    answer: str
    ground_truth: str
    scenario: str = ""
    language: str = ""
    retrieval_config: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Convert the sample into a flat record for CSV and artifact generation."""
        record = {
            "sample_id": self.sample_id,
            "question": self.question,
            "contexts": self.contexts,
            "answer": self.answer,
            "ground_truth": self.ground_truth,
            "scenario": self.scenario,
            "language": self.language,
            "retrieval_config": self.retrieval_config,
        }
        record.update(self.metadata)
        return record


@dataclass(slots=True)
class InvalidSample:
    """A dataset or adapter sample that could not be evaluated."""

    sample_id: str
    error: str
    raw: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        """Convert the invalid sample into a flat reporting row."""
        record = {"sample_id": self.sample_id, "error": self.error}
        record.update(self.raw)
        return record


@dataclass(slots=True)
class MetricScore:
    """Metric values and accumulated errors for one evaluated sample."""

    metrics: dict[str, float | None]
    error: str = ""


@dataclass(slots=True)
class EvaluationResult:
    """Aggregate result object returned after a scenario completes."""

    scenario: Scenario
    run_id: str
    started_at: str
    finished_at: str
    valid_samples: list[NormalizedSample]
    invalid_samples: list[InvalidSample]
    score_rows: list[dict[str, Any]]


@dataclass(slots=True)
class RunArtifactPaths:
    """Canonical file-system paths for all artifacts produced by one run."""

    root_dir: Path
    scenario_snapshot: Path
    scores_csv: Path
    invalid_csv: Path
    summary_md: Path
    metadata_json: Path
