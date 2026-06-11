from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from rag_eval.settings import EvaluationSettings
from rag_eval.shared.utils import parse_contexts


_CHUNK_CACHE: dict[Path, dict[str, dict[str, Any]]] = {}


def _resolve_source_chunks_path(source_chunks_path: str) -> Path:
    """Resolve the configured chunk artifact path, with fallback for missing latest aliases."""
    resolved_path = Path(source_chunks_path).resolve()
    if resolved_path.exists():
        return resolved_path

    if resolved_path.parent.name != "latest":
        raise FileNotFoundError(resolved_path)

    artifact_root = resolved_path.parent.parent
    if not artifact_root.exists():
        raise FileNotFoundError(resolved_path)

    candidate_runs = sorted(
        [
            entry for entry in artifact_root.iterdir()
            if entry.is_dir() and entry.name != "latest"
        ],
        key=lambda path: path.name,
        reverse=True,
    )
    for run_dir in candidate_runs:
        candidate = run_dir / resolved_path.name
        if candidate.exists():
            return candidate

    raise FileNotFoundError(resolved_path)


def _load_source_chunks(source_chunks_path: str) -> dict[str, dict[str, Any]]:
    """Load source chunk rows from JSONL and cache them by absolute file path."""
    resolved_path = _resolve_source_chunks_path(source_chunks_path)
    cached = _CHUNK_CACHE.get(resolved_path)
    if cached is not None:
        return cached

    chunk_lookup: dict[str, dict[str, Any]] = {}
    with resolved_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            chunk_id = str(payload.get("chunk_id", "")).strip()
            if not chunk_id:
                raise ValueError(
                    f"source_chunks.jsonl row {line_number} is missing chunk_id: {resolved_path}"
                )
            chunk_lookup[chunk_id] = payload

    _CHUNK_CACHE[resolved_path] = chunk_lookup
    return chunk_lookup


def _resolve_chunk_ids(raw_chunk_ids: Any) -> list[str]:
    """Parse the serialized source chunk id column into a non-empty list."""
    chunk_ids = parse_contexts(raw_chunk_ids)
    normalized = [chunk_id for chunk_id in chunk_ids if chunk_id]
    if not normalized:
        raise ValueError("source_chunk_ids is required for pdf question bank samples.")
    return normalized


def _build_messages(question: str, contexts: list[str], metadata: dict[str, Any]) -> list[dict[str, str]]:
    """Construct an evidence-grounded prompt for answer generation."""
    evidence_lines = [
        f"[chunk {index}] {context}"
        for index, context in enumerate(contexts, start=1)
    ]
    metadata_lines = [
        f"doc_id: {metadata.get('doc_id', '')}",
        f"doc_name: {metadata.get('doc_name', '')}",
        f"section_path: {metadata.get('section_path', '')}",
    ]
    system_prompt = (
        "You answer questions only from the provided evidence chunks. "
        "Do not use outside knowledge. If the evidence is insufficient, say so plainly. "
        "Do not invent missing facts, citations, steps, or numbers."
    )
    user_prompt = "\n".join(
        [
            "Question:",
            question,
            "",
            "Sample metadata:",
            *metadata_lines,
            "",
            "Evidence chunks:",
            *evidence_lines,
            "",
            "Return a concise answer grounded only in the evidence above.",
        ]
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def run(
    question: str,
    *,
    source_chunks_path: str,
    model: str | None = None,
    client: OpenAI | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Answer one question by resolving cited chunks and querying an OpenAI-compatible model."""
    chunk_ids = _resolve_chunk_ids(kwargs.get("source_chunk_ids"))
    chunk_lookup = _load_source_chunks(source_chunks_path)

    missing_ids = [chunk_id for chunk_id in chunk_ids if chunk_id not in chunk_lookup]
    if missing_ids:
        raise ValueError(
            "source_chunk_ids not found in source chunks artifact: " + ", ".join(missing_ids)
        )

    resolved_chunks = [chunk_lookup[chunk_id] for chunk_id in chunk_ids]
    contexts = [str(chunk.get("text", "")).strip() for chunk in resolved_chunks if str(chunk.get("text", "")).strip()]
    if not contexts:
        raise ValueError("resolved source chunks did not contain usable text contexts.")

    settings = EvaluationSettings()
    target_model = (model or settings.ragas_judge_model).strip()
    if not target_model:
        raise ValueError("A model name is required for pdf question bank adapter.")

    llm_client = client or OpenAI(**settings.openai_client_kwargs)
    completion = llm_client.chat.completions.create(
        model=target_model,
        messages=_build_messages(question, contexts, kwargs),
        temperature=0,
    )
    answer = str(completion.choices[0].message.content or "").strip()

    return {
        "answer": answer,
        "contexts": contexts,
        "raw_response": {
            "resolved_chunk_ids": chunk_ids,
            "resolved_doc_id": kwargs.get("doc_id", ""),
            "resolved_doc_name": kwargs.get("doc_name", ""),
            "model": target_model,
            "response_text": answer,
        },
    }
