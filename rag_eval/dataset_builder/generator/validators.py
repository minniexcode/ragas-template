"""Validation and deduplication helpers for generated draft question samples."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from rag_eval.dataset_builder.models import DraftQuestionSample, ParsedDocument


ALLOWED_QUESTION_TYPES = {"fact", "summary", "procedure", "comparison"}
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}


def validate_draft_sample(
    sample: DraftQuestionSample,
    *,
    document: ParsedDocument,
    max_source_chunks_per_question: int | None = None,
) -> list[str]:
    """Validate one generated sample against the document and enum constraints."""
    errors: list[str] = []
    if not sample.question.strip():
        errors.append("question is empty")
    if not sample.ground_truth.strip():
        errors.append("ground_truth is empty")
    if not sample.source_chunk_ids:
        errors.append("source_chunk_ids is empty")
    if (
        max_source_chunks_per_question is not None
        and len(sample.source_chunk_ids) > max_source_chunks_per_question
    ):
        errors.append(
            f"source_chunk_ids exceeds limit: {len(sample.source_chunk_ids)} > {max_source_chunks_per_question}"
        )

    existing_chunk_ids = {chunk.chunk_id for chunk in document.source_chunks}
    for chunk_id in sample.source_chunk_ids:
        if chunk_id not in existing_chunk_ids:
            errors.append(f"unknown source chunk: {chunk_id}")

    if sample.doc_id != document.doc_id:
        errors.append("sample doc_id does not match source document")
    if sample.question_type not in ALLOWED_QUESTION_TYPES:
        errors.append(f"unsupported question_type: {sample.question_type}")
    if sample.difficulty not in ALLOWED_DIFFICULTIES:
        errors.append(f"unsupported difficulty: {sample.difficulty}")
    return errors


def normalize_question_text(text: str) -> str:
    """Normalize question text for exact-match deduplication."""
    return re.sub(r"\s+", " ", text).strip().lower()


def dedupe_samples(samples: list[DraftQuestionSample]) -> list[DraftQuestionSample]:
    """Drop duplicate questions and enforce one output per chunk group per document."""
    deduped: list[DraftQuestionSample] = []
    seen_questions: set[tuple[str, str]] = set()
    seen_chunk_groups: set[tuple[str, tuple[str, ...]]] = set()
    seen_chunk_answers: list[tuple[str, tuple[str, ...], str]] = []

    for sample in samples:
        question_key = (sample.doc_id, normalize_question_text(sample.question))
        if question_key in seen_questions:
            continue

        chunk_key = tuple(sample.source_chunk_ids)
        chunk_group_key = (sample.doc_id, chunk_key)
        if chunk_group_key in seen_chunk_groups:
            continue
        answer_key = normalize_question_text(sample.ground_truth)
        duplicate = False
        for existing_doc_id, existing_chunk_key, existing_answer in seen_chunk_answers:
            if existing_doc_id != sample.doc_id or existing_chunk_key != chunk_key:
                continue
            if SequenceMatcher(None, existing_answer, answer_key).ratio() >= 0.9:
                duplicate = True
                break
        if duplicate:
            continue

        seen_questions.add(question_key)
        seen_chunk_groups.add(chunk_group_key)
        seen_chunk_answers.append((sample.doc_id, chunk_key, answer_key))
        deduped.append(sample)
    return deduped
