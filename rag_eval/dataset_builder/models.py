"""Internal data models for the PDF-to-dataset build workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


ReviewStatus = Literal["draft", "approved", "rejected", "needs_edit"]
QuestionType = Literal["fact", "summary", "procedure", "comparison"]
Difficulty = Literal["easy", "medium", "hard"]
FailureMode = Literal["fail", "skip"]


@dataclass(slots=True)
class DatasetBuildRuntime:
    """Runtime controls for one dataset build job."""

    max_documents: int | None = None


@dataclass(slots=True)
class DatasetBuildJob:
    """Resolved dataset build configuration consumed by the build runner."""

    job_name: str
    input_path: Path
    input_glob: str
    parser_provider: str
    failure_mode: FailureMode
    generation_model: str
    output_type: str
    review_mode: str
    max_questions_per_document: int
    max_source_chunks_per_question: int
    dataset_path: Path
    artifact_dir: Path
    runtime: DatasetBuildRuntime = field(default_factory=DatasetBuildRuntime)
    source_path: Path | None = None

    def snapshot(self) -> dict[str, Any]:
        """Serialize the job into JSON-friendly metadata."""
        payload = asdict(self)
        payload["input_path"] = self.input_path.as_posix()
        payload["dataset_path"] = self.dataset_path.as_posix()
        payload["artifact_dir"] = self.artifact_dir.as_posix()
        if self.source_path is not None:
            payload["source_path"] = self.source_path.as_posix()
        return payload


@dataclass(slots=True)
class StructureNode:
    """One normalized structure heading extracted from layout results."""

    node_id: str
    level: int
    title: str
    page_start: int
    page_end: int
    section_path: str


@dataclass(slots=True)
class SemanticBlock:
    """One merged semantic block used as an intermediate artifact before chunking."""

    block_id: str
    doc_id: str
    doc_name: str
    text: str
    page_start: int
    page_end: int
    section_path: str
    section_title: str
    source_layout_ids: list[str]

    def to_record(self) -> dict[str, Any]:
        """Convert the block into a flat artifact record."""
        return asdict(self)


@dataclass(slots=True)
class SourceChunk:
    """Evidence chunk used for question generation and human review."""

    chunk_id: str
    doc_id: str
    doc_name: str
    text: str
    page_start: int
    page_end: int
    section_path: str
    section_title: str
    source_layout_ids: list[str]

    def to_record(self) -> dict[str, Any]:
        """Convert the chunk into a flat artifact record."""
        return asdict(self)


@dataclass(slots=True)
class ParsedDocument:
    """Normalized parsed document ready for question generation."""

    doc_id: str
    doc_name: str
    raw_text: str
    structure_nodes: list[StructureNode]
    semantic_blocks: list[SemanticBlock]
    source_chunks: list[SourceChunk]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """Convert the parsed document into a summary artifact record."""
        return {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "raw_text": self.raw_text,
            "structure_nodes": [asdict(item) for item in self.structure_nodes],
            "metadata": self.metadata,
            "semantic_block_count": len(self.semantic_blocks),
            "source_chunk_count": len(self.source_chunks),
        }


@dataclass(slots=True)
class DraftQuestionSample:
    """One draft online evaluation sample pending manual review."""

    sample_id: str
    question: str
    ground_truth: str
    scenario: str
    language: str
    doc_id: str
    doc_name: str
    section_path: str
    page_start: int
    page_end: int
    source_chunk_ids: list[str]
    question_type: QuestionType
    difficulty: Difficulty
    review_status: ReviewStatus = "draft"
    review_notes: str = ""

    def to_record(self) -> dict[str, Any]:
        """Convert the draft sample into a flat CSV row."""
        return {
            "sample_id": self.sample_id,
            "question": self.question,
            "ground_truth": self.ground_truth,
            "scenario": self.scenario,
            "language": self.language,
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "section_path": self.section_path,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "source_chunk_ids": self.source_chunk_ids,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "review_status": self.review_status,
            "review_notes": self.review_notes,
        }


@dataclass(slots=True)
class ParseFailure:
    """One document parse failure recorded for reporting and skip-mode execution."""

    file_path: str
    error: str

    def to_record(self) -> dict[str, str]:
        """Convert the failure into a flat CSV row."""
        return asdict(self)


@dataclass(slots=True)
class DatasetBuildArtifactPaths:
    """Canonical file paths produced by one dataset build run."""

    root_dir: Path
    documents_jsonl: Path
    semantic_blocks_jsonl: Path
    source_chunks_jsonl: Path
    dataset_draft_csv: Path
    parse_failures_csv: Path
    metadata_json: Path


@dataclass(slots=True)
class DatasetBuildResult:
    """Aggregate result object returned after a dataset build completes."""

    job: DatasetBuildJob
    run_id: str
    artifact_paths: DatasetBuildArtifactPaths
    documents: list[ParsedDocument]
    draft_samples: list[DraftQuestionSample]
    parse_failures: list[ParseFailure]
