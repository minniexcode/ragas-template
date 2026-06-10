"""Input source discovery helpers for dataset build jobs."""

from __future__ import annotations

from pathlib import Path


def discover_pdf_files(input_path: Path, pattern: str = "*.pdf") -> list[Path]:
    """Return all PDF files from a single file path or a directory scan."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file is not a PDF: {input_path}")
        return [input_path]

    files = sorted(path for path in input_path.glob(pattern) if path.is_file() and path.suffix.lower() == ".pdf")
    if not files:
        raise ValueError(f"No PDF files found under {input_path} with pattern {pattern}")
    return files
