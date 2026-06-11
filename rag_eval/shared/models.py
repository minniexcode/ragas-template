"""Shared runtime data models exchanged across the evaluation pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


Mode = Literal["offline", "online"]
AdapterType = Literal["http", "python"]


def _serialize_paths(value: Any) -> Any:
    """Convert Path instances nested inside snapshot payloads into POSIX strings."""
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {key: _serialize_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_paths(item) for item in value]
    return value


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
        return _serialize_paths(asdict(self))


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
