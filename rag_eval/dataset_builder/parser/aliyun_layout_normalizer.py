"""Normalization helpers that convert raw layout results into source chunks."""

from __future__ import annotations

import re
from typing import Any

from rag_eval.dataset_builder.models import ParsedDocument, SemanticBlock, SourceChunk, StructureNode


def _clean_text(value: Any) -> str:
    """Normalize free-form layout text into a compact string."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _is_catalog_entry(item_type: str, text: str) -> bool:
    """Detect table-of-contents style entries that should be skipped."""
    lowered = text.lower()
    return item_type == "toc" or "目录" in text or lowered.startswith("table of contents")


def _flatten_table(item: dict[str, Any]) -> str:
    """Convert a table layout node into a searchable plain-text representation."""
    rows = item.get("rows") or []
    flattened_rows: list[str] = []
    for row in rows:
        cells = [str(cell).strip() for cell in row if str(cell).strip()]
        if cells:
            flattened_rows.append(" | ".join(cells))
    return "\n".join(flattened_rows)


def _split_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split long text into overlapping windows so each chunk stays reviewable."""
    if len(text) <= max_chars:
        return [text]

    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        windows.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [window for window in windows if window]


def normalize_layouts(
    *,
    doc_id: str,
    doc_name: str,
    layouts: list[dict[str, Any]],
    max_chunk_chars: int = 1200,
    overlap_chars: int = 150,
) -> ParsedDocument:
    """Convert raw layouts into structure nodes, semantic blocks, and source chunks."""
    structure_nodes: list[StructureNode] = []
    semantic_blocks: list[SemanticBlock] = []
    source_chunks: list[SourceChunk] = []
    section_stack: list[tuple[int, str]] = []

    current_block_text: list[str] = []
    current_block_layout_ids: list[str] = []
    current_page_start: int | None = None
    current_page_end: int | None = None
    current_section_path = ""
    current_section_title = ""

    def flush_block() -> None:
        """Finalize the in-progress semantic block and emit source chunks."""
        nonlocal current_block_text, current_block_layout_ids, current_page_start, current_page_end
        nonlocal current_section_path, current_section_title

        text = _clean_text(" ".join(current_block_text))
        if not text or current_page_start is None or current_page_end is None:
            current_block_text = []
            current_block_layout_ids = []
            current_page_start = None
            current_page_end = None
            return

        block_id = f"{doc_id}-block-{len(semantic_blocks) + 1}"
        block = SemanticBlock(
            block_id=block_id,
            doc_id=doc_id,
            doc_name=doc_name,
            text=text,
            page_start=current_page_start,
            page_end=current_page_end,
            section_path=current_section_path,
            section_title=current_section_title,
            source_layout_ids=list(current_block_layout_ids),
        )
        semantic_blocks.append(block)

        chunk_parts = _split_text(text, max_chars=max_chunk_chars, overlap=overlap_chars)
        for index, part in enumerate(chunk_parts, start=1):
            heading_prefix = current_section_title.strip()
            chunk_text = f"{heading_prefix}\n{part}".strip() if heading_prefix and not part.startswith(heading_prefix) else part
            source_chunks.append(
                SourceChunk(
                    chunk_id=f"{block_id}-chunk-{index}",
                    doc_id=doc_id,
                    doc_name=doc_name,
                    text=chunk_text,
                    page_start=current_page_start,
                    page_end=current_page_end,
                    section_path=current_section_path,
                    section_title=current_section_title,
                    source_layout_ids=list(current_block_layout_ids),
                )
            )

        current_block_text = []
        current_block_layout_ids = []
        current_page_start = None
        current_page_end = None

    for index, item in enumerate(layouts, start=1):
        item_type = str(item.get("type", "paragraph")).lower()
        page = int(item.get("page", 1))
        layout_id = str(item.get("layout_id") or f"layout-{index}")
        level = int(item.get("level", 1))

        if item_type == "table":
            text = _flatten_table(item)
        else:
            text = _clean_text(item.get("text"))

        if not text or _is_catalog_entry(item_type, text):
            continue

        if item_type == "heading":
            flush_block()
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_stack.append((level, text))
            section_titles = [title for _, title in section_stack]
            current_section_title = text
            current_section_path = " > ".join(section_titles)
            structure_nodes.append(
                StructureNode(
                    node_id=f"{doc_id}-node-{len(structure_nodes) + 1}",
                    level=level,
                    title=text,
                    page_start=page,
                    page_end=page,
                    section_path=current_section_path,
                )
            )
            continue

        if item_type == "caption":
            text = f"图注: {text}"

        if current_page_start is None:
            current_page_start = page
        current_page_end = page
        current_block_text.append(text)
        current_block_layout_ids.append(layout_id)

    flush_block()
    raw_text = "\n".join(chunk.text for chunk in source_chunks)
    metadata = {
        "layout_count": len(layouts),
        "structure_node_count": len(structure_nodes),
        "semantic_block_count": len(semantic_blocks),
        "source_chunk_count": len(source_chunks),
    }
    return ParsedDocument(
        doc_id=doc_id,
        doc_name=doc_name,
        raw_text=raw_text,
        structure_nodes=structure_nodes,
        semantic_blocks=semantic_blocks,
        source_chunks=source_chunks,
        metadata=metadata,
    )
