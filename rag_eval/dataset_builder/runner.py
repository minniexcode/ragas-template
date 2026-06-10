"""Orchestration layer for PDF-to-dataset build jobs."""

from __future__ import annotations

from pathlib import Path

import yaml

from rag_eval.settings import EvaluationSettings
from rag_eval.shared.utils import ensure_directory, utc_now_iso

from .generator.question_generator import OpenAIQuestionGenerator, QuestionGenerator
from .generator.validators import dedupe_samples, validate_draft_sample
from .models import DatasetBuildJob, DatasetBuildResult, DatasetBuildRuntime, ParseFailure
from .parser.aliyun_document_parser import AliyunDocumentParser
from .parser.aliyun_docmind_gateway import AliyunDocmindGateway
from .schema import DatasetBuildConfigModel
from .sources import discover_pdf_files
from .writers import build_artifact_paths, write_dataset_build_artifacts


def load_dataset_build_job(path: str | Path, settings: EvaluationSettings | None = None) -> DatasetBuildJob:
    """Load and validate a dataset build YAML file."""
    settings = settings or EvaluationSettings()
    config_path = Path(path).resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model = DatasetBuildConfigModel.model_validate(payload)
    base_dir = config_path.parent

    generation_model = (
        model.generation.model
        or settings.dataset_generator_model
        or "qwen3.6-plus"
    )
    parser_payload = payload.get("parser") or {}
    failure_mode = parser_payload.get("failure_mode") or settings.parser_failure_mode or "fail"
    return DatasetBuildJob(
        job_name=model.job_name,
        input_path=model.resolve_path(base_dir, model.input.path),
        input_glob=model.input.glob,
        parser_provider=model.parser.provider,
        failure_mode=failure_mode,
        generation_model=generation_model,
        output_type=model.generation.output_type,
        review_mode=model.generation.review_mode,
        max_questions_per_document=model.generation.max_questions_per_document,
        max_source_chunks_per_question=model.generation.max_source_chunks_per_question,
        dataset_path=model.resolve_path(base_dir, model.output.dataset_path),
        artifact_dir=model.resolve_path(base_dir, model.output.artifact_dir),
        runtime=DatasetBuildRuntime(max_documents=model.runtime.max_documents),
        source_path=config_path,
    )


def _create_parser(job: DatasetBuildJob, settings: EvaluationSettings) -> AliyunDocumentParser:
    """Create the configured document parser implementation."""
    if job.parser_provider != "aliyun_docmind":
        raise ValueError(f"Unsupported parser provider: {job.parser_provider}")
    gateway = AliyunDocmindGateway(settings)
    return AliyunDocumentParser(gateway)


def _create_generator(job: DatasetBuildJob, settings: EvaluationSettings) -> QuestionGenerator:
    """Create the configured draft question generator implementation."""
    return OpenAIQuestionGenerator(settings=settings, model=job.generation_model)


def run_dataset_build(
    config_path: str | Path,
    *,
    settings: EvaluationSettings | None = None,
    parser: AliyunDocumentParser | None = None,
    generator: QuestionGenerator | None = None,
) -> DatasetBuildResult:
    """Run one dataset build job end to end and persist all required artifacts."""
    settings = settings or EvaluationSettings()
    job = load_dataset_build_job(config_path, settings=settings)
    pdf_files = discover_pdf_files(job.input_path, job.input_glob)
    if job.runtime.max_documents is not None:
        pdf_files = pdf_files[: job.runtime.max_documents]

    parser = parser or _create_parser(job, settings)
    generator = generator or _create_generator(job, settings)

    run_id = utc_now_iso().replace(":", "-")
    artifact_root = job.artifact_dir / run_id
    ensure_directory(artifact_root)
    artifact_paths = build_artifact_paths(artifact_root)

    documents = []
    failures: list[ParseFailure] = []
    draft_samples = []

    for pdf_path in pdf_files:
        try:
            document = parser.parse(pdf_path)
        except Exception as exc:
            failure = ParseFailure(file_path=pdf_path.as_posix(), error=str(exc))
            failures.append(failure)
            if job.failure_mode == "fail":
                result = DatasetBuildResult(
                    job=job,
                    run_id=run_id,
                    artifact_paths=artifact_paths,
                    documents=documents,
                    draft_samples=draft_samples,
                    parse_failures=failures,
                )
                write_dataset_build_artifacts(result)
                raise
            continue

        documents.append(document)
        generated = generator.generate(
            document,
            max_questions=job.max_questions_per_document,
            max_chunks_per_question=job.max_source_chunks_per_question,
            job_name=job.job_name,
        )
        valid_generated = []
        for sample in generated:
            errors = validate_draft_sample(
                sample,
                document=document,
                max_source_chunks_per_question=job.max_source_chunks_per_question,
            )
            if not errors:
                valid_generated.append(sample)
        draft_samples.extend(
            dedupe_samples(valid_generated)[: job.max_questions_per_document]
        )

    result = DatasetBuildResult(
        job=job,
        run_id=run_id,
        artifact_paths=artifact_paths,
        documents=documents,
        draft_samples=draft_samples,
        parse_failures=failures,
    )
    write_dataset_build_artifacts(result)
    return result
