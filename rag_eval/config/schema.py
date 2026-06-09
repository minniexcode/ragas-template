"""Pydantic schemas used to validate raw scenario configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RuntimeConfigModel(BaseModel):
    """Schema for runtime concurrency and sampling settings."""
    model_config = ConfigDict(extra="ignore")

    batch_size: int = 4
    app_concurrency: int | None = None
    metric_concurrency: int | None = None
    max_samples: int | None = None


class AppAdapterConfigModel(BaseModel):
    """Schema for adapter-specific configuration in online scenarios."""
    model_config = ConfigDict(extra="ignore")

    type: Literal["http", "python"]
    endpoint: str | None = None
    method: str = "POST"
    timeout_seconds: int = 30
    callable: str | None = None
    request_template: dict[str, Any] = Field(default_factory=dict)
    response_mapping: dict[str, str] = Field(default_factory=dict)
    static_kwargs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> "AppAdapterConfigModel":
        """Enforce the fields required by each adapter type."""
        if self.type == "http" and not self.endpoint:
            raise ValueError("HTTP adapter requires endpoint.")
        if self.type == "python" and not self.callable:
            raise ValueError("Python adapter requires callable.")
        return self


class ScenarioModel(BaseModel):
    """Schema for a user-authored evaluation scenario file."""
    model_config = ConfigDict(extra="ignore")

    scenario_name: str
    mode: Literal["offline", "online"]
    app_adapter: AppAdapterConfigModel | None = None
    dataset: str
    judge_model: str
    embedding_model: str
    metrics: list[str]
    output_dir: str
    runtime: RuntimeConfigModel = Field(default_factory=RuntimeConfigModel)

    @field_validator("metrics")
    @classmethod
    def ensure_metrics_not_empty(cls, value: list[str]) -> list[str]:
        """Reject scenarios that do not request any metrics."""
        if not value:
            raise ValueError("metrics must not be empty.")
        return value

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> "ScenarioModel":
        """Ensure online scenarios define the adapter they depend on."""
        if self.mode == "online" and self.app_adapter is None:
            raise ValueError("online mode requires app_adapter.")
        return self

    def resolve_path(self, base_dir: Path, raw_path: str) -> Path:
        """Resolve relative paths against the scenario file directory."""
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        return (base_dir / candidate).resolve()
