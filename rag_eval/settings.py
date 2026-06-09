"""Runtime settings loaded from environment variables for evaluation runs."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[1]


class EvaluationSettings(BaseSettings):
    """Application settings shared by the CLI, adapters, and metric pipeline."""
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    ragas_judge_model: str = Field(default="gpt-4o-mini", alias="RAGAS_JUDGE_MODEL")
    ragas_embedding_model: str = Field(
        default="text-embedding-3-large",
        alias="RAGAS_EMBEDDING_MODEL",
    )
    batch_size: int = Field(default=8, alias="BATCH_SIZE")

    @property
    def openai_client_kwargs(self) -> dict[str, str]:
        """Return keyword arguments for the OpenAI client when credentials are available."""
        if not self.openai_api_key:
            return {}

        client_kwargs: dict[str, str] = {"api_key": self.openai_api_key}
        if self.openai_base_url.strip():
            client_kwargs["base_url"] = self.openai_base_url.strip()
        return client_kwargs
