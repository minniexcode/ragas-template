"""Pydantic schemas for dataset build YAML configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetBuildInputModel(BaseModel):
    """Schema for input PDF discovery settings."""

    model_config = ConfigDict(extra="ignore")

    path: str
    glob: str = "*.pdf"


class DatasetBuildParserModel(BaseModel):
    """Schema for parser selection and failure handling."""

    model_config = ConfigDict(extra="ignore")

    provider: Literal["aliyun_docmind"]
    failure_mode: Literal["fail", "skip"] | None = None


class DatasetBuildGenerationModel(BaseModel):
    """Schema for question generation controls."""

    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    output_type: Literal["online_question_bank"]
    review_mode: Literal["draft_with_manual_review"]
    max_questions_per_document: int = Field(default=10, gt=0)
    max_source_chunks_per_question: int = Field(default=3, gt=0)


class DatasetBuildOutputModel(BaseModel):
    """Schema for dataset build output locations."""

    model_config = ConfigDict(extra="ignore")

    dataset_path: str
    artifact_dir: str


class DatasetBuildRuntimeModel(BaseModel):
    """Schema for runtime throttling and document limits."""

    model_config = ConfigDict(extra="ignore")

    max_documents: int | None = Field(default=None, gt=0)


class DatasetBuildConfigModel(BaseModel):
    """Top-level schema for a dataset build job."""

    model_config = ConfigDict(extra="ignore")

    job_name: str
    input: DatasetBuildInputModel
    parser: DatasetBuildParserModel
    generation: DatasetBuildGenerationModel
    output: DatasetBuildOutputModel
    runtime: DatasetBuildRuntimeModel = Field(default_factory=DatasetBuildRuntimeModel)

    @model_validator(mode="after")
    def validate_job_name(self) -> "DatasetBuildConfigModel":
        """Reject blank job names that would break artifact paths."""
        if not self.job_name.strip():
            raise ValueError("job_name must not be empty.")
        return self

    def resolve_path(self, base_dir: Path, raw_path: str) -> Path:
        """Resolve relative paths against the config file directory."""
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return (base_dir / candidate).resolve()
