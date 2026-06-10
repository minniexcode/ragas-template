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
    openai_base_url: str = Field(default="http://6.86.80.4:30080/v1", alias="OPENAI_BASE_URL")
    ragas_judge_model: str = Field(default="deepseek-v4-flash", alias="RAGAS_JUDGE_MODEL")
    ragas_embedding_model: str = Field(
        default="text-embedding-v3",
        alias="RAGAS_EMBEDDING_MODEL",
    )
    batch_size: int = Field(default=8, alias="BATCH_SIZE")
    alibaba_access_key_id: str | None = Field(default=None, alias="ALIBABA_ACCESS_KEY_ID")
    alibaba_access_key_secret: str | None = Field(default=None, alias="ALIBABA_ACCESS_KEY_SECRET")
    alibaba_endpoint: str | None = Field(default=None, alias="ALIBABA_ENDPOINT")
    aliyun_parse_poll_interval_seconds: int = Field(
        default=5,
        alias="ALIYUN_PARSE_POLL_INTERVAL_SECONDS",
    )
    aliyun_parse_timeout_seconds: int = Field(
        default=600,
        alias="ALIYUN_PARSE_TIMEOUT_SECONDS",
    )
    aliyun_parse_layout_step_size: int = Field(
        default=50,
        alias="ALIYUN_PARSE_LAYOUT_STEP_SIZE",
    )
    aliyun_llm_enhancement: bool = Field(default=False, alias="ALIYUN_LLM_ENHANCEMENT")
    aliyun_enhancement_mode: str = Field(default="balanced", alias="ALIYUN_ENHANCEMENT_MODE")
    document_parse_artifact_prefix: str = Field(
        default="outputs/dataset-builds",
        alias="DOCUMENT_PARSE_ARTIFACT_PREFIX",
    )
    parser_failure_mode: str = Field(default="fail", alias="PARSER_FAILURE_MODE")
    dataset_generator_model: str | None = Field(default=None, alias="DATASET_GENERATOR_MODEL")

    @property
    def openai_client_kwargs(self) -> dict[str, str]:
        """Return keyword arguments for the OpenAI client when credentials are available."""
        if not self.openai_api_key:
            return {}

        client_kwargs: dict[str, str] = {"api_key": self.openai_api_key}
        if self.openai_base_url.strip():
            client_kwargs["base_url"] = self.openai_base_url.strip()
        return client_kwargs
