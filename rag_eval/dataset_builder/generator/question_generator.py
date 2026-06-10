"""LLM-backed question generator for dataset build jobs."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI

from rag_eval.dataset_builder.models import DraftQuestionSample, ParsedDocument, SourceChunk
from rag_eval.settings import EvaluationSettings


class QuestionGenerator(ABC):
    """Abstract interface for generating draft questions from parsed documents."""

    @abstractmethod
    def generate(
        self,
        document: ParsedDocument,
        *,
        max_questions: int,
        max_chunks_per_question: int,
        job_name: str,
    ) -> list[DraftQuestionSample]:
        """Generate draft question samples for one parsed document."""
        raise NotImplementedError


class OpenAIQuestionGenerator(QuestionGenerator):
    """Generate draft questions with an OpenAI-compatible chat completion API."""

    def __init__(self, settings: EvaluationSettings, model: str, client: OpenAI | None = None):
        """Initialize the OpenAI-compatible client and target generation model."""
        if not settings.openai_api_key:
            raise EnvironmentError("OPENAI_API_KEY must be set before generating draft questions.")
        self.client = client or OpenAI(**settings.openai_client_kwargs)
        self.model = model

    def _build_prompt(
        self,
        document: ParsedDocument,
        *,
        max_questions: int,
        max_chunks_per_question: int,
    ) -> str:
        """Build a constrained JSON-generation prompt for one document."""
        chunk_lines: list[str] = []
        for chunk in document.source_chunks:
            chunk_lines.append(
                json.dumps(
                    {
                        "chunk_id": chunk.chunk_id,
                        "section_path": chunk.section_path,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "text": chunk.text,
                    },
                    ensure_ascii=False,
                )
            )

        instructions = {
            "task": "Generate reviewable online evaluation draft questions from one document only.",
            "rules": [
                "Return JSON only.",
                f"Generate at most {max_questions} samples.",
                f"Each sample may cite at most {max_chunks_per_question} chunk ids.",
                "Every sample must stay within this document and use existing chunk ids only.",
                "Allowed question_type values: fact, summary, procedure, comparison.",
                "Allowed difficulty values: easy, medium, hard.",
            ],
            "output_schema": {
                "samples": [
                    {
                        "question": "string",
                        "ground_truth": "string",
                        "source_chunk_ids": ["chunk-id"],
                        "question_type": "fact|summary|procedure|comparison",
                        "difficulty": "easy|medium|hard",
                    }
                ]
            },
            "document": {
                "doc_id": document.doc_id,
                "doc_name": document.doc_name,
                "chunks": chunk_lines,
            },
        }
        return json.dumps(instructions, ensure_ascii=False, indent=2)

    def _build_sample(
        self,
        *,
        document: ParsedDocument,
        payload: dict[str, Any],
        index: int,
        job_name: str,
    ) -> DraftQuestionSample:
        """Convert one model output object into the internal draft sample model."""
        chunk_lookup: dict[str, SourceChunk] = {item.chunk_id: item for item in document.source_chunks}
        source_chunk_ids = [str(item).strip() for item in payload.get("source_chunk_ids") or [] if str(item).strip()]
        chunks = [chunk_lookup[item] for item in source_chunk_ids if item in chunk_lookup]

        section_path = chunks[0].section_path if chunks else ""
        page_start = min((chunk.page_start for chunk in chunks), default=0)
        page_end = max((chunk.page_end for chunk in chunks), default=0)
        language = "zh" if any("\u4e00" <= char <= "\u9fff" for char in payload.get("question", "")) else "en"
        return DraftQuestionSample(
            sample_id=f"{document.doc_id}-q{index}",
            question=str(payload.get("question", "")).strip(),
            ground_truth=str(payload.get("ground_truth", "")).strip(),
            scenario=job_name,
            language=language,
            doc_id=document.doc_id,
            doc_name=document.doc_name,
            section_path=section_path,
            page_start=page_start,
            page_end=page_end,
            source_chunk_ids=source_chunk_ids,
            question_type=str(payload.get("question_type", "fact")).strip() or "fact",
            difficulty=str(payload.get("difficulty", "medium")).strip() or "medium",
        )

    @staticmethod
    def _parse_response_payload(content: str) -> list[dict[str, Any]]:
        """Parse the model response into a list of sample payload dictionaries."""
        try:
            payload = json.loads(content or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("Question generator returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Question generator response must be a JSON object.")
        samples = payload.get("samples") or []
        if not isinstance(samples, list):
            raise ValueError("Question generator response field 'samples' must be a list.")

        normalized_samples: list[dict[str, Any]] = []
        for item in samples:
            if isinstance(item, dict):
                normalized_samples.append(item)
        return normalized_samples

    def generate(
        self,
        document: ParsedDocument,
        *,
        max_questions: int,
        max_chunks_per_question: int,
        job_name: str,
    ) -> list[DraftQuestionSample]:
        """Generate draft questions for one parsed document."""
        prompt = self._build_prompt(
            document,
            max_questions=max_questions,
            max_chunks_per_question=max_chunks_per_question,
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You generate structured draft question banks from source documents."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = self._parse_response_payload(content)
        return [
            self._build_sample(document=document, payload=item, index=index, job_name=job_name)
            for index, item in enumerate(payload[:max_questions], start=1)
        ]
