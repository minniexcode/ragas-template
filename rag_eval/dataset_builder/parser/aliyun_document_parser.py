"""Document parser that normalizes Alibaba layout results into internal models."""

from __future__ import annotations

from pathlib import Path

from rag_eval.dataset_builder.models import ParsedDocument

from .aliyun_docmind_gateway import AliyunDocmindGateway
from .aliyun_layout_normalizer import normalize_layouts


class AliyunDocumentParser:
    """Parse PDFs through the Alibaba gateway and normalize the returned layouts."""

    def __init__(self, gateway: AliyunDocmindGateway):
        """Store the gateway dependency used for remote parsing."""
        self.gateway = gateway

    def parse(self, pdf_path: Path) -> ParsedDocument:
        """Parse one PDF file into a normalized parsed-document model."""
        payload = self.gateway.parse_document(pdf_path)
        layouts = payload.get("layouts") or []
        if not layouts:
            raise ValueError(f"No layouts returned for document: {pdf_path.name}")

        document = normalize_layouts(
            doc_id=str(payload.get("doc_id") or pdf_path.stem),
            doc_name=str(payload.get("doc_name") or pdf_path.name),
            layouts=list(layouts),
        )
        document.metadata.update(
            {
                "task_id": payload.get("task_id"),
                "provider": "aliyun_docmind",
            }
        )
        return document
